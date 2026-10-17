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


if __name__ == "__main__":
    unittest.main()
