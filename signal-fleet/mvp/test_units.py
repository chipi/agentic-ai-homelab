"""Offline unit checks for the DETERMINISTIC triage-enhancement helpers (no LLM,
no network, no creds). Companion to eval_hardening.py (real-signal dataset) — this
covers the pure functions the enhancements add, stage by stage.

  SF_OBSERV_DISABLED=1 python3 test_units.py            # all, non-zero on failure

Each enhancement item (#1..#8, docs/wip/signal-fleet-triage-enhancements.md) adds a
TestCase here as it lands; same input → same verdict, every run.
"""
import os
import unittest

os.environ.setdefault("SF_OBSERV_DISABLED", "1")

import actions
import correlate


# ── shared frozen event payloads (Sentry/GlitchTip API shape) ────────────────
def _frame(fn, func, line, in_app=True):
    return {"filename": fn, "function": func, "lineNo": line, "in_app": in_app}


CHAINED_EVENT = {
    "platform": "python",
    "culprit": "service.run_feeds",
    "message": "Multi-feed run finished with one or more feed failures.",
    "tags": [{"key": "release", "value": "sha-abc1234"},
             {"key": "environment", "value": "prod"}],
    "contexts": {"trace": {"trace_id": "deadbeef"}},
    "entries": [{
        "type": "exception",
        "data": {"values": [
            # values[0] = INNERMOST root cause (Sentry: oldest first)
            {"type": "TimeoutError", "value": "The write operation timed out",
             "stacktrace": {"frames": [
                 _frame("service.py", "run_feeds", 200),
                 _frame("transcribe.py", "_call_deepgram", 88)]}},
            # values[-1] = OUTERMOST wrapper actually logged
            {"type": "FeedRunError", "value": "one or more feed failures",
             "stacktrace": {"frames": [
                 _frame("main.py", "main", 10),
                 _frame("service.py", "run_feeds", 205)]}},
        ]},
    }],
}


class TestCauseExtraction(unittest.TestCase):
    """#5 — innermost __cause__, distinct from the outer wrapper."""

    def setUp(self):
        self.s = correlate._summarize_event(CHAINED_EVENT)

    def test_inner_cause_is_values0(self):
        self.assertEqual(self.s["cause_type"], "TimeoutError")
        self.assertEqual(self.s["cause_value"], "The write operation timed out")

    def test_cause_frame_is_inner_crash_site_no_lineno(self):
        # top app frame of the INNER cause = last frame, WITHOUT lineNo
        self.assertEqual(self.s["cause_frame"], "transcribe.py _call_deepgram")
        self.assertNotIn("88", self.s["cause_frame"])

    def test_outer_exc_type_and_top_frame(self):
        # what norm_key (#1) keys on = the outermost raised type + its crash frame
        self.assertEqual(self.s["exc_type"], "FeedRunError")
        self.assertEqual(self.s["top_frame"], "service.py run_feeds")

    def test_chain_depth(self):
        self.assertEqual(self.s["chain_depth"], 2)

    def test_single_exception_inner_equals_outer(self):
        ev = {"entries": [{"type": "exception", "data": {"values": [
            {"type": "ValueError", "value": "boom",
             "stacktrace": {"frames": [_frame("x.py", "f", 3)]}}]}}]}
        s = correlate._summarize_event(ev)
        self.assertEqual(s["cause_type"], "ValueError")
        self.assertEqual(s["exc_type"], "ValueError")
        self.assertEqual(s["chain_depth"], 1)

    def test_no_exception_event_degrades(self):
        s = correlate._summarize_event({"message": "just a log", "tags": []})
        self.assertIsNone(s["cause_type"])
        self.assertIsNone(s["exc_type"])
        self.assertEqual(s["top_frame"], "")
        self.assertEqual(s["cause_frame"], "")

    def test_top_app_frame_prefers_last_in_app(self):
        # crash site is a library frame; the top APP frame is the last in_app one
        stack = {"frames": [
            _frame("app.py", "handler", 5, in_app=True),
            _frame("urllib.py", "urlopen", 99, in_app=False)]}
        self.assertEqual(correlate._top_app_frame(stack), "app.py handler")


