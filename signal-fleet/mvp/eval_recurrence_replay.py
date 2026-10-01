"""Replay eval for GlitchTip recurrence rows — one row per count CHANGE, not per cycle.

The bug (found 2026-10-01): run_glitchtip compares an error's live count with the
count at its last TRIAGE. Once the count rises, that stays true, so every 10-min
cycle appended an identical `recurrence` row until the 24 h re-triage: ~140 rows per
count bump. By 2026-10-01, 10,764 of the 11,700 GlitchTip recurrence rows were repeats.

Input: every GlitchTip row of the live dispositions ledger as of 2026-10-01
(reference-recurrence/glitchtip-history-2026-10-01.tsv.gz: ts, occurrence_id,
fingerprint, disposition, signal_count, cycle_id; no message text). Each row is one
observation the fleet made: that error, that count, at that time.

Each observation is fed, in order and at its own timestamp, through the REAL
run_glitchtip of
  baseline  orchestrator.py as committed at BASE_REV (the code running before this fix)
  fix       the working-tree orchestrator.py
with GlitchTip, the LLM triager and GitHub stubbed (a triage returns the disposition
the history recorded). Each run writes its own temp ledger.

Pass:
  - baseline reproduces the history row for row (the replay is faithful);
  - fix writes ZERO repeated recurrence rows (same error, same count, same baseline);
  - fix keeps every distinct count change the baseline recorded;
  - fix triages exactly the observations the baseline triaged (re-triage untouched).
Limitation: an observation the old code skipped silently left no row, so it is not
in the input. That is safe here: the old code skipping means the new code skips too.

  python3 eval_recurrence_replay.py      # exit 1 on any failure
"""
import csv
import datetime
import gzip
import importlib.util
import io
import os
import subprocess
import sys
import tempfile

os.environ.setdefault("OPENROUTER_API_KEY", "replay-dummy")
os.environ.setdefault("SF_OBSERV_DISABLED", "1")
HERE = os.path.dirname(os.path.abspath(__file__))
CORPUS = os.path.join(HERE, "..", "reference-recurrence", "glitchtip-history-2026-10-01.tsv.gz")
BASE_REV = "1343851"   # main before this fix

import actions   # noqa: E402
import config    # noqa: E402
import observ    # noqa: E402
import sources   # noqa: E402


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _baseline_orchestrator():
    src = subprocess.run(["git", "-C", HERE, "show", f"{BASE_REV}:signal-fleet/mvp/orchestrator.py"],
                         capture_output=True, text=True, check=True).stdout
    tmp = tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, dir=HERE, prefix="_orch_base_")
    tmp.write(src)
    tmp.close()
    try:
        return _load(tmp.name, "orchestrator_baseline")
    finally:
        os.unlink(tmp.name)


def _ts(s):
    return datetime.datetime.fromisoformat(s)


def replay(mod, obs):
    """Feed every observation through mod.run_glitchtip; return the rows it wrote."""
    ledger = tempfile.NamedTemporaryFile("w", suffix=".tsv", delete=False)
    ledger.close()
    os.unlink(ledger.name)
    orig = (config.LEDGER, actions._now, actions.act, sources.glitchtip_unresolved,
            sources.to_error_signal, observ.push_disposition_metric)
    clock = {"now": None}
    config.LEDGER = ledger.name
    actions._now = lambda: clock["now"].isoformat()
    actions.act = lambda sig, disp, dry_run=True: actions.ledger_append(sig, disp)
    observ.push_disposition_metric = lambda *a, **k: None
    sources.to_error_signal = lambda issue: issue
    mod._hours_since = lambda ts: (clock["now"] - _ts(ts)).total_seconds() / 3600
    mod._triage_or_defer = lambda sig: {"disposition": sig["_hist"] if sig["_hist"] != "recurrence"
                                        else "TRIAGED-WHERE-HISTORY-RECORDED-RECURRENCE", "_meta": {}}
    out = sys.stdout
    try:
        sys.stdout = io.StringIO()            # run_glitchtip narrates every decision
        for o in obs:
            clock["now"] = _ts(o["ts"])
            sig = {"fingerprint": o["fingerprint"], "occurrence_id": o["occurrence_id"],
                   "source": "glitchtip", "alertname": "", "_hist": o["disposition"],
                   "labels": {"count": int(o["signal_count"]) if o["signal_count"].isdigit() else 0}}
            sources.glitchtip_unresolved = lambda limit, s=sig: [s]
            mod.run_glitchtip(limit=1, dry_run=True)
    finally:
        sys.stdout = out
        (config.LEDGER, actions._now, actions.act, sources.glitchtip_unresolved,
         sources.to_error_signal, observ.push_disposition_metric) = orig
    with open(ledger.name) as f:
        rows = list(csv.DictReader(f, delimiter="\t"))
    os.unlink(ledger.name)
    return rows


def _key(r):
    return (r["fingerprint"], r["disposition"], r["signal_count"])


def main():
    with gzip.open(CORPUS, "rt") as f:
        obs = list(csv.DictReader(f, delimiter="\t"))
    base_rows = replay(_baseline_orchestrator(), obs)
    fix_rows = replay(_load(os.path.join(HERE, "orchestrator.py"), "orchestrator_fix"), obs)
    fails = []

    hist = [_key(o) for o in obs]
    faithful = sum(a == b for a, b in zip(hist, map(_key, base_rows)))
    print(f"Recurrence replay — {len(obs)} GlitchTip observations from the live ledger\n")
    print(f"  baseline reproduces history: {faithful}/{len(obs)} rows"
          f"{'' if len(base_rows) == len(obs) else f' (wrote {len(base_rows)})'}")
    if faithful != len(obs) or len(base_rows) != len(obs):
        fails.append("baseline replay is not faithful to the history")

    def recurrences(rows):
        return [r for r in rows if r["reason"].startswith("recurred after")]

    def transitions(rows):
        return {(r["fingerprint"], r["reason"]) for r in recurrences(rows)}

    def repeats(rows):
        return len(recurrences(rows)) - len(transitions(rows))

    def triaged(rows):
        return [(r["fingerprint"], r["disposition"]) for r in rows if r["disposition"] != "recurrence"]

    print(f"\n  {'':<34} {'baseline':>9} {'fix':>9}")
    print(f"  {'recurrence rows':<34} {len(recurrences(base_rows)):>9} {len(recurrences(fix_rows)):>9}")
    print(f"  {'  of which repeats (same change)':<34} {repeats(base_rows):>9} {repeats(fix_rows):>9}")
    print(f"  {'distinct count changes recorded':<34} {len(transitions(base_rows)):>9} {len(transitions(fix_rows)):>9}")
    print(f"  {'triage decisions':<34} {len(triaged(base_rows)):>9} {len(triaged(fix_rows)):>9}")
    if repeats(fix_rows):
        fails.append(f"fix still writes {repeats(fix_rows)} repeated recurrence rows")
    lost = transitions(base_rows) - transitions(fix_rows)
    if lost:
        fails.append(f"fix lost {len(lost)} count changes, e.g. {sorted(lost)[0]}")
    if triaged(base_rows) != triaged(fix_rows):
        fails.append("fix changed which observations were triaged")
    print("\n" + ("PASS" if not fails else "FAIL:\n  " + "\n  ".join(fails)))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
