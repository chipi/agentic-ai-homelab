"""Tests for poll.py over fixtures (no network): python3 test_poll.py"""
import copy
import json
import os
import unittest
from datetime import datetime, timezone

import poll

NOW = datetime(2026, 11, 4, 16, 30, tzinfo=timezone.utc)
GH = {"type": "statuspage", "url": "x", "components": ["Git Operations", "Actions", "Packages", "API Requests"]}
SUMMARY = {
    "status": {"indicator": "minor", "description": "Partially Degraded Service"},
    "components": [{"name": "Actions", "status": "degraded_performance"}, {"name": "Git Operations", "status": "operational"},
                   {"name": "Copilot", "status": "major_outage"}],
    "incidents": [
        {"id": "i1", "name": "Incident with Actions and Pages", "impact": "minor", "status": "investigating",
         "created_at": "2026-11-04T16:05:31.580Z", "updated_at": "2026-11-04T16:20:00.000Z", "shortlink": "https://stspg.io/a",
         "components": [{"name": "Actions"}, {"name": "Pages"}], "incident_updates": [{"body": "We are investigating delayed runs."}]},
        {"id": "i2", "name": "Copilot slow", "impact": "minor", "status": "identified", "created_at": "2026-11-04T15:00:00.000Z",
         "updated_at": "2026-11-04T15:10:00.000Z", "shortlink": "https://stspg.io/b", "components": [{"name": "Copilot"}]}],
    "scheduled_maintenances": [
        {"id": "m1", "name": "Git database upgrade", "status": "in_progress", "scheduled_for": "2026-11-04T16:00:00.000Z",
         "scheduled_until": "2026-11-04T18:00:00.000Z", "updated_at": "2026-11-04T16:00:00.000Z", "components": [{"name": "Git Operations"}]},
        {"id": "m2", "name": "Packages storage migration", "status": "scheduled", "scheduled_for": "2026-11-07T02:00:00.000Z",
         "scheduled_until": "2026-11-07T04:00:00.000Z", "updated_at": "2026-11-01T10:00:00.000Z", "components": [{"name": "Packages"}]},
        {"id": "m3", "name": "Far future", "status": "scheduled", "scheduled_for": "2026-11-20T02:00:00.000Z",
         "updated_at": "2026-11-01T10:00:00.000Z", "components": [{"name": "Actions"}]}],
}
OR = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "providers.json")))["providers"]["openrouter"]


