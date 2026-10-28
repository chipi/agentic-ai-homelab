"""Unit tests for poll.py pure functions and poll_once() with mocked I/O."""

from __future__ import annotations

import importlib
import json
import sys
import unittest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch, call

# poll.py is a launchd script — importing it runs load_env() and sets
# module globals from the environment.  That's safe (no side effects beyond
# reading env + an optional .env file that won't exist in CI).  We import
# normally and then patch globals as needed per test.
import poll


# ---------------------------------------------------------------------------
# classify()
# ---------------------------------------------------------------------------

class TestClassify:
    """classify(path) -> event_type | None"""

    # Restore SKIP to its original value after each test that mutates it.
    def setup_method(self):
        self._orig_skip = set(poll.SKIP)

    def teardown_method(self):
        poll.SKIP = self._orig_skip

    # -- path must start with .github/workflows/ ----------------------------

    def test_non_workflow_path_returns_none(self):
        assert poll.classify("scripts/deploy.sh") is None

    def test_dependabot_path_returns_none(self):
        assert poll.classify(".github/dependabot.yml") is None

    def test_empty_path_returns_none(self):
        assert poll.classify("") is None

    # -- SKIP set -----------------------------------------------------------

    def test_skipped_workflow_returns_none(self):
        poll.SKIP = {"deploy-prod.yml"}
        assert poll.classify(".github/workflows/deploy-prod.yml") is None

    def test_non_skipped_workflow_not_blocked(self):
        poll.SKIP = {"deploy-prod.yml"}
        assert poll.classify(".github/workflows/ci.yml") == "ci_run"

    # -- keyword detection --------------------------------------------------

    def test_drift_in_name(self):
        assert poll.classify(".github/workflows/infra-drift.yml") == "drift"

    def test_drift_uppercase_tolerated(self):
        assert poll.classify(".github/workflows/DRIFT-check.yml") == "drift"

    def test_drill_in_name(self):
        assert poll.classify(".github/workflows/dr-drill-weekly.yml") == "drill"

    def test_drill_uppercase_tolerated(self):
        assert poll.classify(".github/workflows/DR-DRILL.yml") == "drill"

    def test_ci_run_fallthrough(self):
        assert poll.classify(".github/workflows/run-tests.yml") == "ci_run"

    def test_bare_filename_no_directory(self):
        # path has no directory component — rsplit gives base = full path
        assert poll.classify("run-tests.yml") is None

    def test_nested_path_uses_basename(self):
        # multiple slashes — rsplit(..., 1)[-1] must give the filename
        assert poll.classify(".github/workflows/sub/drift-check.yml") == "drift"

    # default SKIP set from the module (set at import time from env)
    def test_default_skip_blocks_deploy_prod(self):
        # Only valid if env wasn't overridden.  If SKIP is empty (env override)
        # this assertion would be wrong — guard accordingly.
        if "deploy-prod.yml" in self._orig_skip:
            assert poll.classify(".github/workflows/deploy-prod.yml") is None


# ---------------------------------------------------------------------------
# parse_ts()
# ---------------------------------------------------------------------------

class TestParseTs:

    def test_none_returns_none(self):
        assert poll.parse_ts(None) is None

    def test_empty_string_returns_none(self):
        assert poll.parse_ts("") is None

    def test_zulu_timestamp(self):
        dt = poll.parse_ts("2024-03-15T12:00:00Z")
        assert dt == datetime(2024, 3, 15, 12, 0, 0, tzinfo=timezone.utc)

    def test_offset_timestamp(self):
        dt = poll.parse_ts("2024-03-15T12:00:00+00:00")
        assert dt == datetime(2024, 3, 15, 12, 0, 0, tzinfo=timezone.utc)

    def test_returns_timezone_aware(self):
        dt = poll.parse_ts("2024-01-01T00:00:00Z")
        assert dt.tzinfo is not None

    def test_malformed_raises(self):
        try:
            poll.parse_ts("not-a-date")
            assert False, "expected ValueError"
        except ValueError:
            pass


# ---------------------------------------------------------------------------
# to_event()
# ---------------------------------------------------------------------------

_SAMPLE_RUN = {
    "id": 12345678,
    "run_attempt": 1,
    "name": "CI",
    "head_branch": "main",
    "event": "push",
    "head_sha": "abcdef1234567890",
    "conclusion": "success",
    "created_at": "2024-03-15T11:00:00Z",
    "run_started_at": "2024-03-15T11:01:00Z",
    "updated_at": "2024-03-15T11:05:00Z",
}


