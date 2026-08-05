"""Cross-tenant bounce/complaint poller — reads each sent message's Resend status.

Resend has NO pollable /events list (that endpoint always returns empty; events are only
pushed via webhooks). To stay tailnet-only / egress-only we instead poll ``GET
/emails/{id}`` per sent message and read ``last_event``. On bounced/complained we report
the terminal status back to that message's tenant outbox (routing via the shared, tenant-
tagged sent-index), then mark the message resolved so it is not polled again. A delivered
message with no bounce is resolved once older than the bounce-window TTL, bounding the work."""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Mapping, Optional

from .config import DeliveryConfig
from .envelope import TerminalStatus
from .metrics import POLL_CURSOR_LAG, SENT_TOTAL
from .obs import emit_event
from .outbox_client import OutboxClient
from .resend_client import ResendClient
from .sent_index import SentIndex

logger = logging.getLogger(__name__)

# last_event values that mean "suppress this recipient".
_SUPPRESS = {"bounced": TerminalStatus.BOUNCED, "complained": TerminalStatus.COMPLAINT}
# A delivered message with no bounce after this long won't bounce — stop polling it.
_BOUNCE_WINDOW_SEC = 6 * 3600


class _Resolved:
    """Persisted set of message_ids we're done polling (bounced/complained/aged-out)."""

    def __init__(self, path: Path | str) -> None:
        self._path = Path(path)
        self._ids: set[str] = set()
        if self._path.exists():
            try:
                self._ids = {ln.strip() for ln in self._path.read_text().splitlines() if ln.strip()}
            except Exception:  # noqa: BLE001
                self._ids = set()

    def __contains__(self, mid: str) -> bool:
        return mid in self._ids

    def add(self, mid: str) -> None:
        self._ids.add(mid)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("a", encoding="utf-8") as fh:
            fh.write(mid + "\n")


class EventsPoller:
    def __init__(
        self,
        config: DeliveryConfig,
        resend: ResendClient,
        outboxes: Mapping[str, OutboxClient],
        sent_index: SentIndex,
        *,
        resolved: Optional[_Resolved] = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._cfg = config
        self._resend = resend
        self._outboxes = dict(outboxes)  # tenant -> OutboxClient
        self._sent_index = sent_index
        self._resolved = resolved or _Resolved(f"{config.state_dir}/resend-resolved.txt")
        self._sleep = sleep
        self._clock = clock
        self._last_advance = clock()
        self._stopped = False

    def stop(self) -> None:
        self._stopped = True

    def run_forever(self) -> None:
        logger.info("resend status poller starting (tenants: %s)", ", ".join(self._outboxes))
        while not self._stopped:
            try:
                self.poll_once()
            except Exception:  # noqa: BLE001
                logger.warning("status poll failed; retrying next tick", exc_info=True)
            age = self._clock() - self._last_advance
            for tenant in self._outboxes:
                POLL_CURSOR_LAG.labels(tenant=tenant).set(age)
            if self._stopped:
                break
            self._sleep(self._cfg.poll_interval_sec)

    def poll_once(self) -> int:
        """Poll each un-resolved sent message's Resend status; suppress bounces/complaints.
        Returns the number of suppression write-backs made this cycle."""
        suppressed = 0
        for message_id, ref in self._sent_index.items():
            if self._stopped:
                break
            if not message_id or message_id in self._resolved:
                continue
            try:
                email = self._resend.get_email(message_id)
            except Exception:  # noqa: BLE001 — transient; retry next cycle
                logger.debug("get_email failed for %s", message_id, exc_info=True)
                continue
            last_event = str(email.get("last_event", "")).lower()
            status = _SUPPRESS.get(last_event)
            if status is not None:
                if self._suppress(ref, status, message_id):
                    suppressed += 1
                    self._resolved.add(message_id)
                # write-back failed → leave un-resolved, retry next cycle
            elif self._aged_out(email):
                self._resolved.add(message_id)  # delivered, no bounce coming — stop polling
        self._last_advance = self._clock()
        return suppressed

    def _aged_out(self, email: dict) -> bool:
        created = email.get("created_at")
        if not created:
            return False
        try:
            dt = datetime.fromisoformat(str(created).replace("Z", "+00:00").replace(" ", "T", 1))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return (datetime.now(timezone.utc) - dt).total_seconds() > _BOUNCE_WINDOW_SEC
        except Exception:  # noqa: BLE001
            return False

    def _suppress(self, ref, status: TerminalStatus, message_id: str) -> bool:
        outbox = self._outboxes.get(ref.tenant)
        if outbox is None:
            logger.warning("suppression for unknown tenant=%s (message %s)", ref.tenant, message_id)
            return False
        try:
            outbox.report_status(ref.envelope_id, status, detail=f"resend:{status.value}")
        except Exception:  # noqa: BLE001 — retried next cycle (not marked resolved on failure)
            logger.warning(
                "suppression write-back failed for %s/%s",
                ref.tenant,
                ref.envelope_id,
                exc_info=True,
            )
            return False
        SENT_TOTAL.labels(
            tenant=ref.tenant, channel="email", template="_event", status=status.value
        ).inc()
        emit_event(
            "delivery_suppression",
            tenant=ref.tenant,
            channel="email",
            status=status.value,
            correlation_id=ref.envelope_id,
            envelope_id=ref.envelope_id,
            user_id=ref.user_id,
            message_id=message_id,
        )
        return True
