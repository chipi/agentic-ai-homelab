"""Multi-tenant fleet: the registry drives per-tenant workers with isolated identity, and
the cross-tenant events poller routes suppression back to the right tenant's outbox."""

from __future__ import annotations

from pathlib import Path

import pytest

from delivery.config import DeliveryConfig
from delivery.envelope import Channel, TerminalStatus
from delivery.fleet import build_channel_workers, build_events_poller
from delivery.sent_index import SentIndex
from delivery.tenant import load_registry

_ROOT = Path(__file__).resolve().parent.parent

_TWO_TENANTS = """
tenants:
  podcast:
    outbox_base_url: http://podcast:8092
    internal_token_env: PODCAST_TOK
    vapid_private_key_env: PODCAST_VAPID
    mail_from: "Close Listening <digest@mail.closelistening.app>"
    app_origin: https://closelistening.app
    unsubscribe_path: /api/app/comms/unsubscribe
    vapid_subject: mailto:info@closelistening.app
  orrery:
    outbox_base_url: http://orrery:9200
    internal_token_env: ORRERY_TOK
    vapid_private_key_env: ORRERY_VAPID
    mail_from: "Orrery <updates@mail.orrerylearn.com>"
    app_origin: https://orrerylearn.com
    unsubscribe_path: /api/comms/unsubscribe
    vapid_subject: mailto:hello@orrerylearn.com
"""


@pytest.fixture
def two_tenant_registry(tmp_path):
    # per-tenant template dirs must exist for the renderer to construct
    for t in ("podcast", "orrery"):
        (tmp_path / "delivery" / "templates" / t / "email").mkdir(parents=True)
        (tmp_path / "delivery" / "templates" / t / "push").mkdir(parents=True)
    reg = tmp_path / "tenants.yaml"
    reg.write_text(_TWO_TENANTS)
    env = {
        "PODCAST_TOK": "ptok",
        "PODCAST_VAPID": "pvapid",
        "ORRERY_TOK": "otok",
        "ORRERY_VAPID": "ovapid",
    }
    return load_registry(str(reg), env=env, root=tmp_path)


def test_registry_loads_both_tenants(two_tenant_registry):
    assert set(two_tenant_registry) == {"podcast", "orrery"}
    assert two_tenant_registry["orrery"].mail_from.startswith("Orrery")
    assert two_tenant_registry["podcast"].app_origin == "https://closelistening.app"
    assert two_tenant_registry["orrery"].internal_token == "otok"  # resolved per-tenant secret


def test_email_fleet_one_worker_per_tenant(two_tenant_registry, tmp_path):
    cfg = DeliveryConfig(state_dir=str(tmp_path), resend_api_key="re_x")
    workers = build_channel_workers(cfg, two_tenant_registry, Channel.EMAIL)
    assert {w._tenant for w in workers} == {"podcast", "orrery"}


def test_tenant_missing_secret_is_skipped_not_fatal(tmp_path):
    for t in ("podcast", "orrery"):
        (tmp_path / "delivery" / "templates" / t / "email").mkdir(parents=True)
    reg = tmp_path / "tenants.yaml"
    reg.write_text(_TWO_TENANTS)
    # orrery's token env is unset → orrery skipped, podcast still runs
    tenants = load_registry(str(reg), env={"PODCAST_TOK": "ptok"}, root=tmp_path)
    cfg = DeliveryConfig(state_dir=str(tmp_path), resend_api_key="re_x")
    workers = build_channel_workers(cfg, tenants, Channel.EMAIL)
    assert {w._tenant for w in workers} == {"podcast"}


def test_events_poller_routes_suppression_by_tenant(two_tenant_registry, tmp_path):
    # Record two sends (different tenants) into the shared index; polling each message's
    # Resend status (bounced/complained) must write back to the correct tenant's outbox.
    idx = SentIndex(f"{tmp_path}/sent-index.jsonl")
    idx.record("m_pod", "podcast", "e_pod", "u_1")
    idx.record("m_orr", "orrery", "e_orr", "u_2")

    cfg = DeliveryConfig(state_dir=str(tmp_path), resend_api_key="re_x")
    poller = build_events_poller(cfg, two_tenant_registry)

    # Fake Resend: each message's last_event.
    class FakeResend:
        _events = {"m_pod": "bounced", "m_orr": "complained"}

        def get_email(self, mid):
            return {
                "id": mid,
                "last_event": self._events[mid],
                "created_at": "2026-08-05T10:00:00Z",
            }

    poller._resend = FakeResend()

    calls = {}

    class FakeOutbox:
        def __init__(self, name):
            self.name = name

        def report_status(self, envelope_id, status, detail=None):
            calls[self.name] = (envelope_id, status)

    poller._outboxes = {"podcast": FakeOutbox("podcast"), "orrery": FakeOutbox("orrery")}

    n = poller.poll_once()
    assert n == 2
    assert calls["podcast"] == ("e_pod", TerminalStatus.BOUNCED)
    assert calls["orrery"] == ("e_orr", TerminalStatus.COMPLAINT)