class TestCodeVersion(unittest.TestCase):
    """#6 — code_version stamped from the event and the signal."""

    def test_code_version_from_event_tags(self):
        s = correlate._summarize_event(CHAINED_EVENT)
        self.assertEqual(s["code_version"], "sha-abc1234")

    def test_signal_code_version_from_last_release(self):
        sig = {"raw": {"lastRelease": {"shortVersion": "sha-9f9f9f9"},
                       "firstRelease": {"shortVersion": "sha-000"}}}
        self.assertEqual(actions.signal_code_version(sig), "sha-9f9f9f9")

    def test_signal_code_version_falls_back_to_first_release(self):
        sig = {"raw": {"firstRelease": {"version": "sha-111"}}}
        self.assertEqual(actions.signal_code_version(sig), "sha-111")

    def test_signal_code_version_absent(self):
        self.assertEqual(actions.signal_code_version({"raw": {}}), "")

    def test_build_issue_stamps_code_version(self):
        sig = {"alertname": "x", "source": "glitchtip", "fingerprint": "glitchtip:P-1",
               "raw": {"lastRelease": {"shortVersion": "sha-abc"}}}
        issue = actions.build_issue(sig, {"symptom": "s", "area": "backend",
                                          "acceptance": [], "evidence": []})
        self.assertIn("sha-abc", issue["body"])
        self.assertIn("Code version", issue["body"])


import filing  # noqa: E402


def _psig(fp, title, culprit="podcast.pipeline.audio in _evict", mtype="ValueError",
          src="glitchtip", count="3"):
    """A GlitchTip-shaped signal (as sources.to_error_signal builds)."""
    return {"fingerprint": fp, "source": src, "alertname": title,
            "labels": {"project": "podcast", "level": "error", "culprit": culprit,
                       "count": count},
            "raw": {"metadata": {"type": mtype}, "culprit": culprit}}


# the handover's real clusters (scrubbed), one signal per occurrence
_AUDIO = [
    _psig("glitchtip:PODCAST-PIPELINE-3F",
          "Audio eviction size mismatch: cold (69782850) != local (65937149) for /app/output/feeds/rss_feeds.npr.org_7abc"),
    _psig("glitchtip:PODCAST-PIPELINE-3E",
          "Audio eviction size mismatch: cold (72110022) != local (65937149) for /app/output/feeds/rss_feeds.bbc.co.uk_3def"),
    _psig("glitchtip:PODCAST-PIPELINE-36",
          "Audio eviction size mismatch: cold (551488) != local (12345) for /app/output/feeds/rss_feeds.npr.org_9zzz"),
]
_ADR = [
    _psig("glitchtip:PODCAST-BS", "Failed to generate and validate summary for episode 6a319f2260728bbcda06b463",
          culprit="metadata_generation in _generate_and_validate_summary", mtype="RecoverableSummarizationError"),
    _psig("glitchtip:PODCAST-PIPELINE-8", "Failed to generate and validate summary for episode 6eb845ef30754858",
          culprit="metadata_generation in _generate_and_validate_summary", mtype="RecoverableSummarizationError"),
]


class TestNormalizedKey(unittest.TestCase):
    """#1 — the ~40% lever. Real handover clusters collapse; different bugs don't."""

    def test_audio_cluster_collapses_to_one_key(self):
        keys = {filing.normalized_key(s) for s in _AUDIO}
        self.assertEqual(len(keys), 1, f"audio-eviction #1840-49 must collapse, got {keys}")

    def test_audio_golden_hash(self):
        # golden — a change to the regex list or extractor must break this LOUDLY
        self.assertEqual(filing.normalized_key(_AUDIO[0]), "v1:71c67e6fb210")

    def test_decimal_vs_hex_bytecount_same_placeholder(self):
        # regression guard for the bug golden-testing caught: an 8-digit DECIMAL
        # byte-count must normalize the SAME as a 6-digit one (both <n>, not <id>)
        self.assertEqual(filing.normalized_key(_AUDIO[0]), filing.normalized_key(_AUDIO[2]))

    def test_adr148_cluster_collapses(self):
        keys = {filing.normalized_key(s) for s in _ADR}
        self.assertEqual(len(keys), 1)
        self.assertEqual(filing.normalized_key(_ADR[0]), "v1:96b014ae8606")

    def test_different_bug_does_not_collapse(self):
        other = _psig("glitchtip:PLAYER-9", "TypeError: Cannot read properties of null (reading id)",
                      culprit="render", mtype="TypeError")
        self.assertNotEqual(filing.normalized_key(other), filing.normalized_key(_AUDIO[0]))

    def test_shared_helper_frame_same_exc_diff_skeleton_stay_apart(self):
        # review R4b: two different bugs, SAME exc_type + SAME crash helper, but
        # different messages must NOT collapse — the skeleton carries the load
        a = _psig("glitchtip:P-A", "Search index build failed", culprit="http_util in get_json", mtype="HTTPError")
        b = _psig("glitchtip:P-B", "Feed metadata fetch failed", culprit="http_util in get_json", mtype="HTTPError")
        self.assertNotEqual(filing.normalized_key(a), filing.normalized_key(b))

    def test_count_volatility_same_key(self):
        self.assertEqual(filing.normalized_key(_psig("x", "same title", count="42")),
                         filing.normalized_key(_psig("y", "same title", count="43")))

    def test_cross_source_never_collapses(self):
        gt = _psig("a", "same title", src="glitchtip")
        gf = _psig("a", "same title", src="grafana")
        self.assertNotEqual(filing.normalized_key(gt), filing.normalized_key(gf))

    def test_empty_key_when_nothing_stable(self):
        self.assertEqual(filing.normalized_key({"source": "grafana", "alertname": "", "raw": {}}), "")

    def test_no_volatile_tokens_passthrough(self):
        self.assertEqual(filing._normalize_skeleton("Database connection refused"),
                         "database connection refused")

    def test_event_summary_overrides_raw_metadata(self):
        # when the richer #5 summary is available it wins over raw.metadata.type
        s = _psig("q", "boom", mtype="ValueError")
        k_raw = filing.normalized_key(s)
        k_es = filing.normalized_key(s, event_summary={"exc_type": "KeyError", "top_frame": "z.py f"})
        self.assertNotEqual(k_raw, k_es)


