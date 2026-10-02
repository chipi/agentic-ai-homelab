"""Replay eval: a recurrence matched to an issue closed as a DUPLICATE goes to its
canonical issue instead of reopening the duplicate.

The bug (2026-10-01): one disk alert reopened #42, #44, #45, #46, all closed the day
before as duplicates of #43, so one problem was split across issues again and
the operator had to re-close them by hand.

Input, frozen 2026-10-02:
  reference-filing/filed-2026-10-02.tsv         the live filed-ledger
  reference-filing/duplicates-2026-10-02.json   GitHub state, close time, labels of
      every issue the ledger points to, and for each issue closed as a duplicate its
      `duplicateOf` target (GitHub GraphQL; chains followed).
Every ledger row is replayed as a recurrence of its own fingerprint through the REAL
filing.file_or_update of
  baseline  filing.py at BASE_REV
  fix       the working-tree filing.py
with GitHub reads served from the frozen state (as of the capture day) and writes
recorded, never sent. Pass:
  - every row whose issue was closed as a duplicate now acts on the end of its
    duplicateOf chain, never on the duplicate;
  - every other row acts exactly as the baseline did;
  - the disk rows (#42, #44, #45, #46) comment on #43.

  python3 eval_duplicate_follow_replay.py     # exit 1 on any failure
"""
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
LEDGER = os.path.join(HERE, "..", "reference-filing", "filed-2026-10-02.tsv")
CORPUS = os.path.join(HERE, "..", "reference-filing", "duplicates-2026-10-02.json")
BASE_REV = "857ddf8"   # main before this fix
NOW = datetime(2026, 10, 2, 12, 0, tzinfo=timezone.utc)
_TMP = tempfile.mkdtemp(prefix="sf-dup-replay-")
os.environ["SF_FILED_LEDGER"] = os.path.join(_TMP, "filed.tsv")
shutil.copy(LEDGER, os.environ["SF_FILED_LEDGER"])
os.environ.setdefault("SF_OBSERV_DISABLED", "1")
os.environ.setdefault("GITHUB_TOKEN", "replay-never-sent")


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


def _stub(mod, corpus, writes):
    states, dups = corpus["states"], corpus["duplicate_of"]

    def issue_state(repo, n):
        s = states.get(f"{repo}#{n}", {"state": "open", "reason": "", "closed_at": "", "labels": []})
        ca = s["closed_at"]
        return {"state": s["state"], "labels": s["labels"], "reason": s["reason"], "url": "",
                "closed_at": datetime.fromisoformat(ca.replace("Z", "+00:00")) if ca else None}

    def gh(method, path, payload=None):
        if method != "GET":
            writes.append((method, path, payload or {}))
        return {"number": 999999, "html_url": "replay"}

    mod.issue_state = issue_state
    mod._gh = gh
    mod._now = lambda: NOW
    mod._today = lambda: NOW.strftime("%Y-%m-%d")
    mod._glitchtip_note = lambda *a, **k: None
    mod._grafana_annotation = lambda *a, **k: None
    mod._ensure_labels = lambda *a, **k: None
    mod._milestone_number = lambda *a, **k: None
    mod._related_issues = lambda *a, **k: []
    if hasattr(mod, "duplicate_of"):
        mod.duplicate_of = lambda repo, n: (tuple(dups[f"{repo}#{n}"].split("#")[0:1]) +
                                           (int(dups[f"{repo}#{n}"].split("#")[1]),)) if dups.get(f"{repo}#{n}") else None


def outcome(mod, row, corpus):
    shutil.copy(LEDGER, os.environ["SF_FILED_LEDGER"])
    mod.FILED = os.environ["SF_FILED_LEDGER"]
    writes = []
    _stub(mod, corpus, writes)
    signal = {"fingerprint": row["fingerprint"], "occurrence_id": row["fingerprint"] + "@replay",
              "source": row["fingerprint"].split(":")[0], "alertname": "replayed recurrence",
              "labels": {}, "summary": ""}
    res = mod.file_or_update(signal, {"title": "replayed recurrence", "body": "", "labels": []}, "bug")
    targets = sorted({m.group(1) + "#" + m.group(2) for _, p, _ in writes
                      for m in [re.match(r"/repos/([^/]+/[^/]+)/issues/(\d+)", p)] if m})
    # a regression (target closed >= 7 days) files a NEW issue whose body names it
    for method, p, body in writes:
        if method == "POST" and re.fullmatch(r"/repos/[^/]+/[^/]+/issues", p):
            m = re.search(r"Regression of (\S+#\d+)", body.get("body", ""))
            targets.append("regression-of:" + (m.group(1) if m else "?"))
    return res.split(":")[0], targets


def chain_end(key, dups):
    seen = 0
    while dups.get(key) and seen < 3:
        key, seen = dups[key], seen + 1
    return key


def main():
    corpus = json.load(open(CORPUS))
    dups = corpus["duplicate_of"]
    base, fix = _baseline(), _load(os.path.join(HERE, "filing.py"), "filing_fix")
    rows = [r for r in base._ledger_rows() if r["fingerprint"].startswith(("glitchtip:", "grafana:"))]
    fails, moved, same, examples = [], 0, 0, []
    for r in rows:
        key = f"{r['repo']}#{r['issue']}"
        b, f = outcome(base, r, corpus), outcome(fix, r, corpus)
        if dups.get(key):
            want = chain_end(key, dups)
            moved += 1
            if key in f[1] or not ({want, "regression-of:" + want} & set(f[1])):
                fails.append(f"{key} (duplicate of {want}): fix acted on {f[1]} ({f[0]})")
            if len(examples) < 8 or key.endswith(("#42", "#44", "#45", "#46")):
                examples.append(f"    {key:<34} baseline {b[0]:<10} {','.join(b[1]) or '-':<34} -> fix {f[0]:<10} {','.join(f[1])}")
        else:
            same += b == f
            if b != f:
                fails.append(f"{key} (not a duplicate) changed: {b} -> {f}")
    for k in ("chipi/agentic-ai-homelab#42", "chipi/agentic-ai-homelab#44",
              "chipi/agentic-ai-homelab#45", "chipi/agentic-ai-homelab#46"):
        rr = [r for r in rows if f"{r['repo']}#{r['issue']}" == k]
        if not rr:
            fails.append(f"disk case missing: {k}")
            continue
        res, tg = outcome(fix, rr[0], corpus)
        if res != "COMMENTED" or tg != ["chipi/agentic-ai-homelab#43"]:
            fails.append(f"disk case {k}: expected COMMENTED on #43, got {res} {tg}")
    print(f"Duplicate-follow replay — {len(rows)} ledger rows replayed as recurrences\n")
    print(f"  rows whose issue was closed as a duplicate: {moved}")
    print(f"  other rows acting exactly as before:        {same} of {len(rows) - moved}")
    print("  examples (baseline -> fix):")
    print("\n".join(sorted(set(examples))))
    shutil.rmtree(_TMP, ignore_errors=True)
    print("\n" + ("PASS" if not fails else "FAIL:\n  " + "\n  ".join(fails[:20])))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