# ---------------------------------------------------------------------------
# _aged_out TTL-expiry path
# ---------------------------------------------------------------------------

from datetime import datetime, timedelta, timezone  # noqa: E402

from delivery.events_poller import EventsPoller, _Resolved  # noqa: E402
from delivery.sent_index import SentRef  # noqa: E402


class _FakeSentIndex:
    """Minimal stand-in — poll_once only needs items()."""

    def __init__(self, entries: dict) -> None:
        self._entries = entries

    def items(self):
        return list(self._entries.items())


def _make_poller(tmp_path, entries: dict):
    """Build an EventsPoller with no real outboxes/resend."""
    cfg = DeliveryConfig(state_dir=str(tmp_path), resend_api_key="re_x")
    resolved = _Resolved(tmp_path / "resolved.txt")
    poller = EventsPoller(
        config=cfg,
        resend=None,  # not called in aged-out path (no suppress branch reached)
        outboxes={},
        sent_index=_FakeSentIndex(entries),
        resolved=resolved,
        sleep=lambda _: None,
    )
    return poller, resolved


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def test_aged_out_past_ttl_is_resolved(tmp_path):
    # An email created 7 hours ago (past the 6-hour bounce window) must be
    # added to the resolved set so it is never polled again.
    # _aged_out compares against datetime.now(utc) directly, so use real wall clock.
    created = datetime.now(timezone.utc) - timedelta(hours=7)
    ref = SentRef(tenant="podcast", envelope_id="e_1", user_id="u_1")

    class _Resend:
        def get_email(self, mid):
            return {"id": mid, "last_event": "delivered", "created_at": _iso(created)}

    poller, resolved = _make_poller(tmp_path, {"m_1": ref})
    poller._resend = _Resend()

    n = poller.poll_once()
    assert n == 0  # no suppression write-back; aged-out path doesn't count toward n
    assert "m_1" in resolved


def test_not_aged_out_within_ttl_is_retained(tmp_path):
    # An email created 1 hour ago (well within 6-hour window) must NOT be resolved.
    created = datetime.now(timezone.utc) - timedelta(hours=1)
    ref = SentRef(tenant="podcast", envelope_id="e_2", user_id="u_2")

    class _Resend:
        def get_email(self, mid):
            return {"id": mid, "last_event": "delivered", "created_at": _iso(created)}

    poller, resolved = _make_poller(tmp_path, {"m_2": ref})
    poller._resend = _Resend()

    poller.poll_once()
    assert "m_2" not in resolved


def test_missing_created_at_does_not_resolve(tmp_path):
    # The dangerous edge: a missing/null created_at must NOT silently age out the
    # message. _aged_out returns False → the message stays unresolved (still polled).
    # A bug here (returning True on missing key) would resolve messages prematurely,
    # causing the resolved set to grow unbounded for messages lacking the field.
    ref = SentRef(tenant="podcast", envelope_id="e_3", user_id="u_3")

    class _Resend:
        def get_email(self, mid):
            # created_at absent entirely
            return {"id": mid, "last_event": "delivered"}

    poller, resolved = _make_poller(tmp_path, {"m_3": ref})
    poller._resend = _Resend()

    poller.poll_once()
    assert "m_3" not in resolved


def test_timezone_naive_created_at_treated_as_utc(tmp_path):
    # A tz-naive ISO string (no Z, no +HH:MM) must be treated as UTC, not silently
    # skip expiry. An email created 8 hours ago with a tz-naive stamp should still age out.
    created = datetime.now(timezone.utc) - timedelta(hours=8)
    # tz-naive: no trailing Z or offset
    naive_iso = created.strftime("%Y-%m-%dT%H:%M:%S")
    ref = SentRef(tenant="podcast", envelope_id="e_4", user_id="u_4")

    class _Resend:
        def get_email(self, mid):
            return {"id": mid, "last_event": "delivered", "created_at": naive_iso}

    poller, resolved = _make_poller(tmp_path, {"m_4": ref})
    poller._resend = _Resend()

    poller.poll_once()
    assert "m_4" in resolved
