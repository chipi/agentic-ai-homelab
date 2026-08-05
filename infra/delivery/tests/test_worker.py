"""Drain loop branches: delivered, skip-terminal, expired, bounce, retry, dead-letter,
status-write-failure invariant, correlation record."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from delivery.config import DeliveryConfig
from delivery.envelope import Channel, TerminalStatus
from delivery.ledger import SENDING, IdempotencyLedger
from delivery.sent_index import SentIndex
from delivery.transports import DeliveryOutcome, PermanentDeliveryError, TransientDeliveryError
from delivery.worker import DeliveryWorker

from conftest import FakeOutbox, ScriptedTransport, make_envelope


def _worker(tmp_path, outbox, transport, **over):
    cfg = DeliveryConfig(
        state_dir=str(tmp_path), max_attempts=3, backoff_schedule_sec=(0, 0, 0), **over
    )
    return DeliveryWorker(
        cfg,
        outbox,
        transport,
        Channel.EMAIL,
        tenant="podcast",
        ledger=IdempotencyLedger(tmp_path / "l.jsonl"),
        sent_index=SentIndex(tmp_path / "s.jsonl"),
        sleep=lambda _s: None,
    )


def test_delivered(tmp_path):
    outbox = FakeOutbox([make_envelope(id="e_ok")])
    w = _worker(
        tmp_path,
        outbox,
        ScriptedTransport([DeliveryOutcome(status=TerminalStatus.DELIVERED, message_id="m1")]),
    )
    stats = w.drain_once()
    assert stats.delivered == 1
    assert outbox.reported == [("e_ok", TerminalStatus.DELIVERED, None)]


def test_correlation_recorded(tmp_path):
    outbox = FakeOutbox([make_envelope(id="e_ok")])
    idx = SentIndex(tmp_path / "s.jsonl")
    cfg = DeliveryConfig(state_dir=str(tmp_path), backoff_schedule_sec=(0,))
    w = DeliveryWorker(
        cfg,
        outbox,
        ScriptedTransport([DeliveryOutcome(status=TerminalStatus.DELIVERED, message_id="m1")]),
        Channel.EMAIL,
        tenant="podcast",
        ledger=IdempotencyLedger(tmp_path / "l.jsonl"),
        sent_index=idx,
        sleep=lambda _s: None,
    )
    w.drain_once()
    assert idx.resolve("m1") == ("podcast", "e_ok", "u_000000000000000000000001")


def test_skip_terminal(tmp_path):
    outbox = FakeOutbox([make_envelope(id="e_done")])
    t = ScriptedTransport([])
    w = _worker(tmp_path, outbox, t)
    w._ledger.mark("e_done", TerminalStatus.DELIVERED.value)
    assert w.drain_once().skipped == 1
    assert t.calls == 0


def test_expired_suppressed(tmp_path):
    past = datetime.now(timezone.utc) - timedelta(days=2)
    outbox = FakeOutbox([make_envelope(id="e_old", expires_at=past.isoformat())])
    t = ScriptedTransport([])
    stats = _worker(tmp_path, outbox, t).drain_once()
    assert stats.suppressed == 1 and t.calls == 0
    assert outbox.reported[0][:2] == ("e_old", TerminalStatus.SUPPRESSED)


def test_permanent_bounce(tmp_path):
    outbox = FakeOutbox([make_envelope(id="e_b")])
    t = ScriptedTransport([PermanentDeliveryError(TerminalStatus.BOUNCED, "bad")])
    stats = _worker(tmp_path, outbox, t).drain_once()
    assert stats.bounced == 1 and t.calls == 1


def test_transient_then_success(tmp_path):
    outbox = FakeOutbox([make_envelope(id="e_r")])
    t = ScriptedTransport(
        [TransientDeliveryError("blip"), DeliveryOutcome(status=TerminalStatus.DELIVERED)]
    )
    assert _worker(tmp_path, outbox, t).drain_once().delivered == 1
    assert t.calls == 2


def test_dead_letter(tmp_path):
    outbox = FakeOutbox([make_envelope(id="e_dl")])
    t = ScriptedTransport([TransientDeliveryError("down")] * 5)
    stats = _worker(tmp_path, outbox, t).drain_once()
    assert stats.dead_lettered == 1 and t.calls == 3
    assert outbox.reported[0][:2] == ("e_dl", TerminalStatus.DEAD_LETTERED)


def test_status_write_failure_keeps_ledger_terminal(tmp_path):
    outbox = FakeOutbox([make_envelope(id="e_x")])
    outbox.fail_status_writes = True
    w = _worker(
        tmp_path,
        outbox,
        ScriptedTransport([DeliveryOutcome(status=TerminalStatus.DELIVERED, message_id="m3")]),
    )
    w.drain_once()
    assert w._ledger.is_terminal("e_x") is True


def test_ledger_marks_sending_before_send(tmp_path):
    outbox = FakeOutbox([make_envelope(id="e_s")])
    seen = {}

    class Peek:
        calls = 0

        def deliver(self, env):
            Peek.calls += 1
            seen["status"] = w._ledger.status_of("e_s")
            return DeliveryOutcome(status=TerminalStatus.DELIVERED)

    w = _worker(tmp_path, outbox, Peek())
    w.drain_once()
    assert seen["status"] == SENDING