class TestToEvent:

    def test_schema_field(self):
        ev = poll.to_event(_SAMPLE_RUN, "ci_run")
        assert ev["schema"] == "ops_event/v1"

    def test_event_type(self):
        assert poll.to_event(_SAMPLE_RUN, "drift")["event_type"] == "drift"

    def test_status_uses_conclusion(self):
        assert poll.to_event(_SAMPLE_RUN, "ci_run")["status"] == "success"

    def test_status_falls_back_to_unknown(self):
        run = {**_SAMPLE_RUN, "conclusion": None}
        assert poll.to_event(run, "ci_run")["status"] == "unknown"

    def test_sha_truncated_to_7(self):
        ev = poll.to_event(_SAMPLE_RUN, "ci_run")
        assert ev["sha"] == "abcdef1"

    def test_sha_missing_gives_empty_string(self):
        run = {**_SAMPLE_RUN, "head_sha": None}
        assert poll.to_event(run, "ci_run")["sha"] == ""

    def test_run_id_is_string(self):
        ev = poll.to_event(_SAMPLE_RUN, "ci_run")
        assert isinstance(ev["run_id"], str)
        assert ev["run_id"] == "12345678"

    def test_attempt_is_string(self):
        assert isinstance(poll.to_event(_SAMPLE_RUN, "ci_run")["attempt"], str)

    def test_duration_ms_computed(self):
        ev = poll.to_event(_SAMPLE_RUN, "ci_run")
        # run_started_at -> updated_at = 4 min = 240 000 ms
        assert ev["duration_ms"] == "240000"

    def test_queue_ms_computed(self):
        ev = poll.to_event(_SAMPLE_RUN, "ci_run")
        # created_at -> run_started_at = 1 min = 60 000 ms
        assert ev["queue_ms"] == "60000"

    def test_duration_absent_when_timestamps_missing(self):
        run = {**_SAMPLE_RUN, "run_started_at": None, "updated_at": None}
        ev = poll.to_event(run, "ci_run")
        assert "duration_ms" not in ev

    def test_queue_absent_when_created_missing(self):
        run = {**_SAMPLE_RUN, "created_at": None}
        ev = poll.to_event(run, "ci_run")
        assert "queue_ms" not in ev

    def test_time_field_prefers_updated_at(self):
        ev = poll.to_event(_SAMPLE_RUN, "ci_run")
        assert ev["_time"] == _SAMPLE_RUN["updated_at"]

    def test_time_field_falls_back_to_created_at(self):
        run = {**_SAMPLE_RUN, "updated_at": None}
        ev = poll.to_event(run, "ci_run")
        assert ev["_time"] == _SAMPLE_RUN["created_at"]

    def test_msg_contains_event_type_and_conclusion(self):
        ev = poll.to_event(_SAMPLE_RUN, "ci_run")
        assert "ci_run" in ev["_msg"]
        assert "success" in ev["_msg"]

    def test_app_and_env_from_module_globals(self):
        ev = poll.to_event(_SAMPLE_RUN, "ci_run")
        assert ev["app"] == poll.APP
        assert ev["env"] == poll.ENV

    def test_service_and_environment_join_traces_and_metrics(self):
        # LOG-STANDARD cross-signal keys; same service as the podcast deploy emitter.
        ev = poll.to_event(_SAMPLE_RUN, "ci_run")
        assert ev["service"] == poll.SERVICE == "podcast-ci"
        assert ev["environment"] == poll.ENV


# ---------------------------------------------------------------------------
# poll_once() — mocked I/O
# ---------------------------------------------------------------------------

def _make_run(**over):
    base = {
        "id": 1,
        "run_attempt": 1,
        "status": "completed",
        "conclusion": "success",
        "path": ".github/workflows/ci.yml",
        "name": "CI",
        "head_branch": "main",
        "event": "push",
        "head_sha": "abc1234",
        "created_at": "2024-03-15T11:00:00Z",
        "run_started_at": "2024-03-15T11:01:00Z",
        "updated_at": "2024-03-15T11:05:00Z",
    }
    base.update(over)
    return base


