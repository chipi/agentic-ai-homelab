"""The app↔infra delivery seam as Pydantic-free dataclasses, aligned to the committed
contract (``schema/delivery-envelope.schema.json``, RFC-110 / ADR-145).

Kept dependency-light (stdlib dataclasses, no pydantic) so the worker image stays slim.
The authoritative validation is the JSON Schema itself, exercised in the contract test;
these classes are the ergonomic in-code view the worker renders from. The worker is a
tolerant CONSUMER: it ignores unknown fields so the app can extend the envelope
(additive) without breaking a deployed worker.

Key contract facts the worker depends on:
- ``consent_snapshot.unsubscribe_ref`` (NOT a token) — embedded in the unsubscribe link.
- digest ``payload.sections[].items[]`` and nudge ``payload.lead`` are ``digestItem``s that
  MUST carry ``graph_refs`` + a relative ``deep_link`` (the moat rule).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional


class Channel(str, Enum):
    EMAIL = "email"
    PUSH = "push"


class TerminalStatus(str, Enum):
    """Terminal outcome reported via ``POST /internal/outbox/{id}/status``.

    ``delivered`` is SOFT-terminal: an async bounce/complaint can supersede it later
    (status precedence — the app store must implement it)."""

    DELIVERED = "delivered"
    BOUNCED = "bounced"
    COMPLAINT = "complaint"
    SUPPRESSED = "suppressed"
    FAILED = "failed"
    DEAD_LETTERED = "dead_lettered"


@dataclass(frozen=True)
class Recipient:
    email: Optional[str] = None
    email_verified: bool = False
    push_subscription: Optional[dict[str, Any]] = None

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Recipient":
        return cls(
            email=d.get("email"),
            email_verified=bool(d.get("email_verified", False)),
            push_subscription=d.get("push_subscription"),
        )


@dataclass(frozen=True)
class ConsentSnapshot:
    digest_enabled: bool
    cadence: str
    unsubscribe_ref: str  # opaque, rotatable — the worker embeds it in the unsubscribe link

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ConsentSnapshot":
        return cls(
            digest_enabled=bool(d.get("digest_enabled", True)),
            cadence=str(d.get("cadence", "weekly")),
            unsubscribe_ref=str(d["unsubscribe_ref"]),
        )


@dataclass(frozen=True)
class DeliveryEnvelope:
    id: str
    user_id: str
    channel: Channel
    template: str
    recipient: Recipient
    consent_snapshot: ConsentSnapshot
    payload: dict[str, Any] = field(default_factory=dict)
    schema_version: str = "1"
    not_before: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    created_at: Optional[datetime] = None

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "DeliveryEnvelope":
        """Parse one envelope, ignoring unknown fields (forward-compat)."""
        return cls(
            id=str(d["id"]),
            user_id=str(d["user_id"]),
            channel=Channel(d["channel"]),
            template=str(d["template"]),
            recipient=Recipient.from_dict(d.get("recipient", {})),
            consent_snapshot=ConsentSnapshot.from_dict(d.get("consent_snapshot", {})),
            payload=d.get("payload", {}) or {},
            schema_version=str(d.get("schema_version", "1")),
            not_before=_parse_dt(d.get("not_before")),
            expires_at=_parse_dt(d.get("expires_at")),
            created_at=_parse_dt(d.get("created_at")),
        )

    def is_ready(self, *, now: Optional[datetime] = None) -> bool:
        if self.not_before is None:
            return True
        now = now or datetime.now(timezone.utc)
        return _aware(now) >= _aware(self.not_before)

    def is_expired(self, *, now: Optional[datetime] = None) -> bool:
        if self.expires_at is None:
            return False
        now = now or datetime.now(timezone.utc)
        return _aware(now) > _aware(self.expires_at)


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def _parse_dt(v: Any) -> Optional[datetime]:
    if not v:
        return None
    if isinstance(v, datetime):
        return v
    try:
        return datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except ValueError:
        return None
