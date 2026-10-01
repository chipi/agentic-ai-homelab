"""Replay eval for filing dedup (#9 alert_key) — real history, baseline vs fix.

Acceptance harness the operator asked for on 2026-09-30: every process fix gets an
input, today's output, the problem, and the output after the fix — replayed from
what actually happened, not invented.

The corpus (reference-filing/replay-2026-09-30.json) is the fleet's own record:
every row of results/filed.tsv (with the alert name and source dispositions.tsv
recorded for that fingerprint) plus each issue's real created/closed timestamps.
Each case replays one historical filing through filing.file_or_update() as the
world stood at that moment: only ledger rows filed earlier exist, an issue counts
as open only if it was open then, and norm_key only exists from 2026-08-27 (#1).

Two arms per case:
  baseline  SF_ALERT_KEY_DEDUP=0 — today's code. Must reproduce history (FILED),
            which is the check that the replay itself is faithful.
  fix       SF_ALERT_KEY_DEDUP=1 — must match the case's expectation: COMMENTED on
            an earlier open issue for the same alert, or FILED where the alerts
            are genuinely different (the over-merge guard).

Then a whole-ledger counterfactual: every issue the fleet ever opened, replayed in
order with the fix on, lists which would have been a comment instead.

  python3 eval_filing_replay.py            # report; exit non-zero on any case miss
  python3 eval_filing_replay.py --report OUT.txt   # also write every merge family
  python3 eval_filing_replay.py --build F_TSV D_TSV TIMELINES_JSON   # rebuild corpus
"""
import csv
import json
import os
import sys
import tempfile
from collections import defaultdict

import filing
import scrub

CORPUS = os.path.join(os.path.dirname(__file__), "..", "reference-filing",
                      "replay-2026-09-30.json")
NORM_KEY_SINCE = "2026-08-27"          # ceda02b: normalized dedup key (#1) introduced

# (issue replayed, expectation, why). Expectation "COMMENTED" = must land as a
# comment on an EARLIER open issue for the same alert; "FILED" = must still open
# its own issue. Numbers are chipi/agentic-ai-homelab issues triaged 2026-09-30.
CASES = [
    (25, "COMMENTED", "dup of #13 — same 'No api key passed in.' (closed as dup 2026-09-30)"),
    (35, "COMMENTED", "same alert as #13/#25, filed again 6 days later"),
    (30, "COMMENTED", "dup of #14 — ProxyModelNotFoundError"),
    (32, "COMMENTED", "same alert as #14/#30, filed again"),
    (17, "COMMENTED", "dup of #16 — OpenRouter RateLimitError, filed 1 min apart"),
    (22, "COMMENTED", "dup of #21 — Malformed API Key, filed 1 min apart"),
    (27, "COMMENTED", "same alert as #21/#22, filed 2 days later"),
    (24, "COMMENTED", "dup of #23 — DGX dark; Grafana fingerprint changed within 20 min"),
    (33, "COMMENTED", "dup of #29 — KeyNotFoundError"),
    (34, "COMMENTED", "same alert as #29/#33"),
    (37, "COMMENTED", "dup of #36 — OpenRouter insufficient credits, 10 min apart"),
    (43, "COMMENTED", "Host disk low — one APFS pool filed once per mountpoint (#42 was first, seconds earlier)"),
    (44, "COMMENTED", "Host disk low — same event"),
    (45, "COMMENTED", "Host disk low — same event"),
    (46, "COMMENTED", "Host disk low — same event"),
    (72, "COMMENTED", "dup of #48 — Enrichment/job drain paused; new fingerprint after a rule change, #48's row had no norm_key"),
    # over-merge guards: genuinely different alerts must keep their own issue
    (42, "FILED", "Host disk low — first of that family, must still open"),
    (11, "FILED", "different message from #10 (max_tokens vs temperature) — must NOT merge"),
    (49, "FILED", "'Corpus enrichment has stopped completing' is a different alert from #48's drain-paused"),
    (74, "FILED", "prod-podcast dark — first issue for this alert"),
    (75, "FILED", "prod logs dark — a different alert, same incident as #74 (correlation is a separate fix)"),
    (76, "FILED", "digest scheduler silent — a different alert, same incident"),
    # known limit, kept visible: #50 was written by hand, so it is not in the ledger
    (55, "FILED", "KNOWN MISS: #50 (same symptom) was filed by hand, not by the fleet, so no ledger row exists to match"),
    # alert_key a2 (2026-10-01): counters and measurements no longer split one alert
    ("chipi/podcast_scraper", 2040, "COMMENTED", "a2: DEADLINE EXCEEDED for episode 3 = the episode-9 alert #2037 (the stale-check gap)"),
    ("chipi/podcast_scraper", 1642, "COMMENTED", "a2: cleaning destroyed the transcript (1.5%) = the (26.4%) alert #1395"),
    ("chipi/podcast_scraper", 2026, "COMMENTED", "a2: wall-clock budget 14400s > 14400s = 14401s > 14400s, #1998"),
]
CASE_REPO = "chipi/agentic-ai-homelab"


