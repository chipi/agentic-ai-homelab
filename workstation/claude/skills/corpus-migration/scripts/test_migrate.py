"""Tests for migrate.py's parsing (stdlib): `python3 -m unittest test_migrate` in scripts/."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import migrate  # noqa: E402

STATUS = """Current version: 2.7.23
Target version:  2.7.24
Applied:         0001_faiss_to_lance, 0029_naming_arc_voices_repaired
Pending (1):
  - 0030_adfree_cut_resynced → 2.7.24: rebuild .adfree.txt with today's ad cut
"""


class PendingTests(unittest.TestCase):
    def test_reads_the_pending_list_not_the_applied_one(self) -> None:
        self.assertEqual(migrate.pending(STATUS), ["0030_adfree_cut_resynced"])

    def test_none_pending(self) -> None:
        self.assertEqual(migrate.pending("Applied: 0001_x\nPending (0):\n"), [])
        self.assertEqual(migrate.pending("Applied: 0001_x\n"), [])


class HookExitTests(unittest.TestCase):
    def test_each_hook_exit_has_its_meaning_and_others_none(self) -> None:
        self.assertIn("nothing written", migrate.hook_meaning(3))
        self.assertIn("plan-diff", migrate.hook_meaning(4))
        self.assertIn("Nothing was undone", migrate.hook_meaning(5))
        for rc in (0, 1, 2, 6):
            self.assertIsNone(migrate.hook_meaning(rc))


class ApplyTests(unittest.TestCase):
    def _job(self, tmp: Path) -> "migrate.Job":
        import json, os
        os.environ["CORPUS_MIGRATION_HOME"] = str(tmp)
        (tmp / "j").mkdir()
        (tmp / "j" / "job.json").write_text(json.dumps({
            "ssh": "h", "container": "api", "cli": "python -m podcast_scraper.cli",
            "corpus_dir_in_container": "/app/output", "expect_pending": ["0031_named_voices_shown"]}))
        import importlib
        importlib.reload(migrate)
        job = migrate.Job("j")
        job.log(event="dry-run", exit=0)
        migrate.preflight = lambda j: []
        return job

    def test_the_accept_file_reaches_the_run_command(self) -> None:
        import argparse, contextlib, io, tempfile
        with tempfile.TemporaryDirectory() as d:
            job = self._job(Path(d))
            out = io.StringIO()
            args = argparse.Namespace(said="go", dry_run=True, accept_plan_diff="/app/output/accept.json")
            with contextlib.redirect_stdout(out):
                self.assertEqual(migrate.cmd_apply(job, args), 0)
            self.assertIn("--accept-plan-diff /app/output/accept.json", out.getvalue())
            args.accept_plan_diff = None
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                migrate.cmd_apply(job, args)
            self.assertNotIn("--accept-plan-diff", out.getvalue())


if __name__ == "__main__":
    unittest.main()
