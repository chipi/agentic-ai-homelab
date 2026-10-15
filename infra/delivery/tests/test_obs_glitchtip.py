"""GlitchTip groups one delivery error as one issue (2026-10-15).

A dead-letter message names its envelope id ("... newep_513914963007_u_ced9... after 6
attempts: ..."), so each one would have become its own GlitchTip issue. capture_error now
takes a fingerprint, the dead-letter passes [dead-letter, tenant, channel], and anything else
(captured messages, logging-integration events) gets the message with ids, numbers and
quoted values replaced.
"""
from __future__ import annotations

from delivery import obs


def test_same_message_different_ids_same_fingerprint():
    a = obs._before_send({"logentry": {"formatted": "dead-letter newep_513914963007_u_ced9 after 6 attempts: HTTP 503"}}, None)
    b = obs._before_send({"logentry": {"formatted": "dead-letter newep_99aa11bb22cc_u_0f0f after 3 attempts: HTTP 502"}}, None)
    assert a["fingerprint"] == b["fingerprint"]


def test_different_messages_stay_apart():
    a = obs._before_send({"logentry": {"formatted": "outbox fetch failed: HTTP 500"}}, None)
    b = obs._before_send({"logentry": {"formatted": "apns token rejected: BadDeviceToken"}}, None)
    assert a["fingerprint"] != b["fingerprint"]


def test_explicit_fingerprint_is_kept():
    e = {"logentry": {"formatted": "x 1"}, "fingerprint": ["mine"]}
    assert obs._before_send(e, None)["fingerprint"] == ["mine"]


def test_capture_error_passes_the_fingerprint(monkeypatch):
    seen = {}

    class Scope:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def set_tag(self, k, v):
            seen.setdefault("tags", {})[k] = v

        @property
        def fingerprint(self):
            return seen.get("fingerprint")

        @fingerprint.setter
        def fingerprint(self, v):
            seen["fingerprint"] = v

    import sys
    import types

    fake = types.SimpleNamespace(new_scope=lambda: Scope(), capture_message=lambda m, level: seen.setdefault("msg", m))
    monkeypatch.setitem(sys.modules, "sentry_sdk", fake)
    obs.capture_error("dead-letter e1 after 6 attempts", fingerprint=["delivery-dead-letter", "podcast", "push"], tenant="podcast")
    assert seen["fingerprint"] == ["delivery-dead-letter", "podcast", "push"]
    assert seen["tags"] == {"tenant": "podcast"}
