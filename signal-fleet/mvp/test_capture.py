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

    def test_the_models_own_decision_survives_the_gates(self):
        # 2026-11-05 review: a gate rewrites the decision in place (the intent gate drops the acceptance
        # criteria), so nothing kept what the model decided; a gate change could not be measured without
        # re-running the model. investigate() now keeps the model's decision as _pre_gate.
        replies = iter(['{"action":"decide","disposition":"dismiss","reason":"benign",'
                        '"dismissal_evidence":"seen before","certainty":"high"}'])
        with mock.patch.object(triage, "_call", lambda *a, **k: (next(replies), {})), \
                mock.patch.object(triage.observ, "finalize"):
            d = triage.investigate(SIGNAL, probe_table={})
        self.assertEqual(d["disposition"], "escalate")                 # the dismiss gate, no corroboration
        self.assertEqual(d["_pre_gate"]["disposition"], "dismiss")     # what the model decided
        self.assertEqual(d["_pre_gate"]["dismissal_evidence"], "seen before")
        self.assertNotIn("_pre_gate", d["_pre_gate"])

    def test_capture_keeps_the_models_own_decision(self):
        d = _disp()
        d["_pre_gate"] = {"disposition": "file", "file": {"acceptance": [{"criterion": "c"}]}}
        with mock.patch.object(config, "CAPTURE_PROBES", True), mock.patch.object(config, "CAPTURE_EAGER", False):
            item = json.load(open(capture.record(SIGNAL, d)))
        self.assertEqual(item["model_decision"], d["_pre_gate"])

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


