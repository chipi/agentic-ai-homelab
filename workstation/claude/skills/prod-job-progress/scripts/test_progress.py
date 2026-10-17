"""Unit tests for progress.report (stdlib): `python3 -m unittest test_progress` in scripts/."""

from __future__ import annotations

import datetime as dt
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import progress  # noqa: E402

NOW = dt.datetime(2026, 10, 17, 13, 8, 5, tzinfo=dt.timezone.utc)
BASE = {"found": True, "started": "2026-10-17T11:08:05.043415064Z", "status": "running 0",
        "last_log": "x", "problem_lines": 0, "first_done": "", "last_done": ""}


class ReportTests(unittest.TestCase):
    def test_zero_with_activity_is_inconclusive_not_no_progress(self) -> None:
        text, rc = progress.report({**BASE, "done": 0, "any_files": 791, "log_lines": 2318}, 21, NOW)
        self.assertEqual(rc, 2)
        self.assertIn("INCONCLUSIVE", text)

    def test_zero_with_nothing_written_is_reported_as_no_output_yet(self) -> None:
        text, rc = progress.report({**BASE, "done": 0, "any_files": 0, "log_lines": 10}, 21, NOW)
        self.assertEqual(rc, 0)
        self.assertIn("no output yet", text)

    def test_rate_and_eta(self) -> None:
        t0 = dt.datetime(2026, 10, 17, 11, 15, tzinfo=dt.timezone.utc).timestamp()
        r = {**BASE, "done": 10, "any_files": 500, "log_lines": 900, "first_done": str(t0), "last_done": str(t0 + 3000)}
        text, rc = progress.report(r, 20, NOW)
        self.assertEqual(rc, 0)
        self.assertIn("done: 10 of 20", text)
        self.assertIn("rate: 5.0/h", text)
        self.assertIn("~15:08 UTC", text)  # 10 left at 5/h from 13:08

    def test_missing_container(self) -> None:
        self.assertEqual(progress.report({"found": False}, None, NOW)[1], 1)


if __name__ == "__main__":
    unittest.main()
