"""Replay eval: fuzzy ledger matches prefer an OPEN issue over reopening a closed one.

The bug (2026-10-02): the per-disk mini alert (fix 0702aee) arrived with a new
fingerprint, matched the six old disk rows on norm_key, and newest-row picked #47,
closed, so the fleet would have reopened it while #43, the open issue for the same
disk, sat one row earlier.

Input: the live filed-ledger (reference-filing/filed-2026-10-02.tsv) and the GitHub
state of every issue in chipi's three repos, frozen the same day
(reference-filing/issue-states-2026-10-02.json). For every ledger row, a signal with
a NEW fingerprint and that row's group/norm/alert keys is looked up by
  baseline  filing.py at BASE_REV (newest norm_key row, open or closed)
  fix       the working-tree filing.py (open issue first)
Pass:
  - the disk case moves #47 (closed) -> #43 (open);
  - every changed match moves from a CLOSED issue to an OPEN one that shares the
    signal's norm_key or alert_key; nothing else changes;
  - no match ever moves TO a low-signal rollup bucket (a bucket is not the bug's
    issue; the first version of this fix sent 13 of 32 moves to rollup #1871);
  - every move comes through norm_key (a second version also let alert_key prefer
    open issues; its moves mostly matched GitHub's duplicate links, and where they
    differed the link was the more exact answer, e.g. #2037 -> #1958 vs duplicateOf
    #2040; duplicates are followed explicitly instead, eval_duplicate_follow_replay).

  python3 eval_open_preference_replay.py     # exit 1 on any failure
"""
import importlib.util
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
LEDGER = os.path.join(HERE, "..", "reference-filing", "filed-2026-10-02.tsv")
STATES = os.path.join(HERE, "..", "reference-filing", "issue-states-2026-10-02.json")
BASE_REV = "0702aee"   # main before this fix
os.environ["SF_FILED_LEDGER"] = LEDGER
os.environ.setdefault("SF_OBSERV_DISABLED", "1")


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _baseline():
    src = subprocess.run(["git", "-C", HERE, "show", f"{BASE_REV}:signal-fleet/mvp/filing.py"],
                         capture_output=True, text=True, check=True).stdout
    tmp = tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, dir=HERE, prefix="_filing_base_")
    tmp.write(src)
    tmp.close()
    try:
        return _load(tmp.name, "filing_baseline")
    finally:
        os.unlink(tmp.name)


def main():
    states = json.load(open(STATES))["states"]

    def is_open(repo, issue):
        return states.get(f"{repo}#{issue}", {}).get("state") == "open"

    base, fix = _baseline(), _load(os.path.join(HERE, "filing.py"), "filing_fix")
    rows = [r for r in fix._ledger_rows() if r["fingerprint"].startswith(("glitchtip:", "grafana:"))]
    fails, changed, same = [], [], 0
    for i, r in enumerate(rows):
        keys = (f"replay:new-{i}", r.get("group_key", ""), r.get("norm_key", ""), r.get("alert_key", ""))
        b = base.ledger_lookup(*keys, is_open=is_open)
        f = fix.ledger_lookup(*keys, is_open=is_open)
        bk = (b["repo"], b["issue"]) if b else None
        fk = (f["repo"], f["issue"]) if f else None
        if bk == fk:
            same += 1
            continue
        changed.append((r, b, f))
        ok = (b and f and not is_open(*bk) and is_open(*fk)
              and ((r.get("norm_key") and f.get("norm_key") == r["norm_key"])
                   or (r.get("alert_key") and f.get("alert_key") == r["alert_key"])))
        if not ok:
            fails.append(f"row {r['repo']}#{r['issue']}: {bk} -> {fk} is not closed -> open of the same bug/alert")
        if f and f["_dim"] != "norm_key":
            fails.append(f"row {r['repo']}#{r['issue']}: moved via {f['_dim']}, not norm_key")
        if f and str(f.get("group_key", "")).startswith(fix.ROLLUP_PREFIX):
            fails.append(f"row {r['repo']}#{r['issue']}: moved to rollup bucket #{f['issue']}")

    disk = [r for r in rows if r["repo"] == "chipi/agentic-ai-homelab" and r["issue"] == "47"]
    print(f"Open-preference replay — {len(rows)} ledger rows, each as a new fingerprint\n")
    print(f"  unchanged matches: {same}")
    print(f"  changed matches:   {len(changed)}")
    for r, b, f in changed:
        print(f"    {r['repo'].split('/')[1]}#{r['issue']:<5} baseline {b['repo'].split('/')[1]}#{b['issue']}"
              f" ({'open' if is_open(b['repo'], b['issue']) else 'closed'}, {b['_dim']})"
              f"  ->  fix #{f['issue']} ({'open' if is_open(f['repo'], f['issue']) else 'closed'}, {f['_dim']})")
    if not disk:
        fails.append("disk case missing: no ledger row for homelab#47")
    else:
        keys = ("replay:disk", disk[0].get("group_key", ""), disk[0].get("norm_key", ""), disk[0].get("alert_key", ""))
        b = base.ledger_lookup(*keys, is_open=is_open)
        f = fix.ledger_lookup(*keys, is_open=is_open)
        print(f"\n  disk case (new per-disk alert): baseline #{b and b['issue']} -> fix #{f and f['issue']}")
        if not (b and b["issue"] == "47" and f and f["issue"] == "43"):
            fails.append("disk case: expected baseline #47 -> fix #43")
    print("\n" + ("PASS" if not fails else "FAIL:\n  " + "\n  ".join(fails)))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