def item(title, link, cat, pub, updates):
    d = "".join("<p><small>%s</small><br><strong>%s</strong> - %s </p>" % u for u in updates)
    return ("<item><title>%s</title><link>%s</link><guid isPermaLink=\"true\">%s</guid><pubDate>%s</pubDate>"
            "<category>%s</category><description>%s</description></item>") % (
        title, link, link, pub, cat, d.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


RSS = "<rss><channel><title>OpenRouter - Incident History</title>%s</channel></rss>" % "".join([
    item("Scheduled site maintenance", "https://s/m1", "maintenance", "Sun, 01 Nov 2026 22:00:00 +0000",
         [("Nov  1, 22:00 UTC", "Completed", "Maintenance is complete."), ("Nov  1, 21:00 UTC", "In Progress", "Inference is not affected.")]),
    item("Video webhooks are not being called", "https://s/i1", "incident", "Mon, 26 Oct 2026 00:07:28 +0000",
         [("Oct 26, 00:07 UTC", "Resolved", "Video webhooks are firing correctly again.")]),
    item("Elevated API errors on chat completions", "https://s/i2", "incident", "Wed, 04 Nov 2026 16:10:00 +0000",
         [("Nov  4, 16:10 UTC", "Identified", "Some requests fail with 502."), ("Nov  4, 15:55 UTC", "Investigating", "Looking into errors.")]),
    item("Upgrading the dashboard database", "https://s/m2", "maintenance", "Tue, 03 Nov 2026 09:00:00 +0000",
         [("Nov  3, 09:00 UTC", "Scheduled", "Credits cannot be added during it. Inference is not affected.")]),
    item("Sign-in failures on openrouter.ai", "https://s/i3", "incident", "Wed, 04 Nov 2026 12:00:00 +0000",
         [("Nov  4, 12:00 UTC", "Investigating", "Some users cannot sign in.")]),
])


class Statuspage(unittest.TestCase):
    def test_items(self):
        it = {x["id"]: x for x in poll.statuspage_items(SUMMARY, set(GH["components"]), NOW)}
        self.assertEqual((it["i1"]["relevance"], it["i1"]["phase"], it["i1"]["components"]), ("direct", "ongoing", "Actions"))
        self.assertEqual(it["i1"]["last_update"], "We are investigating delayed runs.")
        self.assertEqual(it["i2"]["relevance"], "other")
        self.assertEqual((it["m1"]["phase"], it["m2"]["phase"], it["m3"]["phase"]), ("ongoing", "upcoming", None))

    def test_metrics(self):
        its, extra = poll.read_provider("github", GH, get=lambda u: json.dumps(SUMMARY), now=NOW)
        lines = poll.metric_lines("github", True, its, extra)
        self.assertIn('provider_status_component{provider="github",name="Actions",status="degraded_performance"} 1', lines)
        self.assertFalse(any("Copilot" in l and "provider_status_component" in l for l in lines))
        self.assertEqual(sum(l.startswith("provider_status_active") for l in lines), 4)       # i1, i2, m1, m2
        self.assertIn('provider_status_poll_ok{provider="github"} 1', lines)
        self.assertEqual(poll.metric_lines("github", False, [], []), ['provider_status_poll_ok{provider="github"} 0'])


class Rss(unittest.TestCase):
    def setUp(self):
        self.it = {x["id"]: x for x in poll.rss_items(RSS, OR)}

    def test_state_from_the_newest_update(self):
        self.assertEqual((self.it["https://s/m1"]["status"], self.it["https://s/m1"]["phase"]), ("Completed", None))
        self.assertEqual((self.it["https://s/i1"]["status"], self.it["https://s/i1"]["phase"]), ("Resolved", None))
        self.assertEqual((self.it["https://s/i2"]["status"], self.it["https://s/i2"]["phase"]), ("Identified", "ongoing"))
        self.assertEqual((self.it["https://s/m2"]["kind"], self.it["https://s/m2"]["phase"]), ("maintenance", "upcoming"))
        self.assertEqual(self.it["https://s/i2"]["last_update"], "Some requests fail with 502.")

    def test_relevance(self):
        self.assertEqual(self.it["https://s/i2"]["relevance"], "direct")                       # the API: ours
        self.assertEqual(self.it["https://s/m2"]["relevance"], "other")                        # "Inference is not affected"
        self.assertEqual(self.it["https://s/i3"]["relevance"], "other")                        # sign-in: the website
        self.assertEqual(self.it["https://s/i1"]["relevance"], "other")                        # video

    def test_metrics_and_update_change(self):
        lines = poll.metric_lines("openrouter", True, list(self.it.values()), [])
        active = [l for l in lines if l.startswith("provider_status_active")]
        self.assertEqual(len(active), 3)                                                        # i2, m2, i3; not the ended two
        self.assertTrue(any('relevance="direct"' in l and "Elevated API errors" in l for l in active))


class Events(unittest.TestCase):
    def test_backfill_per_provider_then_changes(self):
        state = {}
        gh = poll.statuspage_items(SUMMARY, set(GH["components"]), NOW)
        orr = poll.rss_items(RSS, OR)
        self.assertTrue(all(e["backfill"] == "true" for e in poll.new_events(state, "github", gh)))
        self.assertEqual(poll.new_events(state, "github", gh), [])
        first_or = poll.new_events(state, "openrouter", orr)                                    # a new provider: its own backfill
        self.assertTrue(first_or and all(e["backfill"] == "true" and e["provider"] == "openrouter" for e in first_or))
        rss2 = RSS.replace("Wed, 04 Nov 2026 16:10:00 +0000", "Wed, 04 Nov 2026 16:40:00 +0000").replace(
            "&lt;strong&gt;Identified&lt;/strong&gt;", "&lt;strong&gt;Monitoring&lt;/strong&gt;")
        ev = poll.new_events(state, "openrouter", poll.rss_items(rss2, OR))
        self.assertEqual([(e["id"], e["backfill"], e["status"]) for e in ev], [("https://s/i2", "false", "Monitoring")])
        self.assertEqual(ev[0]["app"], "provider-status")

    def test_state_forgets_items_gone_from_the_source(self):
        state = {}
        poll.new_events(state, "github", poll.statuspage_items(SUMMARY, set(GH["components"]), NOW))
        s2 = copy.deepcopy(SUMMARY)
        s2["incidents"] = []
        poll.new_events(state, "github", poll.statuspage_items(s2, set(GH["components"]), NOW))
        self.assertNotIn("i1", state["seen"]["github"])


class RealFeed(unittest.TestCase):
    def test_parses_providers_json(self):
        p = poll.load_providers()
        self.assertEqual(set(p), {"github", "openrouter"})
        self.assertEqual((p["github"]["type"], p["openrouter"]["type"]), ("statuspage", "rss"))


if __name__ == "__main__":
    unittest.main()
