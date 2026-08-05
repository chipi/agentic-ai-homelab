"""Client for the app-owned outbox seam (§2 of #1412), over the tailnet.

    GET  /internal/outbox/pending?channel=&limit=  -> {envelopes:[...]}
    POST /internal/outbox/{id}/status              <- {status, detail?}

Shared token (INTERNAL_OUTBOX_TOKEN) in the ``X-Internal-Token`` header (seam v1.1 amendment
6). Status POST is safe to retry — the app treats
a repeated terminal status as a no-op (status precedence)."""

from __future__ import annotations

import logging
from typing import Optional

import httpx

from .envelope import DeliveryEnvelope, TerminalStatus

logger = logging.getLogger(__name__)


class OutboxClient:
    def __init__(
        self,
        base_url: str,
        token: str,
        *,
        timeout_sec: float = 15.0,
        client: Optional[httpx.Client] = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        # The app gates /internal/outbox/* on the X-Internal-Token header (seam v1.1
        # amendment 6), NOT Authorization: Bearer.
        headers = {"X-Internal-Token": token} if token else {}
        self._client = client or httpx.Client(
            base_url=self._base_url, headers=headers, timeout=timeout_sec
        )

    def fetch_pending(self, channel: str, limit: int) -> list[DeliveryEnvelope]:
        resp = self._client.get(
            "/internal/outbox/pending", params={"channel": channel, "limit": limit}
        )
        resp.raise_for_status()
        out: list[DeliveryEnvelope] = []
        for item in resp.json().get("envelopes", []):
            try:
                out.append(DeliveryEnvelope.from_dict(item))
            except Exception:  # noqa: BLE001 — one bad envelope must not stall the batch
                logger.warning("dropping malformed envelope %s", item.get("id"), exc_info=True)
        return out

    def report_status(
        self, envelope_id: str, status: TerminalStatus, detail: Optional[str] = None
    ) -> None:
        body: dict[str, str] = {"status": status.value}
        if detail:
            body["detail"] = detail
        resp = self._client.post(f"/internal/outbox/{envelope_id}/status", json=body)
        resp.raise_for_status()

    def close(self) -> None:
        self._client.close()