class TestPollOnce:

    REPO = "chipi/podcast_scraper"

    def _run(self, fake_runs, state=None, emit_raises=None):
        """Run poll_once over one repo with fetch_runs and emit mocked. `state` is that
        repo's {"since", "seen"}; returns (emit mock, the repo's saved state)."""
        if state is None:
            state = {"since": None, "seen": {}}
        full = {"repos": {self.REPO: state}}
        saved = {}

        def fake_save(s):
            saved.update(s["repos"].get(self.REPO, {}))

        with patch.object(poll, "REPOS", [self.REPO]), \
             patch.object(poll, "fetch_runs", return_value=fake_runs), \
             patch.object(poll, "emit") as mock_emit, \
             patch.object(poll, "save_state", side_effect=fake_save):
            if emit_raises:
                mock_emit.side_effect = emit_raises
                try:
                    poll.poll_once(full)
                except Exception:
                    pass
            else:
                poll.poll_once(full)
            return mock_emit, saved

    # -- happy path ---------------------------------------------------------

    def test_completed_ci_run_emitted(self):
        mock_emit, _ = self._run([_make_run()])
        mock_emit.assert_called_once()
        events = mock_emit.call_args[0][0]
        assert len(events) == 1
        assert events[0]["event_type"] == "ci_run"

    def test_incomplete_run_skipped(self):
        mock_emit, _ = self._run([_make_run(status="in_progress")])
        events = mock_emit.call_args[0][0]
        assert events == []

    def test_skipped_workflow_not_emitted(self):
        orig_skip = poll.SKIP
        try:
            poll.SKIP = {"ci.yml"}
            mock_emit, _ = self._run([_make_run()])
            assert mock_emit.call_args[0][0] == []
        finally:
            poll.SKIP = orig_skip

    def test_already_seen_run_deduplicated(self):
        state = {"since": None, "seen": {"1:1": "2024-03-15T11:00:00Z"}}
        mock_emit, _ = self._run([_make_run()], state=state)
        assert mock_emit.call_args[0][0] == []

    def test_re_run_new_attempt_not_deduplicated(self):
        # attempt 1 seen, attempt 2 is new
        state = {"since": None, "seen": {"1:1": "2024-03-15T11:00:00Z"}}
        mock_emit, _ = self._run([_make_run(run_attempt=2)], state=state)
        events = mock_emit.call_args[0][0]
        assert len(events) == 1

    def test_seen_set_updated_after_emit(self):
        # created_at must be recent or the prune step will drop it before save
        recent = (datetime.now(timezone.utc) - timedelta(hours=1)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        run = _make_run(created_at=recent, run_started_at=recent, updated_at=recent)
        _, saved = self._run([run])
        assert "1:1" in saved["seen"]

    def test_since_cursor_advanced(self):
        _, saved = self._run([])
        # cursor should be a UTC ISO string
        dt = datetime.fromisoformat(saved["since"].replace("Z", "+00:00"))
        assert dt.tzinfo is not None

    def test_drift_path_classifies_as_drift(self):
        run = _make_run(path=".github/workflows/infra-drift.yml")
        mock_emit, _ = self._run([run])
        events = mock_emit.call_args[0][0]
        assert events[0]["event_type"] == "drift"

    def test_drill_path_classifies_as_drill(self):
        run = _make_run(path=".github/workflows/dr-drill.yml")
        mock_emit, _ = self._run([run])
        events = mock_emit.call_args[0][0]
        assert events[0]["event_type"] == "drill"

    # -- stale-seen pruning -------------------------------------------------

    def test_old_seen_entries_pruned(self):
        old_ts = (datetime.now(timezone.utc) - timedelta(days=30)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        state = {
            "since": None,
            "seen": {"999:1": old_ts},
        }
        _, saved = self._run([], state=state)
        assert "999:1" not in saved["seen"]

    def test_recent_seen_entries_kept(self):
        recent_ts = (datetime.now(timezone.utc) - timedelta(hours=1)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        state = {
            "since": None,
            "seen": {"999:1": recent_ts},
        }
        _, saved = self._run([], state=state)
        assert "999:1" in saved["seen"]

    # -- API-error path: must degrade, not crash ----------------------------

    def test_http_error_on_one_repo_does_not_stop_the_others(self):
        """A repo the token cannot see yet (404) or a rate limit (403) is logged and keeps
        its old cursor, so its window is re-scanned next poll; the other repos still run."""
        import urllib.error
        http_err = urllib.error.HTTPError(
            url="https://api.github.com/...", code=404, msg="Not Found",
            hdrs=None, fp=None,  # type: ignore[arg-type]
        )
        old = {"since": "2026-10-28T10:00:00Z", "seen": {}}
        state = {"repos": {"chipi/infra": dict(old)}}

        def fake_fetch(repo, since_iso):
            if repo == "chipi/infra":
                raise http_err
            return [_make_run()]

        with patch.object(poll, "REPOS", ["chipi/infra", "chipi/podcast_scraper"]), \
             patch.object(poll, "fetch_runs", side_effect=fake_fetch), \
             patch.object(poll, "emit") as mock_emit, \
             patch.object(poll, "save_state"):
            poll.poll_once(state)
        assert state["repos"]["chipi/infra"] == old
        events = mock_emit.call_args[0][0]
        assert [e["repo"] for e in events] == ["chipi/podcast_scraper"]

    def test_each_repo_polled_with_its_own_cursor(self):
        state = {"repos": {"a/x": {"since": "2026-10-28T10:00:00Z", "seen": {}},
                           "b/y": {"since": "2026-10-28T11:00:00Z", "seen": {}}}}
        calls = []
        with patch.object(poll, "REPOS", ["a/x", "b/y"]), \
             patch.object(poll, "OVERLAP_MIN", 0), \
             patch.object(poll, "fetch_runs", side_effect=lambda r, s: calls.append((r, s)) or []), \
             patch.object(poll, "emit"), \
             patch.object(poll, "save_state"):
            poll.poll_once(state)
        assert calls == [("a/x", "2026-10-28T10:00:00Z"), ("b/y", "2026-10-28T11:00:00Z")]

    def test_events_carry_their_repo(self):
        with patch.object(poll, "REPOS", ["chipi/infra"]), \
             patch.object(poll, "fetch_runs", return_value=[_make_run(path=".github/workflows/infra-drift.yml")]), \
             patch.object(poll, "emit") as mock_emit, \
             patch.object(poll, "save_state"):
            poll.poll_once({"repos": {}})
        ev = mock_emit.call_args[0][0][0]
        assert (ev["repo"], ev["event_type"]) == ("chipi/infra", "drift")

    def test_multiple_runs_all_emitted(self):
        runs = [_make_run(id=i, run_attempt=1) for i in range(1, 4)]
        mock_emit, _ = self._run(runs)
        events = mock_emit.call_args[0][0]
        assert len(events) == 3


class TestStateMigration:
    """A single-repo state file becomes the first repo's entry: no re-scan, no re-emit."""

    def test_legacy_state_becomes_first_repo(self, tmp_path):
        f = tmp_path / "state.json"
        f.write_text(json.dumps({"since": "2026-10-28T19:00:00Z", "seen": {"1:1": "2026-10-28T18:00:00Z"}}))
        with patch.object(poll, "STATE_FILE", str(f)), \
             patch.object(poll, "REPOS", ["chipi/podcast_scraper", "chipi/infra"]):
            st = poll.load_state()
        assert st == {"repos": {"chipi/podcast_scraper": {"since": "2026-10-28T19:00:00Z",
                                                          "seen": {"1:1": "2026-10-28T18:00:00Z"}}}}

    def test_missing_state_file_is_empty(self, tmp_path):
        with patch.object(poll, "STATE_FILE", str(tmp_path / "none.json")):
            assert poll.load_state() == {"repos": {}}

    def test_new_shape_loaded_as_is(self, tmp_path):
        f = tmp_path / "state.json"
        new = {"repos": {"chipi/infra": {"since": None, "seen": {}}}}
        f.write_text(json.dumps(new))
        with patch.object(poll, "STATE_FILE", str(f)):
            assert poll.load_state() == new


def test_default_skip_covers_every_push_path_workflow():
    """The eight workflows that call emit-ops-event (chipi/infra) push their own events."""
    for wf in ("deploy-prod.yml", "deploy-player.yml", "deploy-operator.yml", "deploy-litellm.yml",
               "deploy-config.yml", "backup-corpus-prod.yml", "backup-player-appdata-prod.yml",
               "backup-operator-appdata-prod.yml"):
        assert poll.classify(".github/workflows/" + wf) is None, wf


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-v"]))
