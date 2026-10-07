"""End-to-end real send through the NEW multi-tenant delivery code.

Builds the podcast tenant, renders a real your-week-digest via the podcast template dir,
sends a LIVE email through Resend to the recipient on argv, and reports the o11y that fired:
the delivery_sent_total metric + the canonical JSONL event (tenant + correlation_id).

It is a TEST, and says so: the subject starts with "[E2E test]" (operator 2026-10-07 — a test
email that looks real was mistaken for a broken digest). And it links only to things that EXIST in
production — the episodes and topics are read from prod's public discover / trending endpoints at
send time — so every link in it opens a real page. Hard-coded sample slugs did not: "Play from"
opened "Episode not found".

    python e2e/e2e_send.py marko.dragoljevic@gmail.com      # from infra/delivery
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
import urllib.request
from dataclasses import replace
from pathlib import Path

from delivery.config import DeliveryConfig
from delivery.envelope import Channel, DeliveryEnvelope
from delivery.metrics import SENT_TOTAL
from delivery.render import RenderedEmail, Renderer
from delivery.resend_client import ResendClient
from delivery.tenant import TenantConfig
from delivery.transports import EmailTransport

# infra/delivery — where `delivery/templates` and `schema/` live (this file sits in e2e/).
ROOT = Path(__file__).resolve().parents[1]
APP_ORIGIN = "https://closelistening.app"
SUBJECT_PREFIX = "[E2E test] "
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")


def _podcast_tenant() -> TenantConfig:
    return TenantConfig(
        name="podcast",
        outbox_base_url="http://unused",
        internal_token="x",
        mail_from="Close Listening <digest@mail.closelistening.app>",
        app_origin=APP_ORIGIN,
        unsubscribe_path="/api/app/comms/unsubscribe",
        vapid_private_key="",
        vapid_subject="mailto:info@closelistening.app",
        template_dir=ROOT / "delivery" / "templates" / "podcast",
        schema_dir=ROOT / "schema" / "podcast",
    )


def _read_env_file(path: Path) -> dict[str, str]:
    """KEY=value lines from the service's .env. python-dotenv is not a dependency of this
    package, so the script failed to import wherever nobody had installed it by hand."""
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.removeprefix("export ").partition("=")
        out[key.strip()] = value.strip().strip('"').strip("'")
    return out


class E2ERenderer(Renderer):
    """The real renderer, with the subject marked as a test."""

    def render_email(self, env: DeliveryEnvelope) -> RenderedEmail:
        rendered = super().render_email(env)
        return replace(rendered, subject=SUBJECT_PREFIX + rendered.subject)


def _get_json(path: str) -> dict:
    # A named agent: the edge refuses Python's default one (measured: 403 to urllib, 200 to curl).
    req = urllib.request.Request(
        f"{APP_ORIGIN}{path}", headers={"User-Agent": "close-listening-e2e/1"}
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.load(resp)


def _real_material() -> tuple[list[dict], list[dict]]:
    """Two real episodes (with transcripts) and two real topics, read from production now."""
    episodes = [
        e for e in _get_json("/api/app/discover").get("items", [])
        if e.get("slug") and e.get("title") and e.get("has_transcript")
    ]
    topics = [
        t for t in _get_json("/api/app/corpus/trending-topics").get("topics", [])
        if t.get("topic_id") and t.get("topic_label")
    ]
    if len(episodes) < 2 or len(topics) < 2:
        raise SystemExit(
            f"prod returned {len(episodes)} episodes / {len(topics)} topics — need 2 of each"
        )
    return episodes[:2], topics[:2]


def _digest_envelope(to: str) -> DeliveryEnvelope:
    (revisit, new), (t1, t2) = _real_material()
    chip = lambda t: {"id": t["topic_id"], "kind": "topic", "label": t["topic_label"]}  # noqa: E731
    play_at_s = 60  # inside any episode: durations are not always known
    return DeliveryEnvelope.from_dict({
        "schema_version": "1",
        # A fresh id per run: it is Resend's idempotency key, and a fixed one made every send after
        # the first within 24 h fail with 409 (2026-10-07).
        "id": f"e2e-{int(time.time())}",
        "user_id": "u_000000000000000000000001",
        "channel": "email",
        "template": "your-week-digest.v1",
        "recipient": {"email": to, "email_verified": True},
        "consent_snapshot": {"digest_enabled": True, "cadence": "weekly",
                             "unsubscribe_ref": "e2e-demo-ref"},
        "payload": {"sections": [
            {"kind": "revisit", "items": [
                {"quote": "E2E test highlight — tapping Play from should start this episode at 1:00.",
                 "episode_slug": revisit["slug"], "episode_title": revisit["title"],
                 "podcast_title": revisit.get("podcast_title"),
                 "artwork_url": revisit.get("artwork_url"),
                 "t_ms": play_at_s * 1000,
                 "graph_refs": [chip(t1), chip(t2)],
                 "deep_link": f"/episode/{revisit['slug']}?t={play_at_s}", "source": "user"}]},
            {"kind": "new_in_follows", "items": [
                {"episode_slug": new["slug"], "episode_title": new["title"],
                 "podcast_title": new.get("podcast_title"),
                 "artwork_url": new.get("artwork_url"),
                 "graph_refs": [chip(t2)],
                 "deep_link": f"/episode/{new['slug']}", "source": "auto"}]},
        ]},
    })


def main() -> int:
    to = sys.argv[1] if len(sys.argv) > 1 else "marko.dragoljevic@gmail.com"
    os.environ.update(_read_env_file(ROOT / ".env"))
    cfg = DeliveryConfig.from_env()
    if not cfg.resend_api_key:
        print("RESEND_API_KEY not set in .env")
        return 2

    tenant = _podcast_tenant()
    renderer = E2ERenderer.for_tenant(tenant)
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