class TestLedgerDedup(unittest.TestCase):
    """#1 ledger dimension: newest-row, never-inherit-MUTED across a fuzzy hash,
    old-schema (pre-#1) filed.tsv safety. `_gh`/`issue_state` mocked — no network."""

    def setUp(self):
        import tempfile
        self._tmp = tempfile.NamedTemporaryFile("w", suffix=".tsv", delete=False)
        self._tmp.close()
        self._orig = (filing.FILED, filing._gh, filing.issue_state)
        filing.FILED = self._tmp.name
        self.gh_calls = []
        filing._gh = lambda m, p, payload=None: (self.gh_calls.append((m, p, payload))
                                                  or {"number": 99, "html_url": "u/99"})

    def tearDown(self):
        filing.FILED, filing._gh, filing.issue_state = self._orig
        os.unlink(self._tmp.name)

    def _seed(self, rows):
        filing._ledger_write(rows)

    def test_newest_row_wins_on_group_key(self):
        self._seed([
            {"fingerprint": "fp1", "repo": "r", "issue": "10", "group_key": "gk", "norm_key": ""},
            {"fingerprint": "fp2", "repo": "r", "issue": "20", "group_key": "gk", "norm_key": ""},
        ])
        hit = filing.ledger_lookup("nomatch", group_key="gk")
        self.assertEqual(hit["issue"], "20")
        self.assertEqual(hit["_dim"], "group_key")

    def test_norm_key_dimension_matches(self):
        self._seed([{"fingerprint": "fpA", "repo": "r", "issue": "7", "group_key": "", "norm_key": "v1:abc"}])
        hit = filing.ledger_lookup("other", group_key="", norm_key="v1:abc")
        self.assertEqual(hit["issue"], "7")
        self.assertEqual(hit["_dim"], "norm_key")

    def test_empty_norm_key_never_matches(self):
        self._seed([{"fingerprint": "fpA", "repo": "r", "issue": "7", "group_key": "", "norm_key": ""}])
        self.assertIsNone(filing.ledger_lookup("other", group_key="", norm_key=""))

    def test_old_schema_filed_tsv_no_keyerror(self):
        # a pre-#1 6-column filed.tsv: rows zip short, lack norm_key; reads must .get
        with open(filing.FILED, "w") as f:
            f.write("\t".join(filing.FILED_COLS[:-1]) + "\n")           # 6-col header
            f.write("fp1\tr\t10\t\t2026-01-01\t\n")                      # 6-col row
        self.assertIsNone(filing.ledger_lookup("nomatch", norm_key="v1:x"))
        # a fingerprint hit on an old row still works and reports the dimension
        self.assertEqual(filing.ledger_lookup("fp1")["_dim"], "fingerprint")

    def test_norm_key_hit_never_inherits_mute(self):
        # review R3: a norm_key (fuzzy) hit on a MUTED issue must file FRESH, not
        # inherit the mute — else a different bug is silently buried forever
        sig = _psig("glitchtip:PODCAST-NEW", "Audio eviction size mismatch: cold (999999) != local (1) for /a/b/c")
        nk = filing.normalized_key(sig)
        self._seed([{"fingerprint": "glitchtip:PODCAST-OLD", "repo": "chipi/podcast_scraper",
                     "issue": "5", "group_key": "", "norm_key": nk}])
        filing.issue_state = lambda repo, num: {"state": "open", "labels": [filing.MUTE_LABEL],
                                                "closed_at": None, "url": ""}
        out = filing.file_or_update(sig, {"title": "Audio eviction size mismatch on npr feed",
                                          "body": "b"}, "bug")
        self.assertTrue(out.startswith("FILED"), f"expected fresh file, got: {out}")
        self.assertTrue(any(m == "POST" and "/issues" in p for m, p, _ in self.gh_calls))

    def test_exact_fp_hit_DOES_honor_mute(self):
        # control: an EXACT fingerprint hit on a muted issue is honored (no new file)
        sig = _psig("glitchtip:PODCAST-OLD", "whatever")
        self._seed([{"fingerprint": "glitchtip:PODCAST-OLD", "repo": "chipi/podcast_scraper",
                     "issue": "5", "group_key": "", "norm_key": ""}])
        filing.issue_state = lambda repo, num: {"state": "open", "labels": [filing.MUTE_LABEL],
                                                "closed_at": None, "url": ""}
        out = filing.file_or_update(sig, {"title": "t", "body": "b"}, "bug")
        self.assertTrue(out.startswith("MUTED"), f"expected mute honored, got: {out}")


