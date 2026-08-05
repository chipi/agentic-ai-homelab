"""The stateless drain loop: poll pending → render → deliver → report terminal status.

One worker per (tenant, channel). No queue of its own (the app outbox is the SoT) — only a
small idempotency ledger + (email) a correlation index. "Pause all sends in <5 min" = stop
the process; nothing is lost and the bounded batch_limit drip-feeds on restart.

o11y: every metric/log/error/span carries ``tenant`` and the ``correlation_id`` (= the
envelope id, the end-to-end trace key that also rides to Resend as a header)."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from .config import DeliveryConfig
from .envelope import Channel, DeliveryEnvelope, TerminalStatus
from .ledger import SENDING, IdempotencyLedger
from .metrics import ATTEMPTS_TOTAL, PENDING, SEND_SECONDS, SENT_TOTAL
from .obs import capture_error, emit_event, span
from .outbox_client import OutboxClient
from .sent_index import SentIndex
from .transports import PermanentDeliveryError, Transport, TransientDeliveryError

logger = logging.getLogger(__name__)


@dataclass
class DrainStats:
    fetched: int = 0
    delivered: int = 0
    bounced: int = 0
    suppressed: int = 0
    dead_lettered: int = 0
    skipped: int = 0


class DeliveryWorker:
    def __init__(
        self,
        config: DeliveryConfig,
        outbox: OutboxClient,
        transport: Transport,
        channel: Channel,
        *,
        tenant: str,
        ledger: Optional[IdempotencyLedger] = None,
        sent_index: Optional[SentIndex] = None,
        sleep: Callable[[float], None] = time.sleep,
        liveness_path: Optional[str] = None,
    ) -> None:
        self._cfg = config
        self._outbox = outbox
        self._transport = transport
        self._channel = channel
        self._tenant = tenant
        self._ledger = ledger or IdempotencyLedger(
            f"{config.state_dir}/ledger-{tenant}-{channel.value}.jsonl"
        )
        self._sent_index = sent_index
        self._sleep = sleep
        self._liveness_path = liveness_path
        self._stopped = False

    def stop(self) -> None:
        self._stopped = True

    def _touch_liveness(self) -> None:
        if not self._liveness_path:
            return
        try:
            p = Path(self._liveness_path)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.touch()
        except Exception:  # noqa: BLE001
            logger.debug("liveness touch failed for %s", self._liveness_path, exc_info=True)

    def run_forever(self) -> None:
        logger.info(
            "delivery worker starting: tenant=%s channel=%s", self._tenant, self._channel.value
        )
        while not self._stopped:
            try:
                with span("delivery.drain", tenant=self._tenant, channel=self._channel.value):
                    self.drain_once()
            except Exception:  # noqa: BLE001 — one bad poll must not kill the worker
                logger.warning("drain_once failed; retrying next tick", exc_info=True)
            self._touch_liveness()
            if self._stopped:
                break
            self._sleep(self._cfg.poll_interval_sec)

    def drain_once(self) -> DrainStats:
        stats = DrainStats()
        envelopes = self._outbox.fetch_pending(self._channel.value, self._cfg.batch_limit)
        stats.fetched = len(envelopes)
        PENDING.labels(tenant=self._tenant, channel=self._channel.value).set(len(envelopes))
        for env in envelopes:
            self._process(env, stats)
            if self._stopped:
                break
        return stats

    def _process(self, env: DeliveryEnvelope, stats: DrainStats) -> None:
        if self._ledger.is_terminal(env.id):
            stats.skipped += 1
            return
        if env.is_expired():
            self._report(env, TerminalStatus.SUPPRESSED, "expired before delivery")
            stats.suppressed += 1
            return
        self._ledger.mark(env.id, SENDING)
        last_detail = ""
        for attempt in range(self._cfg.max_attempts):
            try:
                with span(
                    "delivery.send",
                    tenant=self._tenant,
                    channel=self._channel.value,
                    correlation_id=env.id,
                ):
                    started = time.monotonic()
                    outcome = self._transport.deliver(env)
                SEND_SECONDS.labels(tenant=self._tenant, channel=self._channel.value).observe(
                    time.monotonic() - started
                )
                ATTEMPTS_TOTAL.labels(
                    tenant=self._tenant, channel=self._channel.value, result="ok"
                ).inc()
                if outcome.message_id and self._sent_index is not None:
                    self._sent_index.record(outcome.message_id, self._tenant, env.id, env.user_id)
                self._report(env, outcome.status, outcome.detail)
                stats.delivered += 1
                return
            except PermanentDeliveryError as exc:
                ATTEMPTS_TOTAL.labels(
                    tenant=self._tenant, channel=self._channel.value, result="permanent"
                ).inc()
                self._report(env, exc.status, exc.detail)
                if exc.status == TerminalStatus.BOUNCED:
                    stats.bounced += 1
                else:
                    stats.dead_lettered += 1
                return
            except TransientDeliveryError as exc:
                ATTEMPTS_TOTAL.labels(
                    tenant=self._tenant, channel=self._channel.value, result="transient"
                ).inc()
                last_detail = str(exc)
                if attempt < self._cfg.max_attempts - 1:
                    self._sleep(self._backoff_for(attempt))
        self._dead_letter(env, last_detail)
        stats.dead_lettered += 1

    def _backoff_for(self, attempt_index: int) -> float:
        s = self._cfg.backoff_schedule_sec
        return s[min(attempt_index, len(s) - 1)] if s else 0.0

    def _report(self, env: DeliveryEnvelope, status: TerminalStatus, detail: Optional[str]) -> None:
        try:
            self._outbox.report_status(env.id, status, detail)
        except Exception:  # noqa: BLE001 — keep the ledger truthful even if write-back failed
            logger.warning(
                "status write-back failed for %s (%s)", env.id, status.value, exc_info=True
            )
        self._ledger.mark(env.id, status.value)
        SENT_TOTAL.labels(
            tenant=self._tenant,
            channel=self._channel.value,
            template=env.template,
            status=status.value,
        ).inc()
        emit_event(
            "delivery",
            tenant=self._tenant,
            channel=self._channel.value,
            template=env.template,
            status=status.value,
            correlation_id=env.id,
            envelope_id=env.id,
            user_id=env.user_id,
            detail=detail,
        )

    def _dead_letter(self, env: DeliveryEnvelope, detail: str) -> None:
        logger.error(
            "dead-lettering %s after %d attempts: %s", env.id, self._cfg.max_attempts, detail
        )
        self._report(env, TerminalStatus.DEAD_LETTERED, detail)
        emit_event(
            "delivery_deadletter",
            tenant=self._tenant,
            channel=self._channel.value,
            correlation_id=env.id,
            envelope_id=env.id,
            detail=detail,
        )
        capture_error(
            f"delivery dead-letter [{self._tenant}/{self._channel.value}] {env.id} "
            f"after {self._cfg.max_attempts} attempts: {detail}",
            tenant=self._tenant,
            correlation_id=env.id,
        )
