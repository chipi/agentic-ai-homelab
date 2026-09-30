"""Acceptance + unit tests for drift.py, replaying the real 2026-09-30 state.

  python3 test_drift.py
"""
import json
import os
import unittest

import drift

FX = os.path.join(os.path.dirname(__file__), "fixtures")


def _load(repo_yaml, live_json):
    with open(os.path.join(FX, repo_yaml)) as f:
        repo = drift.repo_rules(f.read())
    with open(os.path.join(FX, live_json)) as f:
        live = {r["uid"]: r for r in json.load(f)}
    return repo, live


class TestReplay20260930(unittest.TestCase):
    """Input: the repo's rules.yaml and Grafana's live rules on 2026-09-30.
    Today (no check): the drift was invisible for 12 days (#58 fired falsely,
    four delivery rules never ran). After: the check names exactly that drift."""

    def test_before_reload_finds_the_real_drift(self):
        r = drift.compare(*_load("repo-rules-2026-09-30-before.yaml",
                                 "live-rules-2026-09-30-before-reload.json"))
        self.assertEqual(r["missing"], ["delivery-cadence-daily-recap-stale",
                                        "delivery-cadence-erroring",
                                        "delivery-cadence-recommendations-stale",
                                        "delivery-cadence-weekly-stale"])
        self.assertEqual(list(r["changed"]), ["podcast-ingest-stalled"])
        self.assertEqual(r["extra"], [])

    def test_after_reload_is_clean(self):
        r = drift.compare(*_load("repo-rules-2026-09-30-after.yaml",
                                 "live-rules-2026-09-30-after-reload.json"))
        self.assertEqual((r["missing"], r["extra"], r["changed"]), ([], [], {}))


class TestNormalisation(unittest.TestCase):
    def _rule(self, **kw):
        base = {"uid": "u", "title": "t", "condition": "c", "for": "0s", "noDataState": "OK",
                "labels": {"severity": "warning"},
                "data": [{"refId": "q", "datasourceUid": "vm", "model": {"expr": "up == 0"},
                          "relativeTimeRange": {"from": 600, "to": 0}},
                         {"refId": "c", "datasourceUid": "__expr__",
                          "model": {"type": "threshold", "expression": "q"}}]}
        base.update(kw)
        return base

    def test_duration_spelling_is_not_drift(self):
        r = drift.compare({"u": self._rule(**{"for": "0m"})}, {"u": self._rule()})
        self.assertEqual(r["changed"], {})

    def test_default_nodata_is_not_drift(self):
        repo = self._rule()
        del repo["noDataState"]
        r = drift.compare({"u": repo}, {"u": self._rule(noDataState="NoData")})
        self.assertEqual(r["changed"], {})

    def test_query_change_is_drift(self):
        live = self._rule()
        live["data"][0]["model"]["expr"] = "up == 1"
        self.assertEqual(drift.compare({"u": self._rule()}, {"u": live})["changed"], {"u": ["data"]})

    def test_label_change_is_drift(self):
        r = drift.compare({"u": self._rule(labels={"severity": "critical"})}, {"u": self._rule()})
        self.assertEqual(r["changed"], {"u": ["labels"]})

    def test_nodata_change_is_drift(self):
        r = drift.compare({"u": self._rule(noDataState="Alerting")}, {"u": self._rule()})
        self.assertEqual(r["changed"], {"u": ["noDataState"]})

    def test_annotation_change_is_not_drift(self):
        r = drift.compare({"u": self._rule(annotations={"summary": "new wording"})}, {"u": self._rule()})
        self.assertEqual(r["changed"], {})

    def test_metrics_push_body(self):
        body = drift.metrics({"missing": ["a"], "extra": [], "changed": {"b": ["data"]}})
        self.assertIn('grafana_alert_rules_drift{kind="missing"', body)
        self.assertIn("grafana_alert_rules_drift_check_ok", body)
        self.assertTrue(body.strip().splitlines()[-1].startswith("grafana_alert_rules_drift_last_check_timestamp"))
        failed = drift.metrics(None, ok=False)
        self.assertIn("grafana_alert_rules_drift_check_ok{service=\"grafana\",environment=\"operations\"} 0", failed)
        self.assertNotIn("last_check_timestamp", failed)


if __name__ == "__main__":
    unittest.main()