def _lowsig(fp, title, count="1", users=0, culprit=""):
    return {"fingerprint": fp, "source": "glitchtip", "alertname": title,
            "labels": {"project": "podcast", "count": count},
            "raw": {"count": count, "userCount": users, "culprit": culprit}}


class TestLowSignal(unittest.TestCase):
    """#4 — low-signal classifier + per-bucket rollup + promotion. `_gh`/`issue_state`
    mocked; temp FILED ledger. Rollup is a FILE (never a dismiss)."""

    def setUp(self):
        import tempfile
        self._tmp = tempfile.NamedTemporaryFile("w", suffix=".tsv", delete=False)
        self._tmp.close()
        self._orig = (filing.FILED, filing._gh, filing.issue_state)
        filing.FILED = self._tmp.name
        self.gh = []
        self._num = [100]

        def fake_gh(m, p, payload=None):
            self.gh.append((m, p, payload))
            self._num[0] += 1
            return {"number": self._num[0], "html_url": f"u/{self._num[0]}"}
        filing._gh = fake_gh
        filing.issue_state = lambda repo, num: {"state": "open", "labels": [],
                                                "closed_at": None, "url": ""}

    def tearDown(self):
        filing.FILED, filing._gh, filing.issue_state = self._orig
        os.unlink(self._tmp.name)

    # classifier
    def test_low_signal_true_for_single_unsymbolicated(self):
        self.assertTrue(filing.low_signal(_lowsig("glitchtip:P-1", "one-off crash")))

    def test_not_low_signal_when_recurring(self):
        self.assertFalse(filing.low_signal(_lowsig("glitchtip:P-1", "x", count="42")))

    def test_not_low_signal_when_users_affected(self):
        self.assertFalse(filing.low_signal(_lowsig("glitchtip:P-1", "x", users=3)))

    def test_not_low_signal_when_symbolicated(self):
        self.assertFalse(filing.low_signal(_lowsig("glitchtip:P-1", "x", culprit="mod.fn")))

    # routing
    def test_first_low_signal_opens_rollup(self):
        out = filing.file_or_update(_lowsig("glitchtip:PODCAST-A", "one-off crash A"),
                                    {"title": "one-off A", "body": "b"}, "bug")
        self.assertTrue(out.startswith("ROLLUP-OPENED"), out)
        opened = [p for m, p, _ in self.gh if m == "POST" and p.endswith("/issues")]
        self.assertEqual(len(opened), 1)

    def test_second_low_signal_same_bucket_folds(self):
        filing.file_or_update(_lowsig("glitchtip:PODCAST-A", "one-off A"),
                              {"title": "A", "body": "b"}, "bug")
        out = filing.file_or_update(_lowsig("glitchtip:PODCAST-B", "one-off B"),
                                    {"title": "B", "body": "b"}, "bug")
        self.assertTrue(out.startswith("ROLLED-UP"), out)
        # exactly ONE issue created total; the 2nd folded as a comment
        created = [p for m, p, _ in self.gh if m == "POST" and p.endswith("/issues")]
        self.assertEqual(len(created), 1)

    def test_not_low_signal_files_normally(self):
        out = filing.file_or_update(_lowsig("glitchtip:PODCAST-C", "recurring bug", count="42"),
                                    {"title": "C", "body": "b"}, "bug")
        self.assertTrue(out.startswith("FILED"), out)

    def test_promotion_out_of_rollup(self):
        # seed: this fp is already folded into the podcast rollup (issue 50)
        nk = filing.normalized_key(_lowsig("glitchtip:PODCAST-Z", "flaky thing"))
        filing._ledger_write([{"fingerprint": "glitchtip:PODCAST-Z", "repo": "chipi/podcast_scraper",
                               "issue": "50", "group_key": "low-signal:podcast",
                               "last_comment_day": "", "norm_key": nk}])
        # it recurs at count=12 → no longer low-signal → must break OUT to its own issue
        out = filing.file_or_update(_lowsig("glitchtip:PODCAST-Z", "flaky thing", count="12"),
                                    {"title": "flaky thing", "body": "b"}, "bug")
        self.assertTrue(out.startswith("FILED"), out)
        created = [payload for m, p, payload in self.gh if m == "POST" and p.endswith("/issues")]
        self.assertEqual(len(created), 1)
        self.assertIn("Promoted out of low-signal rollup", created[0]["body"])


