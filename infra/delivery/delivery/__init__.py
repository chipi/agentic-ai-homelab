"""Standalone outbound delivery worker for the closelistening player (#1412 / ADR-145).

Pure consumer of the app↔infra delivery seam: drains the app outbox → renders (Jinja,
extractive, D6) → delivers (Resend HTTP API for email, self-hosted Web Push for push) →
reports terminal status. Idempotent on envelope id; retry+backoff; dead-letter after N.
Homelab, tailnet-only, 443 egress. No app-repo dependency; the seam contract is vendored
under ``schema/`` (see schema/SYNC.md)."""

from __future__ import annotations

from .envelope import (
    Channel,
    ConsentSnapshot,
    DeliveryEnvelope,
    Recipient,
    TerminalStatus,
)

__all__ = ["Channel", "ConsentSnapshot", "DeliveryEnvelope", "Recipient", "TerminalStatus"]
