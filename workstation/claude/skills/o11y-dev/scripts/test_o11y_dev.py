"""Tests for o11y_dev.py with fake HTTP: `python3 -m unittest test_o11y_dev` from this directory."""

from __future__ import annotations

import contextlib
import datetime as dt
import io
import json
import os
import unittest
import urllib.parse
from unittest import mock

import o11y_dev

NOW = dt.datetime(2026, 11, 16, 12, 0, tzinfo=dt.timezone.utc)


def issue(short, last, title="TypeError: x"):
    return {"shortId": short, "count": "2", "lastSeen": last, "title": title, "culprit": "mod.fn",
            "permalink": f"https://glitchtip.example/{short}"}


def trace(env, spans, worktree=None, tid="abc123"):
    tags = [{"key": "deployment.environment", "value": env}]
    if worktree:
        tags.append({"key": "worktree", "value": worktree})
    return {"traceID": tid, "processes": {"p1": {"tags": tags}}, "spans": spans}


def span(op="GET", start=0, dur=1_000_000, **tags):
    return {"operationName": op, "startTime": start, "duration": dur,
            "tags": [{"key": k, "value": v} for k, v in tags.items()]}


class Fake:
    """Routes by URL; records every URL. A value that is an Exception is raised."""

    def __init__(self, issues=None, stats=None, err_count=0, rows=None, traces=None, logs_error=None):
        self.issues, self.stats, self.err_count, self.rows = issues or [], stats or [], err_count, rows or []
        self.traces, self.logs_error, self.urls = traces or [], logs_error, []

    def __call__(self, url, headers=None, timeout=60):
        self.urls.append(url)
        if "/api/0/projects/" in url:
            assert headers and headers["Authorization"].startswith("Bearer ")
            return json.dumps(self.issues)
        if "/select/logsql/query" in url:
            if self.logs_error:
                raise self.logs_error
            q = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)["query"][0]
            if "stats by (level)" in q:
                return "\n".join(json.dumps(r) for r in self.stats)
            if "stats count()" in q:
                return json.dumps({"n": str(self.err_count)})
            return "\n".join(json.dumps(r) for r in self.rows)
        if "/jaeger/api/traces" in url:
            return json.dumps({"data": self.traces})
        raise AssertionError(url)


def run(args, fake, token="tok"):
    out = io.StringIO()
    env = {"GLITCHTIP_DEV_TOKEN": token} if token else {}
    with mock.patch.dict(os.environ, env, clear=True), \
            mock.patch.object(o11y_dev, "load_token", lambda: token), contextlib.redirect_stdout(out):
        rc = o11y_dev.main(args, get=fake, now=NOW)
    return rc, out.getvalue()