class FilingAndSweepRecords(unittest.TestCase):
    """callrec.py (ADR-0004 / RFC-0002 §9 step 1): what filing and the stale sweep looked up, computed and wrote,
    recorded for an exact replay, without changing what they do. GitHub is a stand-in; nothing leaves the test."""

    def setUp(self):
        import callrec
        import filing
        self.filing, self.callrec = filing, callrec
        self.root = tempfile.mkdtemp()
        self.probes = os.path.join(self.root, "probes")
        self.ledger = os.path.join(self.root, "filed.tsv")
        self.gh_calls = []

        def gh(method, path, payload=None):
            self.gh_calls.append((method, path))
            if method == "POST" and path.endswith("/issues"):
                return {"number": 7, "html_url": "u/7"}
            if method == "GET" and "/milestones" in path:
                return []
            return {}
        self.gh = gh
        self.patches = [mock.patch.object(config, "CAPTURE_DIR", self.probes),
                        mock.patch.object(probes, "run_probe", lambda *a, **k: "<eager>"),
                        mock.patch.object(filing, "FILED", self.ledger),
                        mock.patch.object(filing, "_gh", gh),
                        mock.patch.object(filing, "_related_issues", lambda *a, **k: []),
                        mock.patch.object(filing, "_glitchtip_note", lambda *a, **k: None),
                        mock.patch.object(filing, "issue_state",
                                          lambda r, n: {"state": "open", "labels": [], "closed_at": None, "url": ""})]
        for p in self.patches:
            p.start()
        callrec.LAST_FILING = None

    def tearDown(self):
        for p in self.patches:
            p.stop()

    def _file(self):
        return self.filing.file_or_update(SIGNAL, {"title": "TypeError: x is undefined", "body": "b"}, "bug")

    def test_off_records_nothing_and_changes_nothing(self):
        out = self._file()
        self.assertTrue(out.startswith("FILED"), out)
        self.assertIs(self.filing._gh, self.gh)
        self.assertIsNone(self.callrec.LAST_FILING)
        self.assertFalse(os.path.exists(os.path.join(self.root, "filing")))

    def test_on_the_same_outcome_and_calls_as_off(self):
        off = self._file()
        calls_off = list(self.gh_calls)
        os.unlink(self.ledger)
        self.gh_calls.clear()
        with mock.patch.object(config, "CAPTURE_PROBES", True):
            on = self._file()
        self.assertEqual(on, off)
        self.assertEqual(self.gh_calls, calls_off)
        self.assertIs(self.filing._gh, self.gh)   # restored

    def test_the_filing_record(self):
        with mock.patch.object(config, "CAPTURE_PROBES", True):
            out = self._file()
            path = capture.record(SIGNAL, _disp())
        rec = json.load(open(os.path.join(self.root, "filing", os.path.basename(path))))
        self.assertEqual(rec["fingerprint"], SIGNAL["fingerprint"])
        self.assertEqual(rec["result"], out)
        self.assertEqual(rec["work_type"], "bug")
        self.assertEqual(rec["issue"], {"title": "TypeError: x is undefined", "body": "b"})   # the input as passed
        self.assertTrue(rec["clock"])   # every clock reading filing made (it stamps filed_at with one)
        self.assertEqual(set(rec["keys"]), {"group_key", "norm_key", "alert_key", "repo"})
        self.assertEqual(rec["keys"]["norm_key"], self.filing.normalized_key(SIGNAL))
        self.assertIsNone(rec["matched"])
        self.assertIn(["POST", "/repos/" + rec["keys"]["repo"] + "/issues"],
                      [[c["method"], c["path"]] for c in rec["github"]])
        self.assertEqual([r["issue"] for r in rec["written"]], [7])
        self.assertEqual(stat.S_IMODE(os.stat(os.path.join(self.root, "filing", os.path.basename(path))).st_mode), 0o600)

    def test_a_match_records_its_dimension(self):
        nk = self.filing.normalized_key(SIGNAL)
        self.filing._ledger_write([{"fingerprint": "glitchtip:ORRERY-PROD-1", "repo": "chipi/orrery", "issue": "5",
                                    "group_key": "", "norm_key": nk, "alert_key": "", "last_comment_day": ""}])
        with mock.patch.object(config, "CAPTURE_PROBES", True):
            out = self._file()
        rec = self.callrec.LAST_FILING
        self.assertTrue(out.startswith("COMMENTED"), out)
        self.assertEqual((rec["matched"]["issue"], rec["matched"]["_dim"]), ("5", "norm_key"))

    def test_probes_gets_only_the_capture(self):
        with mock.patch.object(config, "CAPTURE_PROBES", True):
            self._file()
            path = capture.record(SIGNAL, _disp())
        self.assertEqual(os.listdir(self.probes), [os.path.basename(path)])

    def test_a_record_of_another_decision_is_not_written(self):
        with mock.patch.object(config, "CAPTURE_PROBES", True):
            self._file()
            other = dict(SIGNAL, fingerprint="glitchtip:ORRERY-PROD-2")
            path = capture.record(other, _disp())
        self.assertFalse(os.path.exists(os.path.join(self.root, "filing", os.path.basename(path))))
        self.assertIsNone(self.callrec.LAST_FILING)

    def test_gh_restored_when_filing_raises(self):
        def boom(method, path, payload=None):
            raise RuntimeError("github down")
        with mock.patch.object(self.filing, "_gh", boom), mock.patch.object(config, "CAPTURE_PROBES", True):
            with self.assertRaises(RuntimeError):
                self._file()
            self.assertIs(self.filing._gh, boom)

    def test_the_sweep_record(self):
        import datetime
        import sources
        import stale
        now = datetime.datetime(2026, 11, 9, 0, 4, 12, tzinfo=datetime.timezone.utc)
        self.filing._ledger_write([{"fingerprint": "glitchtip:ORRERY-PROD-9", "repo": "chipi/orrery", "issue": "5"}])
        occ = [("2026-10-01T00:00:00+00:00", "glitchtip:ORRERY-PROD-9", "glitchtip", "TypeError: x is undefined")]

        def gh(method, path, payload=None):
            self.gh_calls.append((method, path))
            if path.startswith("/search/issues"):
                return {"items": [{"number": 5, "labels": []}]}
            return []
        with mock.patch.object(config, "CAPTURE_PROBES", True), mock.patch.object(self.filing, "_gh", gh), \
                mock.patch.object(stale, "_occurrences", lambda: occ), \
                mock.patch.object(sources, "firing_alerts", lambda: [{"labels": {"alertname": "A"}}]):
            summary = stale.run_pass(dry_run=True, now=now, force=True)
        rec = json.load(open(os.path.join(self.root, "sweeps", "20261109T000412Z.json")))
        self.assertEqual(rec["summary"], summary)
        self.assertEqual((rec["now"], rec["dry_run"], rec["firing"]), (now.isoformat(), True, ["A"]))
        self.assertEqual(rec["occurrences"]["count"], 1)
        self.assertEqual([c["path"].split("?")[0] for c in rec["github"]],
                         ["/search/issues", "/repos/chipi/orrery/issues/5/comments"])


if __name__ == "__main__":
    unittest.main()