class TestCrossLinkAndLabels(unittest.TestCase):
    """#7 cross-link + #8 area label / ensure-labels / milestone. Path-routing
    `_gh` mock; nothing hits the network."""

    def setUp(self):
        import tempfile
        self._tmp = tempfile.NamedTemporaryFile("w", suffix=".tsv", delete=False)
        self._tmp.close()
        self._orig = (filing.FILED, filing._gh, filing.issue_state)
        filing.FILED = self._tmp.name
        self.search_items, self.milestones, self.created = [], [], []

        def fake_gh(m, p, payload=None):
            if p.startswith("/search/issues"):
                return {"items": self.search_items}
            if "/milestones" in p:
                return self.milestones
            if p.endswith("/labels"):
                return {}
            if p.endswith("/issues") and m == "POST":
                self.created.append(payload)
                return {"number": 200, "html_url": "u/200"}
            return {}
        filing._gh = fake_gh
        filing.issue_state = lambda r, n: {"state": "open", "labels": [], "closed_at": None, "url": ""}

    def tearDown(self):
        filing.FILED, filing._gh, filing.issue_state = self._orig
        os.unlink(self._tmp.name)

    def _bug(self):
        # not low-signal (count 42), symbolicated → goes through the create path
        return _psig("glitchtip:PODCAST-XL", "Summary schema validation failed",
                     culprit="metadata_generation in _generate_and_validate_summary", count="42")

    def test_build_issue_adds_area_label(self):
        iss = actions.build_issue({"fingerprint": "f", "source": "glitchtip", "raw": {}},
                                  {"title": "t", "area": "Backend", "acceptance": [], "evidence": []})
        self.assertIn("area:backend", iss["labels"])

    def test_build_issue_no_area_no_label(self):
        iss = actions.build_issue({"fingerprint": "f", "source": "glitchtip", "raw": {}},
                                  {"title": "t", "area": "", "acceptance": [], "evidence": []})
        self.assertFalse(any(l.startswith("area:") for l in iss["labels"]))

    def test_cross_link_appends_related(self):
        self.search_items = [{"number": 7}, {"number": 9}]
        filing.file_or_update(self._bug(), {"title": "t", "body": "b"}, "bug")
        self.assertIn("Possibly related:", self.created[0]["body"])
        self.assertIn("#7", self.created[0]["body"])

    def test_no_related_when_none_found(self):
        self.search_items = []
        filing.file_or_update(self._bug(), {"title": "t", "body": "b"}, "bug")
        self.assertNotIn("Possibly related:", self.created[0]["body"])

    def test_milestone_resolved_into_payload(self):
        self.milestones = [{"title": "triage", "number": 3}]
        filing.file_or_update(self._bug(), {"title": "t", "body": "b"}, "bug")
        self.assertEqual(self.created[0].get("milestone"), 3)

    def test_no_milestone_key_when_absent(self):
        self.milestones = []
        filing.file_or_update(self._bug(), {"title": "t", "body": "b"}, "bug")
        self.assertNotIn("milestone", self.created[0])

    def test_related_skipped_for_short_or_missing_frame(self):
        self.assertEqual(filing._related_issues("r", {"raw": {"culprit": ""}}), [])


def _grafana(alertname, instance="box-a"):
    """A Grafana signal as sources.to_signal builds it — NO count/userCount/culprit."""
    labels = {"alertname": alertname, "instance": instance}
    return {"fingerprint": f"grafana:{alertname}-{instance}", "source": "grafana",
            "alertname": alertname, "labels": labels, "summary": alertname,
            "raw": {"labels": labels}}