class DevTests(unittest.TestCase):
    def test_orrery_is_branch_filtered_and_drops_issues_outside_the_window(self):
        fake = Fake(issues=[issue("ORRERY-DEV-1", "2026-11-15T10:00:00Z"), issue("ORRERY-DEV-2", "2026-10-01T10:00:00Z")])
        rc, out = run(["--project", "orrery", "--branch", "feat/x", "--since", "7d"], fake)
        self.assertEqual(rc, 0, out)
        self.assertIn("worktree%3Afeat%2Fx", fake.urls[0])
        self.assertTrue(any('worktree%3A%22feat%2Fx%22' in u for u in fake.urls if "logsql" in u))
        self.assertIn("ORRERY-DEV-1", out)
        self.assertNotIn("ORRERY-DEV-2", out)
        self.assertIn("O11Y-DEV chipi/orrery feat/x: errors=1 (branch-filtered), error-logs=0, failed-traces=0", out)

    def test_podcast_queries_every_dev_project_by_branch(self):
        # from podcast_scraper b647d1633 its dev errors, logs and traces carry `worktree` (ingestion, 2026-11-16)
        fake = Fake(issues=[issue("PIPE-1", "2026-11-15T10:00:00Z")])
        rc, out = run(["--project", "podcast_scraper", "--branch", "b", "--since", "7d"], fake)
        self.assertEqual(rc, 0, out)
        gt = [u for u in fake.urls if "/api/0/projects/" in u]
        self.assertEqual(len(gt), 4)
        self.assertTrue(any("gi-kg-viewer-dev" in u for u in gt))
        self.assertTrue(all("worktree" in u for u in gt))
        self.assertIn("(branch-filtered)", out)

    def test_a_logs_failure_is_not_checked_and_exits_2_never_zero_errors(self):
        rc, out = run(["--project", "orrery", "--branch", "b", "--since", "7d"], Fake(logs_error=OSError("timed out")))
        self.assertEqual(rc, 2)
        self.assertIn("NOT CHECKED logs: VictoriaLogs: timed out", out)

    def test_no_token_is_not_checked_and_exits_2(self):
        rc, out = run(["--project", "orrery", "--branch", "b", "--since", "7d"], Fake(), token="")
        self.assertEqual(rc, 2)
        self.assertIn("NOT CHECKED glitchtip: no GLITCHTIP_DEV_TOKEN", out)

    def test_project_without_dev_telemetry_is_said_plainly(self):
        with mock.patch.object(o11y_dev, "declared_reason", lambda cwd=None: ""):
            rc, out = run(["--project", "chipi/oceancanvas", "--branch", "b"], Fake())
        self.assertEqual(rc, 2)
        self.assertIn("sends no dev telemetry yet", out)
        self.assertIn("o11y-dev.md", out)
        self.assertIn(".o11y-dev.json", out)

    def test_a_declared_project_has_nothing_to_check_and_passes(self):
        fake = Fake()
        with mock.patch.object(o11y_dev, "declared_reason", lambda cwd=None: "static pages; local checks send nothing"):
            rc, out = run(["--project", "chipi/humancopilot.eu", "--branch", "b"], fake)
        self.assertEqual(rc, 0, out)
        self.assertIn("static pages; local checks send nothing", out)
        self.assertIn("O11Y-DEV chipi/humancopilot.eu b: nothing to check (declared by the project)", out)
        self.assertEqual(fake.urls, [])

    def test_a_declaration_does_not_silence_a_project_with_telemetry(self):
        with mock.patch.object(o11y_dev, "declared_reason", lambda cwd=None: "nothing here"):
            rc, out = run(["--project", "orrery", "--branch", "feat/x", "--since", "7d"], Fake())
        self.assertNotIn("nothing to check", out)
        self.assertIn("O11Y-DEV chipi/orrery feat/x: errors=", out)

    def test_declared_reason_reads_the_repo_root(self):
        import subprocess
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            subprocess.run(["git", "init", "-q", d], check=True)
            os.makedirs(os.path.join(d, "sub"))
            self.assertEqual(o11y_dev.declared_reason(os.path.join(d, "sub")), "")
            with open(os.path.join(d, ".o11y-dev.json"), "w") as f:
                json.dump({"nothing_to_check": " static site "}, f)
            self.assertEqual(o11y_dev.declared_reason(os.path.join(d, "sub")), "static site")
            with open(os.path.join(d, ".o11y-dev.json"), "w") as f:
                f.write("not json")
            self.assertEqual(o11y_dev.declared_reason(d), "")

    def test_error_logs_levels_and_normalized_patterns(self):
        fake = Fake(stats=[{"level": "info", "n": "40"}, {"level": "error", "n": "3"}], err_count=3, rows=[
            {"level": "error", "_msg": "fetch failed for episode 1234 id 0123456789abcdef"},
            {"level": "error", "_msg": "fetch failed for episode 99 id fedcba9876543210"},
            {"level": "warn", "_msg": "slow"}])
        rc, out = run(["--project", "orrery", "--branch", "b", "--since", "7d"], fake)
        self.assertIn("info=40", out)
        self.assertIn("2  error  fetch failed for episode <n> id <id>", out.replace("   ", " "))
        self.assertIn("error-logs=3", out)

    def test_traces_keep_dev_only_count_failed_and_respect_a_worktree_tag(self):
        fake = Fake(traces=[
            trace("dev", [span(**{"http.status_code": 500})], tid="t500"),
            trace("dev", [span(error=True)], worktree="other", tid="tother"),
            trace("dev", [span(error="true")], worktree="b", tid="tmine"),
            trace("prod", [span(error=True)], tid="tprod"),
            trace("dev", [span(**{"http.status_code": 200})], tid="tok")])
        rc, out = run(["--project", "orrery", "--branch", "b", "--since", "7d"], fake)
        self.assertIn("orrery-lab-api: 3 dev traces, 2 failed (2 without a `worktree` label, not branch-filtered)", out)
        self.assertIn("failed-traces=4", out)
        self.assertNotIn("tprod", out)
        self.assertNotIn("tother", out)

    def test_the_trace_query_names_the_resource_attribute(self):
        # VictoriaTraces' Jaeger API matches a resource attribute only as resource_attr:<name>: the bare
        # "deployment.environment" matched no trace (eval-harness session, 2026-11-16: 0 vs 4 over 2h)
        fake = Fake()
        run(["--project", "orrery", "--branch", "b", "--since", "7d"], fake)
        jaeger = [u for u in fake.urls if "/jaeger/api/traces" in u]
        self.assertTrue(jaeger)
        for u in jaeger:
            self.assertIn("resource_attr%3Adeployment.environment", u)

    def test_the_player_app_reads_player_dev_by_branch(self):
        cfg = o11y_dev.PROJECTS["chipi/closelistening-player"]
        self.assertEqual(cfg["glitchtip"], ["player-dev"])
        self.assertTrue(cfg["branch_tag"])
        self.assertFalse(cfg["logs_branch"])
        self.assertEqual(cfg["traces"], ["player-api"])

    def test_eval_harness_is_on_the_contract(self):
        cfg = o11y_dev.PROJECTS["chipi/eval-harness"]
        self.assertEqual(cfg["glitchtip"], ["evals-dev"])
        self.assertTrue(cfg["branch_tag"] and cfg["logs_branch"])
        self.assertEqual(cfg["traces"], ["evals-inspector", "evals-mcp"])

    def test_helpers(self):
        self.assertEqual(o11y_dev.project_from_remote("git@github.com:chipi/orrery.git"), "chipi/orrery")
        self.assertEqual(o11y_dev.project_from_remote("https://github.com/chipi/podcast_scraper"), "chipi/podcast_scraper")
        self.assertEqual(o11y_dev.parse_since("14d", NOW), NOW - dt.timedelta(days=14))
        self.assertEqual(o11y_dev.trace_failed([span(**{"http.response.status_code": "503"})]), True)


if __name__ == "__main__":
    unittest.main()
