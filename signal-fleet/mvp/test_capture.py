"""Offline checks for per-decision probe capture (capture.py). No LLM, no network.

  SF_OBSERV_DISABLED=1 python3 test_capture.py     # non-zero on failure
"""
import json
import os
import stat
import tempfile
import unittest
from unittest import mock

os.environ.setdefault("SF_OBSERV_DISABLED", "1")

import capture
import config
import probes
import triage

SIGNAL = {"fingerprint": "glitchtip:ORRERY-PROD-9", "occurrence_id": "glitchtip:ORRERY-PROD-9@2026-10-20T10:00:00Z",
          "source": "glitchtip", "alertname": "TypeError: x is undefined",
          "labels": {"project": "orrery-prod"}, "summary": "TypeError (count=3)", "issue_id": 42,
          "raw": {"count": 3, "status": "unresolved"}}
LONG = "x" * 2500   # longer than triage._trim's 1800, so "shown" differs from the raw answer


def _disp():
    trace = [{"probe": "event_detail", "args": {}, "result": {"culprit": "a.js"}},
             {"probe": "service_logs", "args": {"window": "2h"}, "result": LONG}]
    d = {"disposition": "file", "reason": "real bug", "certainty": "high",
         "file": {"work_type": "bug"}}
    with mock.patch.object(triage.observ, "finalize"):
        return triage._finish(SIGNAL, d, trace, "intent", {"prompt_tokens": 1, "completion_tokens": 1}, 0)


class Capture(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.calls = []

        def fake_probe(signal, name, args, table=None):
            self.calls.append((name, args))
            return f"<eager {name}>"
        self.patches = [mock.patch.object(config, "CAPTURE_DIR", self.dir),
                        mock.patch.object(probes, "run_probe", fake_probe)]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()

    def test_off_by_default_writes_nothing(self):
        with mock.patch.object(config, "CAPTURE_PROBES", False):
            self.assertIsNone(capture.record(SIGNAL, _disp()))
        self.assertEqual(os.listdir(self.dir), [])
        self.assertEqual(self.calls, [])

    def test_finish_records_the_trace_with_the_text_shown(self):
        t = _disp()["_probe_trace"]
        self.assertEqual([x["probe"] for x in t], ["event_detail", "service_logs"])
        self.assertEqual(t[1]["result"], LONG)
        self.assertEqual(t[1]["shown"], triage._trim(LONG))
        self.assertIn("[truncated", t[1]["shown"])

    def test_on_writes_a_replayable_private_file(self):
        with mock.patch.object(config, "CAPTURE_PROBES", True), mock.patch.object(config, "CAPTURE_EAGER", True):
            path = capture.record(SIGNAL, _disp())
        self.assertTrue(path and os.path.exists(path))
        self.assertEqual(stat.S_IMODE(os.stat(path).st_mode), 0o600)
        item = json.load(open(path))
        k_ev, k_logs = probes.probe_key("event_detail", {}), probes.probe_key("service_logs", {"window": "2h"})
        # the model's own answers are kept as they were, never re-run
        self.assertEqual(item["probes"][k_ev], {"culprit": "a.js"})
        self.assertEqual(item["probes"][k_logs], LONG)
        self.assertEqual(item["probes_shown"][k_logs], triage._trim(LONG))
        self.assertEqual(item["probe_source"][k_ev], "model")
        self.assertNotIn(("event_detail", {}), self.calls)
        # the rest of the menu is fetched once, at default args
        for name in probes.PROBES:
            self.assertIn(probes.probe_key(name, {}), item["probes"])
        self.assertEqual(sorted(n for n, _ in self.calls), sorted(n for n in probes.PROBES if n != "event_detail"))
        self.assertEqual(item["fleet_decision"]["disposition"], "file")
        self.assertEqual(item["fleet_decision"]["work_type"], "bug")
        self.assertEqual(item["signal"]["fingerprint"], SIGNAL["fingerprint"])

    def test_replay_hits_every_captured_answer(self):
        with mock.patch.object(config, "CAPTURE_PROBES", True):
            item = json.load(open(capture.record(SIGNAL, _disp())))
        for p in self.patches:
            p.stop()
        try:
            for key, want in item["probes"].items():
                name, _, a = key.partition(":")
                self.assertEqual(probes.run_probe(item["signal"], name, json.loads(a), table=item["probes"]), want)
        finally:
            for p in self.patches:
                p.start()

    def test_eager_off_keeps_only_the_model_probes(self):
        with mock.patch.object(config, "CAPTURE_PROBES", True), mock.patch.object(config, "CAPTURE_EAGER", False):
            item = json.load(open(capture.record(SIGNAL, _disp())))
        self.assertEqual(set(item["probe_source"].values()), {"model"})
        self.assertEqual(self.calls, [])

    def test_a_failed_write_never_breaks_the_cycle(self):
        with mock.patch.object(config, "CAPTURE_PROBES", True), \
             mock.patch.object(config, "CAPTURE_DIR", "/proc/no-such-dir/x"):
            self.assertIsNone(capture.record(SIGNAL, _disp()))

    def test_act_calls_capture_after_the_ledger_row(self):
        import actions
        order = []
        with mock.patch.object(actions, "ledger_append", lambda *a, **k: order.append("ledger")), \
             mock.patch.object(capture, "record", lambda *a, **k: order.append("capture")):
            actions.act(SIGNAL, {"disposition": "escalate", "reason": "r", "question": "q"}, dry_run=True)
        self.assertEqual(order, ["ledger", "capture"])


if __name__ == "__main__":
    unittest.main()