class TestSourceGuards(unittest.TestCase):
    """Fable pre-deploy review F1/F2/F3 — the GlitchTip-shape assumptions must not
    misfire on Grafana/other sources. These are the Grafana-shaped cases the original
    44 tests structurally lacked."""

    def setUp(self):
        import tempfile
        self._tmp = tempfile.NamedTemporaryFile("w", suffix=".tsv", delete=False)
        self._tmp.close()
        self._orig = (filing.FILED, filing._gh, filing.issue_state)
        filing.FILED = self._tmp.name
        self.gh = []
        self._num = [300]

        def fake_gh(m, p, payload=None):
            self.gh.append((m, p, payload))
            self._num[0] += 1
            return {"number": self._num[0], "html_url": f"u/{self._num[0]}"}
        filing._gh = fake_gh
        filing.issue_state = lambda r, n: {"state": "open", "labels": [], "closed_at": None, "url": ""}

    def tearDown(self):
        filing.FILED, filing._gh, filing.issue_state = self._orig
        os.unlink(self._tmp.name)

    # F1 — Grafana / evidence-absent must NOT be low-signal
    def test_grafana_signal_is_never_low_signal(self):
        self.assertFalse(filing.low_signal(_grafana("Orrery launch data stale")))

    def test_grafana_file_gets_its_own_issue_not_rollup(self):
        out = filing.file_or_update(_grafana("Orrery launch data stale"),
                                    {"title": "orrery stale", "body": "b"}, "config-enhancement")
        self.assertFalse(out.startswith(("ROLLUP", "ROLLED")), out)

    def test_glitchtip_without_count_not_low_signal(self):
        # evidence-present required — a malformed glitchtip signal isn't "low" by absence
        sig = {"fingerprint": "glitchtip:P-1", "source": "glitchtip", "alertname": "x",
               "labels": {}, "raw": {}}
        self.assertFalse(filing.low_signal(sig))

    def test_substrate_triager_down_signal_not_low_signal(self):
        # the fail-closed substrate issue (orchestrator._file_triager_down) is grafana-source
        sig = {"fingerprint": "grafana:fleet-triager-down", "source": "grafana",
               "alertname": "signal-fleet triager unavailable", "labels": {"meta": "true"},
               "raw": {}}
        self.assertFalse(filing.low_signal(sig))

    # F2 — escalation / substrate never rolled up even when low-signal-shaped
    def test_escalation_not_rolled_up(self):
        low = _lowsig("glitchtip:PODCAST-ESC", "one-off, needs a human")
        out = filing.file_or_update(low, {"title": "escalation X", "body": "Q for operator"}, "escalation")
        self.assertFalse(out.startswith(("ROLLUP", "ROLLED")), out)

    # F3 — Grafana norm_key must separate instances
    def test_grafana_norm_key_separates_instances(self):
        a = filing.normalized_key(_grafana("DiskWillFill", "box-a"))
        b = filing.normalized_key(_grafana("DiskWillFill", "box-b"))
        self.assertTrue(a and b and a != b, f"instances must not collapse: {a} vs {b}")

    def test_grafana_no_instance_still_keys(self):
        sig = {"source": "grafana", "alertname": "SomeAlert", "labels": {}, "raw": {}}
        self.assertTrue(filing.normalized_key(sig).startswith("v1:"))

    def test_glitchtip_golden_hash_unchanged_by_f3(self):
        # F3 appends instance for grafana ONLY — GlitchTip keys must stay byte-identical
        self.assertEqual(filing.normalized_key(_AUDIO[0]), "v1:71c67e6fb210")

    # promotion-before-mute: a muted rollup must not bury a threshold-crossing bug
    def test_promotion_beats_mute(self):
        sig = _lowsig("glitchtip:PODCAST-PROMO", "flaky", count="20")   # crossed threshold
        nk = filing.normalized_key(sig)
        filing._ledger_write([{"fingerprint": "glitchtip:PODCAST-PROMO", "repo": "chipi/podcast_scraper",
                               "issue": "5", "group_key": "low-signal:podcast",
                               "last_comment_day": "", "norm_key": nk}])
        filing.issue_state = lambda r, n: {"state": "open", "labels": [filing.MUTE_LABEL],
                                           "closed_at": None, "url": ""}
        out = filing.file_or_update(sig, {"title": "flaky", "body": "b"}, "bug")
        self.assertTrue(out.startswith("FILED"), f"promotion must beat mute, got: {out}")


