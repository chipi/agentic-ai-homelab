"""End-to-end real send through the NEW multi-tenant delivery code.

Builds the podcast tenant, renders a real your-week-digest via the podcast template dir,
sends a LIVE email through Resend to the recipient on argv, and reports the o11y that fired:
the delivery_sent_total metric + the canonical JSONL event (tenant + correlation_id).

    python e2e_send.py marko.dragoljevic@gmail.com
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

from dotenv import dotenv_values

from delivery.config import DeliveryConfig
from delivery.envelope import Channel, DeliveryEnvelope
from delivery.metrics import SENT_TOTAL
from delivery.render import Renderer
from delivery.resend_client import ResendClient
from delivery.tenant import TenantConfig
from delivery.transports import EmailTransport

ROOT = Path(__file__).resolve().parent
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")


def _podcast_tenant() -> TenantConfig:
    return TenantConfig(
        name="podcast",
        outbox_base_url="http://unused",
        internal_token="x",
        mail_from="Close Listening <digest@mail.closelistening.app>",
        app_origin="https://closelistening.app",
        unsubscribe_path="/api/app/comms/unsubscribe",
        vapid_private_key="",
        vapid_subject="mailto:info@closelistening.app",
        template_dir=ROOT / "delivery" / "templates" / "podcast",
        schema_dir=ROOT / "schema" / "podcast",
    )


def _digest_envelope(to: str) -> DeliveryEnvelope:
    return DeliveryEnvelope.from_dict({
        "schema_version": "1",
        "id": "e2e-newinfra-1",
        "user_id": "u_000000000000000000000001",
        "channel": "email",
        "template": "your-week-digest.v1",
        "recipient": {"email": to, "email_verified": True},
        "consent_snapshot": {"digest_enabled": True, "cadence": "weekly",
                             "unsubscribe_ref": "e2e-demo-ref"},
        "payload": {"sections": [
            {"kind": "revisit", "items": [
                {"quote": "The bottleneck was never compute; it was our willingness to throw away a working model.",
                 "episode_slug": "acquired-nvidia", "episode_title": "NVIDIA: The Machine That Makes the Machine",
                 "t_ms": 3921000,
                 "graph_refs": [{"id": "person:jensen-huang", "kind": "person", "label": "Jensen Huang"},
                                {"id": "topic:scaling-laws", "kind": "topic", "label": "Scaling Laws"}],
                 "deep_link": "/player/acquired-nvidia?t=3921", "source": "user"}]},
            {"kind": "new_in_follows", "items": [
                {"episode_slug": "dwarkesh-ai-safety", "episode_title": "How AI Could Go Wrong",
                 "graph_refs": [{"id": "topic:ai-safety", "kind": "topic", "label": "AI Safety"}],
                 "deep_link": "/player/dwarkesh-ai-safety", "source": "auto"}]},
        ]},
    })


def main() -> int:
    to = sys.argv[1] if len(sys.argv) > 1 else "marko.dragoljevic@gmail.com"
    env = dotenv_values(ROOT / ".env")
    os.environ.update({k: v for k, v in env.items() if v is not None})
    cfg = DeliveryConfig.from_env()
    if not cfg.resend_api_key:
        print("RESEND_API_KEY not set in .env")
        return 2

    tenant = _podcast_tenant()
    renderer = Renderer.for_tenant(tenant)
    resend = ResendClient(cfg.resend_api_key, base_url=cfg.resend_base_url)
    transport = EmailTransport(renderer, resend, tenant.mail_from)
    envelope = _digest_envelope(to)

    print(f"\n--- sending your-week-digest.v1 to {to} via {tenant.mail_from} ---")
    outcome = transport.deliver(envelope)
    # mimic the worker's metric + event emission for the o11y proof
    SENT_TOTAL.labels(tenant="podcast", channel="email", template=envelope.template,
                      status=outcome.status.value).inc()
    from delivery.obs import emit_event
    line = emit_event("delivery", tenant="podcast", channel="email", template=envelope.template,
                      status=outcome.status.value, correlation_id=envelope.id,
                      envelope_id=envelope.id, user_id=envelope.user_id)

    print(f"\nRESULT status={outcome.status.value} resend_message_id={outcome.message_id}")
    print(f"correlation_id (X-Correlation-Id header sent to Resend) = {envelope.id}")
    print("\n--- o11y: metric ---")
    from prometheus_client import generate_latest, REGISTRY
    for ln in generate_latest(REGISTRY).decode().splitlines():
        if "delivery_sent_total" in ln and "podcast" in ln:
            print("  " + ln)
    print("\n--- o11y: JSONL log event (what Alloy ships to VictoriaLogs) ---")
    print("  " + (line or "<none>"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