# ── corpus ──────────────────────────────────────────────────────────────────
def build(filed_tsv, dispositions_tsv, timelines_json, out=CORPUS):
    names = {}
    with open(dispositions_tsv) as f:
        for d in csv.DictReader(f, delimiter="\t"):
            names.setdefault(d["fingerprint"], (d["source"], d["alertname"]))
    rows = []
    with open(filed_tsv) as f:
        for r in csv.DictReader(f, delimiter="\t"):
            src, name = names.get(r["fingerprint"], ("", ""))
            name = scrub.scrub_str(name)          # same scrub as reference-dedup/
            rows.append({k: r.get(k, "") for k in ("fingerprint", "repo", "issue", "group_key",
                                                    "filed_at", "norm_key")}
                        | {"source": src, "alertname": name})
    rows.sort(key=lambda r: r["filed_at"])
    with open(timelines_json) as f:
        issues = json.load(f)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w") as f:
        json.dump({"built_from": "results/filed.tsv + dispositions.tsv on the mini, "
                                 "GitHub issue timelines, 2026-09-30; alert names scrubbed "
                                 "via scrub.py",
                   "rows": rows, "issues": issues}, f, indent=1, ensure_ascii=False)
    print(f"corpus: {len(rows)} ledger rows, {len(issues)} issue timelines -> {out}")


# ── replay machinery ────────────────────────────────────────────────────────
class World:
    """Ledger + GitHub as they stood at one moment. Swaps filing's I/O for fakes."""

    def __init__(self, corpus, at, ledger_rows):
        self.corpus, self.at = corpus, at
        self.calls = []
        self._tmp = tempfile.NamedTemporaryFile("w", suffix=".tsv", delete=False)
        self._tmp.close()
        self._orig = (filing.FILED, filing._gh, filing.issue_state)
        filing.FILED = self._tmp.name
        filing._gh = self._gh
        filing.issue_state = self._state
        filing._ledger_write([self._as_ledger_row(r) for r in ledger_rows])

    def _as_ledger_row(self, r):
        nk = r["norm_key"] if self.at >= NORM_KEY_SINCE else ""
        return {"fingerprint": r["fingerprint"], "repo": r["repo"], "issue": r["issue"],
                "group_key": r["group_key"], "filed_at": r["filed_at"],
                "last_comment_day": "", "norm_key": nk,
                "alert_key": filing.alert_key(r["repo"], r["source"], r["alertname"])}

    def _state(self, repo, num):
        t = self.corpus["issues"].get(f"{repo}#{num}", {})
        closed = t.get("closed")
        is_open = bool(t) and t["created"] <= self.at and (not closed or closed > self.at)
        return {"state": "open" if is_open else "closed", "labels": [],
                "closed_at": filing.datetime.fromisoformat(closed.replace("Z", "+00:00"))
                if closed and not is_open else None, "url": ""}

    def _gh(self, method, path, payload=None):
        self.calls.append((method, path))
        if method == "POST" and path.endswith("/issues"):
            return {"number": "NEW", "html_url": "replay"}
        if method == "GET" and "/search/issues" in path:
            return {"items": []}
        if method == "GET" and "/milestones" in path:
            return []
        return {}

    def close(self):
        filing.FILED, filing._gh, filing.issue_state = self._orig
        os.unlink(self._tmp.name)


def replay(corpus, row, fix_on, exclude=frozenset()):
    """Replay one historical filing. Returns (outcome_word, target_issue_or_None, raw).
    `exclude` drops ledger rows of issues that, in the fixed world, were never opened."""
    os.environ["SF_ALERT_KEY_DEDUP"] = "1" if fix_on else "0"
    at = row["filed_at"]
    before = [r for r in corpus["rows"]
              if r["filed_at"] < at and (r["repo"], r["issue"]) not in exclude]
    w = World(corpus, at, before)
    try:
        signal = {"fingerprint": row["fingerprint"], "source": row["source"],
                  "alertname": row["alertname"], "labels": {}}
        out = filing.file_or_update(signal, {"title": row["alertname"] or "replayed signal",
                                             "body": "replay"}, "bug")
    finally:
        w.close()
    word = out.split(":")[0]
    target = None
    if word in ("COMMENTED", "REOPENED", "MUTED", "DEDUP"):
        target = out.split("#")[1].split()[0] if "#" in out else None
    return word, target, out