class TestAlertKeyDedup(unittest.TestCase):
    """#9 alert_key: the same alert with a new fingerprint and no norm_key comments on
    the OPEN issue already tracking it (the #48 -> #72 case). `_gh`/`issue_state` mocked."""

    def setUp(self):
        import tempfile
        self._tmp = tempfile.NamedTemporaryFile("w", suffix=".tsv", delete=False)
        self._tmp.close()
        self._orig = (filing.FILED, filing._gh, filing.issue_state)
        self._env = os.environ.get("SF_ALERT_KEY_DEDUP")
        os.environ.pop("SF_ALERT_KEY_DEDUP", None)
        filing.FILED = self._tmp.name
        self.gh = []
        filing._gh = lambda m, p, payload=None: (self.gh.append((m, p, payload))
                                                 or {"number": 99, "html_url": "u/99"})
        self.open = {"48"}
        filing.issue_state = lambda repo, num: {
            "state": "open" if str(num) in self.open else "closed",
            "labels": ["triage-fleet/muted"] if str(num) == "77" else [],
            "closed_at": None, "url": ""}
        self.repo = "chipi/agentic-ai-homelab"
        self.ak = filing.alert_key(self.repo, "grafana", "Enrichment/job drain paused")

    def tearDown(self):
        filing.FILED, filing._gh, filing.issue_state = self._orig
        if self._env is None:
            os.environ.pop("SF_ALERT_KEY_DEDUP", None)
        else:
            os.environ["SF_ALERT_KEY_DEDUP"] = self._env
        os.unlink(self._tmp.name)

    def _signal(self, fp="grafana:57cf073a75e944ec"):
        return {"fingerprint": fp, "source": "grafana", "alertname": "Enrichment/job drain paused",
                "labels": {"instance": "homelab"}}

    def _seed_48(self, issue="48"):
        filing._ledger_write([{"fingerprint": "grafana:ab6d6d8f8b808627", "repo": self.repo,
                               "issue": issue, "group_key": "", "norm_key": "",
                               "alert_key": self.ak}])

    def test_key_ignores_volatile_tokens_but_not_repo(self):
        a = filing.alert_key("r", "glitchtip", "GI INVARIANT VIOLATED [3da68c36-8ac2-11f1-b9f0-57c51db071f6]")
        b = filing.alert_key("r", "glitchtip", "GI INVARIANT VIOLATED [bcfa4532-6f5a-11f1-8bb5-c3355609e72d]")
        self.assertEqual(a, b)
        self.assertNotEqual(a, filing.alert_key("other/repo", "glitchtip", "GI INVARIANT VIOLATED [x]"))
        self.assertEqual(filing.alert_key("r", "grafana", ""), "")

    def test_different_messages_do_not_share_a_key(self):
        a = filing.alert_key("r", "glitchtip", 'BadRequestError: {"message":"Expected temperature')
        b = filing.alert_key("r", "glitchtip", 'BadRequestError: {"message":"Expected max_tokens')
        self.assertNotEqual(a, b)

    def test_same_alert_new_fingerprint_comments_on_open_issue(self):
        self._seed_48()
        out = filing.file_or_update(self._signal(), {"title": "Enrichment drain paused", "body": "b"}, "bug")
        self.assertTrue(out.startswith("COMMENTED") and "#48" in out and "alert_key" in out, out)
        self.assertFalse([p for m, p, _ in self.gh if m == "POST" and p.endswith("/issues")])
        body = [pl for m, p, pl in self.gh if p.endswith("/comments")][0]["body"]
        self.assertIn("instance `homelab`", body)

    def test_closed_issue_is_not_matched_on_alert_key(self):
        self._seed_48()
        self.open = set()
        out = filing.file_or_update(self._signal(), {"title": "Enrichment drain paused", "body": "b"}, "bug")
        self.assertTrue(out.startswith("FILED"), out)

    def test_flag_off_restores_old_behaviour(self):
        self._seed_48()
        os.environ["SF_ALERT_KEY_DEDUP"] = "0"
        out = filing.file_or_update(self._signal(), {"title": "Enrichment drain paused", "body": "b"}, "bug")
        self.assertTrue(out.startswith("FILED"), out)

    def test_alert_key_hit_never_inherits_mute(self):
        self._seed_48(issue="77")
        self.open = {"77"}
        out = filing.file_or_update(self._signal(), {"title": "Enrichment drain paused", "body": "b"}, "bug")
        self.assertTrue(out.startswith("FILED"), out)

    def test_backfill_from_dispositions(self):
        import tempfile
        filing._ledger_write([
            {"fingerprint": "grafana:ab6d", "repo": self.repo, "issue": "48", "group_key": "", "norm_key": ""},
            {"fingerprint": "grafana:none", "repo": self.repo, "issue": "9", "group_key": "", "norm_key": ""}])
        d = tempfile.NamedTemporaryFile("w", suffix=".tsv", delete=False)
        d.write("ts\tfingerprint\tsource\talertname\n"
                "2026-08-27\tgrafana:ab6d\tgrafana\tEnrichment/job drain paused\n")
        d.close()
        try:
            res = filing.backfill_alert_keys(d.name)
        finally:
            os.unlink(d.name)
        self.assertEqual((res["backfilled"], res["no_history"]), (1, 1))
        rows = {r["issue"]: r for r in filing._ledger_rows()}
        self.assertEqual(rows["48"]["alert_key"], self.ak)
        self.assertEqual(rows["9"].get("alert_key", ""), "")


