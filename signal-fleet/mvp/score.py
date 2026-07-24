"""Score the triager over the frozen reference fixtures (EVAL.md, SIGNALS §7.3).

Replays each fixture's FROZEN probe->response table k times through the investigation
loop. Every probe the model requests is intercepted against the frozen table (no live
correlation — that's the point), so variation across k is the MODEL's judgement, not
evidence drift. The model is attributed via SF_TRIAGE_MODEL, so a model change = a new
comparable run (EVAL.md §3.6).

Asymmetric metrics (EVAL.md §3.3) — the errors are NOT symmetric:
- FALSE-DISMISS  (⭐ gate): ground-truth file|escalate but got dismiss — a real defect
  or genuinely-hard signal silently dropped. The expensive error.
- over-FILE:      ground-truth dismiss|cleanup but got file — a non-defect pushed
  downstream (an issue someone must pick up; cost goes up).
- file-recall:    of the ground-truth files, how many were caught as file.
- escalate-rate:  fraction routed to the human (the autonomy cost — too high = useless).
- inconsistency:  fixtures whose disposition varied across the k runs.

  SF_OBSERV_DISABLED=1 SF_TRIAGE_MODEL=deepseek/deepseek-v4-pro python3 score.py 3
"""
import collections
import json
import os
import sys

import config
import triage

EXPENSIVE_MISS = {"file", "escalate"}  # dismissing one of these is the costly error


def load():
    out = []
    for fn in sorted(os.listdir(config.REFERENCE_DIR)):
        if fn.endswith(".json"):
            with open(os.path.join(config.REFERENCE_DIR, fn)) as f:
                out.append(json.load(f))
    return out


def score(k=3):
    everything = load()
    labeled = [f for f in everything if (f.get("ground_truth") or {}).get("disposition")]
    unlabeled = [f["id"] for f in everything if not (f.get("ground_truth") or {}).get("disposition")]
    legacy = [f["id"] for f in labeled if "probes" not in f]
    if unlabeled:
        print(f"UNLABELED (skipped — fill ground_truth): {len(unlabeled)}  {unlabeled[:8]}")
    if legacy:
        print(f"LEGACY (skipped — no frozen probe table; re-run freeze.py): {legacy[:8]}")
        labeled = [f for f in labeled if "probes" in f]
    if not labeled:
        print("no scorable fixtures — fill ground_truth and (re-)freeze probe tables.")
        return
    print(f"scoring {len(labeled)} labeled fixtures · k={k} · model={config.TRIAGE_MODEL}\n")

    total = escalate = false_dismiss = expensive = over_file = 0
    file_gt = file_hit = 0
    consistency = collections.defaultdict(set)
    confusion = collections.Counter()

    for f in labeled:
        gt = f["ground_truth"]["disposition"]              # dismiss|cleanup|file|escalate
        table = f["probes"]
        for _ in range(k):
            d = triage.investigate(f["signal"], probe_table=table)
            got = d["disposition"]
            total += 1
            confusion[(gt, got)] += 1
            consistency[f["id"]].add(got)
            if got == "escalate":
                escalate += 1
            if gt in EXPENSIVE_MISS:
                expensive += 1
                if got == "dismiss":
                    false_dismiss += 1                     # the expensive error
            if gt in ("dismiss", "cleanup") and got == "file":
                over_file += 1                             # non-defect pushed downstream
            if gt == "file":
                file_gt += 1
                if got == "file":
                    file_hit += 1

    fd_rate = false_dismiss / expensive if expensive else 0.0
    esc_rate = escalate / total if total else 0.0
    recall = file_hit / file_gt if file_gt else None
    inconsistent = [fid for fid, s in consistency.items() if len(s) > 1]

    print(f"=== RESULT · model={config.TRIAGE_MODEL} · prompt={triage.PROMPT_SHA} · k={k} ===")
    print(f"FALSE-DISMISS rate : {false_dismiss}/{expensive} = {fd_rate:.2f}   ⭐ the gate metric")
    print(f"over-FILE rate     : {over_file}/{total} = {over_file / total if total else 0:.2f}")
    print(f"file-recall        : "
          + (f"{file_hit}/{file_gt} = {recall:.2f}" if recall is not None else "n/a (no file GT)"))
    print(f"escalate rate      : {escalate}/{total} = {esc_rate:.2f}")
    print(f"inconsistent (varied across k): {len(inconsistent)}/{len(labeled)}  {inconsistent[:8]}")
    print("confusion (ground_truth -> got):")
    for (gt, got), n in sorted(confusion.items()):
        flag = ""
        if gt in EXPENSIVE_MISS and got == "dismiss":
            flag = "  <-- FALSE-DISMISS"
        elif gt in ("dismiss", "cleanup") and got == "file":
            flag = "  <-- over-FILE"
        print(f"  {gt:>8} -> {got:<8} {n}{flag}")


if __name__ == "__main__":
    score(int(sys.argv[1]) if len(sys.argv) > 1 else 3)