def _row_for(corpus, repo, issue):
    rows = [r for r in corpus["rows"] if r["repo"] == repo and r["issue"] == str(issue)]
    return min(rows, key=lambda r: r["filed_at"]) if rows else None


def run_cases(corpus):
    print("Acceptance cases — real filings replayed (baseline = today's code, fix = #9 on)\n")
    print(f"  {'issue':>6}  {'baseline':<10} {'fix':<22} {'expect':<10} ok  why")
    fails = unfaithful = 0
    for case in CASES:
        repo, num, expect, why = case if len(case) == 4 else (CASE_REPO, *case)
        row = _row_for(corpus, repo, num)
        if not row:
            print(f"  #{num:<5}  (not in ledger — cannot replay)            ✗   {why}")
            fails += 1
            continue
        b_word, _, _ = replay(corpus, row, fix_on=False)
        f_word, f_target, _ = replay(corpus, row, fix_on=True)
        fix_txt = f_word + (f" #{f_target}" if f_target else "")
        faithful = b_word == "FILED"                      # baseline must reproduce history
        unfaithful += not faithful
        ok = faithful and (f_word == expect)
        if expect == "COMMENTED" and ok:
            t = corpus["issues"].get(f"{repo}#{f_target}", {})
            ok = bool(t) and t["created"] < row["filed_at"]   # an EARLIER issue
        fails += not ok
        flag = "✓" if ok else "✗"
        base_txt = b_word if faithful else f"{b_word}!"
        print(f"  #{num:<5}  {base_txt:<10} {fix_txt:<22} {expect:<10} {flag}   {why}")
    print(f"\n  {len(CASES) - fails}/{len(CASES)} cases pass; baseline reproduced history in "
          f"{len(CASES) - unfaithful}/{len(CASES)}{'' if not unfaithful else ' (marked !)'}")
    return fails


def counterfactual(corpus, report_path=None):
    """Every issue the fleet ever OPENED, in order, with the fix on: which would have
    been a comment instead? Evolving world — a merged filing opens nothing, so later
    recurrences attach to the family's FIRST issue (its root)."""
    first_row = {}
    for r in corpus["rows"]:
        k = (r["repo"], r["issue"])
        if k not in first_row or r["filed_at"] < first_row[k]["filed_at"]:
            first_row[k] = r
    creations = sorted(first_row.values(), key=lambda r: r["filed_at"])
    never_opened, root = set(), {}
    families = defaultdict(list)          # (repo, root issue) -> would-be duplicates
    for r in creations:
        word, target, _ = replay(corpus, r, fix_on=True, exclude=frozenset(never_opened))
        if word == "COMMENTED" and target:
            top = root.get((r["repo"], target), target)
            root[(r["repo"], r["issue"])] = top
            never_opened.add((r["repo"], r["issue"]))
            families[(r["repo"], top)].append(r)
    n_merged = len(never_opened)
    kept = len(creations) - n_merged
    lines = [f"Whole-ledger counterfactual — {len(creations)} issues the fleet opened, "
             f"replayed in order with the fix on:",
             f"  still opened: {kept}   would have been a comment instead: {n_merged} "
             f"({100 * n_merged // max(len(creations), 1)}%)"]
    by_repo = defaultdict(int)
    for (repo, _), v in families.items():
        by_repo[repo] += len(v)
    lines += [f"    {repo}: {n}" for repo, n in sorted(by_repo.items())]
    lines.append(f"\n  {len(families)} issue families — root issue, the would-be duplicates "
                 f"that become comments on it (= its extra signals), alert:")
    for (repo, top), dups in sorted(families.items(), key=lambda kv: -len(kv[1])):
        name = first_row[(repo, top)]["alertname"][:80] if (repo, top) in first_row else ""
        lines.append(f"    {repo.split('/')[1]}#{top}  +{len(dups):<3} "
                     f"<- {', '.join('#' + d['issue'] for d in dups)}")
        lines.append(f"        {name}")
    print("\n" + "\n".join(lines[:3 + len(by_repo) + 1 + 2 * 12]))
    if len(families) > 12:
        print(f"    … {len(families) - 12} more families" +
              (f" — full list in {report_path}" if report_path else ""))
    if report_path:
        with open(report_path, "w") as f:
            f.write("\n".join(lines) + "\n")
    return n_merged


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--build":
        build(*sys.argv[2:5])
        raise SystemExit(0)
    with open(CORPUS) as f:
        corpus = json.load(f)
    fails = run_cases(corpus)
    if "--cases-only" not in sys.argv:
        rp = sys.argv[sys.argv.index("--report") + 1] if "--report" in sys.argv else None
        counterfactual(corpus, rp)
    raise SystemExit(1 if fails else 0)
