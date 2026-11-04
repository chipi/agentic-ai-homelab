"""Tests for poll.py over a fixture summary (no network): python3 test_poll.py"""
import copy
import unittest
from datetime import datetime, timezone

import poll

NOW = datetime(2026, 11, 4, 16, 30, tzinfo=timezone.utc)
OURS = {"Git Operations", "Actions", "Packages", "API Requests"}
SUMMARY = {
    "status": {"indicator": "minor", "description": "Partially Degraded Service"},
    "components": [
        {"name": "Actions", "status": "degraded_performance"},
        {"name": "Git Operations", "status": "operational"},
        {"name": "Copilot", "status": "major_outage"},
    ],
    "incidents": [
        {"id": "i1", "name": "Incident with Actions and Pages", "impact": "minor", "status": "investigating",
         "created_at": "2026-11-04T16:05:31.580Z", "updated_at": "2026-11-04T16:20:00.000Z", "shortlink": "https://stspg.io/a",
         "components": [{"name": "Actions"}, {"name": "Pages"}],
         "incident_updates": [{"body": "We are investigating delayed runs."}]},
        {"id": "i2", "name": "Copilot slow", "impact": "minor", "status": "identified",
         "created_at": "2026-11-04T15:00:00.000Z", "updated_at": "2026-11-04T15:10:00.000Z", "shortlink": "https://stspg.io/b",
         "components": [{"name": "Copilot"}], "incident_updates": []},
    ],
    "scheduled_maintenances": [
        {"id": "m1", "name": "Git database upgrade", "impact": "maintenance", "status": "in_progress",
         "scheduled_for": "2026-11-04T16:00:00.000Z", "scheduled_until": "2026-11-04T18:00:00.000Z", "updated_at": "2026-11-04T16:00:00.000Z",
         "shortlink": "https://stspg.io/c", "components": [{"name": "Git Operations"}]},
        {"id": "m2", "name": "Packages storage migration", "impact": "maintenance", "status": "scheduled",
         "scheduled_for": "2026-11-07T02:00:00.000Z", "scheduled_until": "2026-11-07T04:00:00.000Z", "updated_at": "2026-11-01T10:00:00.000Z",
         "shortlink": "https://stspg.io/d", "components": [{"name": "Packages"}]},
        {"id": "m3", "name": "Far future", "impact": "maintenance", "status": "scheduled",
         "scheduled_for": "2026-11-20T02:00:00.000Z", "updated_at": "2026-11-01T10:00:00.000Z", "components": [{"name": "Actions"}]},
    ],
}


class Items(unittest.TestCase):
    def test_relevance_and_phase(self):
        it = {x["id"]: x for x in poll.items(SUMMARY, OURS, NOW)}
        self.assertEqual((it["i1"]["relevance"], it["i1"]["phase"], it["i1"]["kind"]), ("direct", "ongoing", "incident"))
        self.assertEqual(it["i1"]["components"], "Actions")              # the matching ones, not Pages too
        self.assertEqual(it["i1"]["last_update"], "We are investigating delayed runs.")
        self.assertEqual((it["i2"]["relevance"], it["i2"]["components"]), ("other", "Copilot"))
        self.assertEqual((it["m1"]["phase"], it["m1"]["relevance"]), ("ongoing", "direct"))   # maintenance in progress
        self.assertEqual((it["m2"]["phase"], it["m2"]["start"]), ("upcoming", "2026-11-07T02:00:00.000Z"))  # within 7 days
        self.assertIsNone(it["m3"]["phase"])                             # 16 days out: not shown yet

    def test_metrics(self):
        lines = poll.metric_lines(True, SUMMARY, OURS, NOW)
        self.assertIn('github_status_component{name="Actions",status="degraded_performance"} 1', lines)
        self.assertFalse(any("Copilot" in l and l.startswith("github_status_component") for l in lines))  # not ours
        active = [l for l in lines if l.startswith("github_status_active")]
        self.assertEqual(len(active), 4)                                 # i1, i2, m1, m2; not m3
        self.assertTrue(any('phase="upcoming"' in l and "Packages" in l for l in active))
        self.assertIn('github_status_indicator{indicator="minor",description="Partially Degraded Service"} 1', lines)

    def test_failed_poll_publishes_only_poll_ok_0(self):
        self.assertEqual(poll.metric_lines(False, {}, OURS), ["github_status_poll_ok 0"])


class Events(unittest.TestCase):
    def test_first_run_is_backfill_then_only_changes(self):
        state = {}
        its = poll.items(SUMMARY, OURS, NOW)
        first = poll.new_events(state, its)
        self.assertEqual(len(first), 5)
        self.assertTrue(all(e["backfill"] == "true" for e in first))   # already there when watching started: no alert
        self.assertEqual(poll.new_events(state, its), [])              # nothing changed
        s2 = copy.deepcopy(SUMMARY)
        s2["incidents"][0]["updated_at"] = "2026-11-04T16:40:00.000Z"
        s2["incidents"][0]["status"] = "identified"
        ev = poll.new_events(state, poll.items(s2, OURS, NOW))
        self.assertEqual([(e["id"], e["backfill"], e["status"]) for e in ev], [("i1", "false", "identified")])
        self.assertEqual(ev[0]["app"], "github-status")

    def test_state_forgets_resolved_items(self):
        state = {}
        poll.new_events(state, poll.items(SUMMARY, OURS, NOW))
        s2 = copy.deepcopy(SUMMARY)
        s2["incidents"] = []
        poll.new_events(state, poll.items(s2, OURS, NOW))
        self.assertNotIn("i1", state["seen"])


if __name__ == "__main__":
    unittest.main()
