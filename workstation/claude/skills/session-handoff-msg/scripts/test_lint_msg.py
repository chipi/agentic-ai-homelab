"""Tests for lint_msg.py, replaying the two 2026-10-17 messages: `python3 -m unittest test_lint_msg`."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent / "lint_msg.py"


def run(text: str, *args: str) -> subprocess.CompletedProcess[str]:
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
        f.write(text)
    return subprocess.run([sys.executable, str(SCRIPT), f.name, *args], capture_output=True, text=True)


class LintTests(unittest.TestCase):
    def test_the_real_placeholder_message_is_refused(self) -> None:
        r = run("Questions:\n3. Do you want a different stage for any of the 21?\n\nBatch 2 ids: BATCH2_IDS")
        self.assertEqual(r.returncode, 1)
        self.assertIn("BATCH2_IDS", r.stdout)

    def test_a_real_name_in_backticks_is_not_a_placeholder(self) -> None:
        r = run("Set `PROD_SSH_HOST_KEY` on the repo.")
        self.assertEqual(r.returncode, 0, r.stdout)

    def test_an_unproven_hold_claim_is_refused(self) -> None:
        r = run("Batch 2 is dispatched but NOT started. I am holding it until you answer.")
        self.assertEqual(r.returncode, 1)
        self.assertIn("claim 'holding' has no --proof", r.stdout)

    def test_a_proof_that_fails_refuses_and_one_that_passes_sends(self) -> None:
        msg = "I am holding it until you answer."
        self.assertEqual(run(msg, "--proof", "holding=test -e /nonexistent/HOLD").returncode, 1)
        r = run(msg, "--proof", "holding=true")
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("SENDABLE", r.stdout)

    def test_markers_and_brackets(self) -> None:
        for bad in ("ids: <ids here>", "ids: {ids}", "ids: $BATCH_IDS", "TODO add the ids"):
            self.assertEqual(run(bad).returncode, 1, bad)


if __name__ == "__main__":
    unittest.main()
