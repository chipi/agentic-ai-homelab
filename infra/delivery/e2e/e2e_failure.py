"""Failure-scenario o11y check: force a DEAD-LETTER and confirm every surface captures it.

Points the email transport at an unreachable Resend endpoint so every attempt fails
transiently; after max_attempts the worker dead-letters → metric + JSONL event +
GlitchTip error (tagged tenant + correlation_id). Prints what fired; GlitchTip receipt is
verified separately on the host.
"""

from __future__ import annotations

import logging
import os
import sys
import time
from pathlib import Path

from dotenv import dotenv_values

from delivery.config import DeliveryConfig
from delivery.envelope import Channel, DeliveryEnvelope, TerminalStatus
from delivery.ledger import IdempotencyLedger
from delivery.metrics import SENT_TOTAL
from delivery.obs import init_error_reporting
from delivery.render import Renderer
from delivery.resend_client import ResendClient
from delivery.tenant import TenantConfig
from delivery.transports import EmailTransport
from delivery.worker import DeliveryWorker

ROOT = Path(__file__).resolve().parent
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")


class OneEnvelopeOutbox:
    def __init__(self, env):
        self._env = env
        self.reported = []

    def fetch_pending(self, channel, limit):
        return [self._env]

    def report_status(self, envelope_id, status, detail=None):
        self.reported.append((envelope_id, status.value, detail))


def _tenant() -> TenantConfig:
    return TenantConfig("podcast", "http://unused", "x",
                        "Close Listening <digest@mail.closelistening.app>",
                        "https://closelistening.app", "/api/app/comms/unsubscribe", "",
                        "mailto:info@closelistening.app",
                        ROOT / "delivery" / "templates" / "podcast", ROOT / "schema" / "podcast")


def main() -> int:
    env = dotenv_values(ROOT / ".env")
    os.environ.update({k: v for k, v in env.items() if v is not None})
    print("GlitchTip error reporting:", "ON" if init_error_reporting() else "OFF (no DSN)")

    envelope = DeliveryEnvelope.from_dict({
        "schema_version": "1", "id": "e2e-deadletter-1", "user_id": "u_000000000000000000000001",
        "channel": "email", "template": "your-week-digest.v1",
        "recipient": {"email": "nobody@example.com", "email_verified": True},
        "consent_snapshot": {"digest_enabled": True, "cadence": "weekly", "unsubscribe_ref": "r"},
        "payload": {"sections": [{"kind": "revisit", "items": [
            {"episode_slug": "x", "episode_title": "X", "deep_link": "/player/x",
             "graph_refs": [{"id": "topic:ai", "kind": "topic", "label": "AI"}]}]}]},
    })
    outbox = OneEnvelopeOutbox(envelope)
    # Unreachable Resend endpoint → every attempt is a transient connection failure.
    resend = ResendClient("re_x", base_url="http://127.0.0.1:9", timeout_sec=2.0)
    transport = EmailTransport(Renderer.for_tenant(_tenant()), resend,
                               "Close Listening <digest@mail.closelistening.app>")
    cfg = DeliveryConfig(state_dir="/tmp/e2e-delivery-state", max_attempts=2, backoff_schedule_sec=(0,))
    worker = DeliveryWorker(cfg, outbox, transport, Channel.EMAIL, tenant="podcast",
                            ledger=IdempotencyLedger("/tmp/e2e-delivery-state/l.jsonl"),
                            sleep=lambda _s: None)

    print("\n--- draining (expect dead-letter after 2 failed attempts) ---")
    stats = worker.drain_once()
    print(f"stats: dead_lettered={stats.dead_lettered}")
    print(f"status write-back: {outbox.reported}")

    print("\n--- o11y: dead-letter metric ---")
    from prometheus_client import generate_latest, REGISTRY
    for ln in generate_latest(REGISTRY).decode().splitlines():
        if "delivery_sent_total" in ln and "dead_lettered" in ln:
            print("  " + ln)

    # Flush GlitchTip so the error is delivered before we exit.
    try:
        import sentry_sdk
        sentry_sdk.flush(timeout=5)
        print("\n--- GlitchTip: dead-letter error flushed to project 'delivery' (id 13) ---")
    except Exception as e:  # noqa: BLE001
        print("sentry flush note:", e)
    time.sleep(1)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
