"""Resend HTTP API client — email last-mile. HTTPS 443 only (no SMTP → port-25 moot)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)


class ResendPermanentError(RuntimeError):
    """4xx that won't succeed on retry (bad address, rejected content) — bounce, no retry."""


class ResendTransientError(RuntimeError):
    """5xx / 429 / network — retry with backoff, then dead-letter."""


@dataclass(frozen=True)
class SendResult:
    message_id: str


class ResendClient:
    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = "https://api.resend.com",
        timeout_sec: float = 15.0,
        client: Optional[httpx.Client] = None,
    ) -> None:
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self._client = client or httpx.Client(
            base_url=base_url.rstrip("/"), headers=headers, timeout=timeout_sec
        )

    def send_email(
        self,
        *,
        sender: str,
        to: str,
        subject: str,
        html: str,
        idempotency_key: str,
        headers: Optional[dict[str, str]] = None,
    ) -> SendResult:
        body: dict[str, Any] = {"from": sender, "to": [to], "subject": subject, "html": html}
        if headers:
            body["headers"] = headers
        try:
            resp = self._client.post(
                "/emails", json=body, headers={"Idempotency-Key": idempotency_key}
            )
        except httpx.HTTPError as exc:
            raise ResendTransientError(str(exc)) from exc
        if resp.status_code >= 500:
            raise ResendTransientError(f"resend {resp.status_code}: {resp.text[:200]}")
        if resp.status_code >= 400:
            if resp.status_code == 429:
                raise ResendTransientError(f"resend 429: {resp.text[:200]}")
            raise ResendPermanentError(f"resend {resp.status_code}: {resp.text[:200]}")
        return SendResult(message_id=resp.json().get("id", ""))

    def get_email(self, message_id: str) -> dict[str, Any]:
        """Retrieve a sent email's current state, incl. ``last_event`` (delivered / bounced
        / complained). Resend has no pollable /events list — event state is read per
        message here (or pushed via webhooks, which we deliberately avoid to stay
        tailnet-only / egress-only)."""
        resp = self._client.get(f"/emails/{message_id}")
        resp.raise_for_status()
        email: dict[str, Any] = resp.json()
        return email

    def close(self) -> None:
        self._client.close()