class TestStaleNudge(unittest.TestCase):
    """#10: pure rule — quiet for 7 days, no human comment, never while firing."""

    def setUp(self):
        import stale
        self.s = stale
        self.now = stale._ts("2026-09-30T08:00:00Z")
        self.repo = "chipi/agentic-ai-homelab"
        self.names = {"fpA": ("grafana", "Enrichment/job drain paused")}
        self.ledger = [{"fingerprint": "fpA", "repo": self.repo, "issue": "48"}]

    def _seen(self, occ, firing=()):
        fps, aks = self.s.issue_signals(self.ledger, self.repo, 48, self.names)
        return self.s.last_seen(fps, aks, self.repo, occ, set(firing), self.now)

    def test_quiet_for_a_week_is_stale(self):
        seen = self._seen([("2026-09-20T00:00:00Z", "fpA", "grafana", "Enrichment/job drain paused")])
        self.assertTrue(self.s.is_stale(seen, [], self.now))

    def test_recent_occurrence_is_not_stale(self):
        seen = self._seen([("2026-09-28T00:00:00Z", "fpA", "grafana", "Enrichment/job drain paused")])
        self.assertFalse(self.s.is_stale(seen, [], self.now))

    def test_new_fingerprint_same_alert_counts_as_seen(self):
        # the #48 -> #72 case: a recurrence under a new fingerprint still refreshes last_seen
        seen = self._seen([("2026-09-01T00:00:00Z", "fpA", "grafana", "Enrichment/job drain paused"),
                           ("2026-09-29T00:00:00Z", "fpNEW", "grafana", "Enrichment/job drain paused")])
        self.assertFalse(self.s.is_stale(seen, [], self.now))

    def test_firing_now_is_never_stale(self):
        # a continuously firing alert records one occurrence at its start (#71)
        seen = self._seen([("2026-09-01T00:00:00Z", "fpA", "grafana", "Enrichment/job drain paused")],
                          firing=["Enrichment/job drain paused"])
        self.assertEqual(seen, self.now)
        self.assertFalse(self.s.is_stale(seen, [], self.now))

    def test_recent_human_comment_blocks_the_nudge(self):
        seen = self._seen([("2026-09-01T00:00:00Z", "fpA", "grafana", "Enrichment/job drain paused")])
        self.assertFalse(self.s.is_stale(seen, ["2026-09-29T12:00:00Z"], self.now))

    def test_no_evidence_never_nudges(self):
        self.assertFalse(self.s.is_stale(None, [], self.now))

    def test_opt_in_flag_forces_dry_run(self):
        os.environ.pop("SF_STALE_NUDGE", None)
        self.assertFalse(self.s.enabled())


class TestTriagerFailureDeferral(unittest.TestCase):
    """#11: transient triager failures defer (retry next cycle); 402 fails closed;
    a signal deferred DEFER_LIMIT times escalates; an all-deferred cycle is an outage."""

    def setUp(self):
        import tempfile
        import orchestrator
        self.o = orchestrator
        self._tmp = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
        self._tmp.close()
        os.unlink(self._tmp.name)
        self._orig = (orchestrator.DEFER_STATE, orchestrator.triage.triage)
        orchestrator.DEFER_STATE = self._tmp.name
        orchestrator._cycle.update(deferred=0, triaged=0, last_error="")
        self.sig = {"occurrence_id": "occ-1", "fingerprint": "grafana:x", "alertname": "a"}

    def tearDown(self):
        self.o.DEFER_STATE, self.o.triage.triage = self._orig
        if os.path.exists(self._tmp.name):
            os.unlink(self._tmp.name)

    def _flaky(self, *a, **k):
        raise self.o.triage.TriageDeferred("triager call failed: timed out")

    def test_transient_failure_defers_without_a_disposition(self):
        self.o.triage.triage = self._flaky
        self.assertIsNone(self.o._triage_or_defer(self.sig))
        self.assertEqual(self.o._cycle["deferred"], 1)

    def test_persistent_failure_escalates_after_the_limit(self):
        self.o.triage.triage = self._flaky
        for _ in range(self.o.DEFER_LIMIT - 1):
            self.assertIsNone(self.o._triage_or_defer(self.sig))
        d = self.o._triage_or_defer(self.sig)
        self.assertEqual(d["disposition"], "escalate")
        self.assertIn("cycles in a row", d["reason"])

    def test_success_clears_the_defer_count(self):
        self.o.triage.triage = self._flaky
        self.o._triage_or_defer(self.sig)
        self.o.triage.triage = lambda sig: {"disposition": "dismiss"}
        self.assertEqual(self.o._triage_or_defer(self.sig)["disposition"], "dismiss")
        self.assertEqual(self.o._defer_counts(), {})

    def test_402_fails_closed(self):
        import urllib.error
        import triage as t
        orig = t.post_json
        def boom(*a, **k):
            raise urllib.error.HTTPError("u", 402, "Payment Required", {}, None)
        t.post_json = boom
        orig_key, t.config.OPENROUTER_KEY = t.config.OPENROUTER_KEY, "test-key"
        try:
            with self.assertRaises(t.TriagerDown):
                t._call([{"role": "user", "content": "x"}])
        finally:
            t.post_json, t.config.OPENROUTER_KEY = orig, orig_key


if __name__ == "__main__":
    unittest.main(verbosity=2)
