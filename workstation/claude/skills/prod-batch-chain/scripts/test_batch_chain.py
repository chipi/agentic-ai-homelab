"""Unit tests for batch_chain.py (stdlib only): `python3 -m unittest test_batch_chain` in scripts/."""

from __future__ import annotations

import datetime as dt
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))


class Base(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["PROD_BATCH_CHAIN_HOME"] = self.tmp.name
        import importlib

        import batch_chain

        self.bc = importlib.reload(batch_chain)
        d = Path(self.tmp.name) / "j"
        d.mkdir()
        (d / "job.json").write_text(json.dumps({
            "repo": "o/r", "workflow": "w.yml", "inputs": {}, "ids_input": "ids", "environment": "prod",
            "ssh": "x", "speed_work_per_wall": 3.0, "window_end_utc": "23:30", "margin_min": 15,
            "max_batch_wall_min": 320,
        }))
        (d / "pool.json").write_text(json.dumps([{"id": f"e{i}", "min": m} for i, m in enumerate([50, 50, 40, 12, 12])]))
        self.job = self.bc.Job("j")

    def tearDown(self) -> None:
        self.tmp.cleanup()


class PlanTests(Base):
    def at(self, h: int, m: int = 0) -> dt.datetime:
        return dt.datetime(2026, 10, 17, h, m, tzinfo=dt.timezone.utc)

    def test_a_batch_fits_the_window_largest_first(self) -> None:
        # 22:45 → wall left 45-15 = 30 min → 90 work-min cap: 50 + 40 fit, not the second 50
        batch, msg = self.bc.plan_batch(self.job, self.at(22, 45))
        self.assertEqual([x["id"] for x in batch], ["e0", "e2"])
        self.assertIn("left after: 3", msg)

    def test_nothing_fits_says_so(self) -> None:
        batch, msg = self.bc.plan_batch(self.job, self.at(23, 20))
        self.assertEqual(batch, [])
        self.assertIn("nothing fits", msg)

    def test_succeeded_and_in_flight_ids_are_never_replanned_but_failed_ones_are(self) -> None:
        self.job.log(event="dispatched", run_id="1", ids=["e0"], n=1, work_min=50)
        self.job.log(event="result", run_id="1", conclusion="success")
        self.job.log(event="dispatched", run_id="2", ids=["e1"], n=1, work_min=50)
        self.job.log(event="result", run_id="2", conclusion="failure")
        self.job.log(event="dispatched", run_id="3", ids=["e2"], n=1, work_min=40)
        self.assertEqual(self.job.done_ids(), {"e0", "e2"})
        self.assertEqual(self.job.in_flight(), "3")
        batch, _ = self.bc.plan_batch(self.job, self.at(10))
        self.assertEqual({x["id"] for x in batch}, {"e1", "e3", "e4"})


class MatchTests(Base):
    def test_only_our_dispatch_after_the_timestamp_matches(self) -> None:
        since = dt.datetime(2026, 10, 17, 12, 0, tzinfo=dt.timezone.utc)
        runs = [
            {"databaseId": 1, "createdAt": "2026-10-17T11:59:00Z", "event": "workflow_dispatch", "actor": "me"},
            {"databaseId": 2, "createdAt": "2026-10-17T12:00:20Z", "event": "workflow_dispatch", "actor": "me"},
            {"databaseId": 3, "createdAt": "2026-10-17T12:00:30Z", "event": "workflow_dispatch", "actor": "bot"},
            {"databaseId": 4, "createdAt": "2026-10-17T12:00:40Z", "event": "schedule", "actor": "me"},
        ]
        self.assertEqual([r["databaseId"] for r in self.bc.match_run(runs, since, "me")], [2])


class GateTests(Base):
    def test_no_approval_file_refuses(self) -> None:
        ok, why = self.job.approval()
        self.assertFalse(ok)
        self.assertIn("no approval", why)

    def test_approval_counts_batches_and_expires(self) -> None:
        a = {"said": "go", "given": (self.bc.now() - dt.timedelta(minutes=1)).isoformat(timespec="seconds"),
             "until": (self.bc.now() + dt.timedelta(hours=1)).isoformat(timespec="seconds"), "max_batches": 1}
        (self.job.dir / "approval.json").write_text(json.dumps(a))
        self.assertTrue(self.job.approval()[0])
        self.job.log(event="dispatched", run_id="8", ids=["e1"], n=1, work_min=50, adopted=True)
        self.assertTrue(self.job.approval()[0], "an adopted run was dispatched before this approval")
        self.job.log(event="dispatched", run_id="9", ids=["e0"], n=1, work_min=50)
        ok, why = self.job.approval()
        self.assertFalse(ok)
        self.assertIn("covered 1", why)
        a["until"] = (self.bc.now() - dt.timedelta(seconds=1)).isoformat(timespec="seconds")
        a["max_batches"] = 5
        (self.job.dir / "approval.json").write_text(json.dumps(a))
        self.assertIn("expired", self.job.approval()[1])

    def test_hold_stops_the_gate(self) -> None:
        a = {"said": "go", "given": self.bc.now().isoformat(timespec="seconds"),
             "until": (self.bc.now() + dt.timedelta(hours=1)).isoformat(timespec="seconds"), "max_batches": 9}
        (self.job.dir / "approval.json").write_text(json.dumps(a))
        (self.job.dir / "HOLD").write_text("x")
        with self.assertRaises(SystemExit):
            self.bc.gate(self.job)


if __name__ == "__main__":
    unittest.main()
