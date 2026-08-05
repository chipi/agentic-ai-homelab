"""Shared fakes for the worker tests. No network (D6)."""

from __future__ import annotations

from typing import Any, Optional

from delivery.envelope import DeliveryEnvelope, TerminalStatus
from delivery.transports import DeliveryOutcome


def make_envelope(**over: Any) -> DeliveryEnvelope:
    base: dict[str, Any] = {
        "schema_version": "1",
        "id": "e_1",
        "user_id": "u_000000000000000000000001",
        "channel": "email",
        "template": "your-week-digest.v1",
        "recipient": {"email": "a@b.com", "email_verified": True},
        "consent_snapshot": {
            "digest_enabled": True,
            "cadence": "weekly",
            "unsubscribe_ref": "ref_1",
        },
        "payload": {
            "sections": [
                {
                    "kind": "revisit",
                    "items": [
                        {
                            "episode_slug": "ep-1",
                            "episode_title": "Ep One",
                            "deep_link": "/player/ep-1",
                            "graph_refs": [{"id": "topic:ai", "kind": "topic", "label": "AI"}],
                        }
                    ],
                }
            ]
        },
    }
    base.update(over)
    return DeliveryEnvelope.from_dict(base)


class FakeOutbox:
    def __init__(self, pending: Optional[list[DeliveryEnvelope]] = None) -> None:
        self._pending = pending or []
        self.reported: list[tuple[str, TerminalStatus, Optional[str]]] = []
        self.fail_status_writes = False

    def fetch_pending(self, channel: str, limit: int) -> list[DeliveryEnvelope]:
        return list(self._pending[:limit])

    def report_status(
        self, envelope_id: str, status: TerminalStatus, detail: Optional[str] = None
    ) -> None:
        if self.fail_status_writes:
            raise RuntimeError("status write-back down")
        self.reported.append((envelope_id, status, detail))


class ScriptedTransport:
    def __init__(self, script: list[Any]) -> None:
        self._script = list(script)
        self.calls = 0

    def deliver(self, env: DeliveryEnvelope) -> DeliveryOutcome:
        self.calls += 1
        item = (
            self._script.pop(0)
            if self._script
            else DeliveryOutcome(status=TerminalStatus.DELIVERED)
        )
        if isinstance(item, Exception):
            raise item
        return item
