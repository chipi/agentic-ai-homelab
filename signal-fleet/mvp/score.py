"""Score the triager over the frozen reference fixtures (EVAL.md).

Replays each fixture's FROZEN evidence bundle k times through triage.triage (no
re-correlation — that's the point) and reports the asymmetric metrics against the
operator's ground-truth labels. The model is attributed via SF_TRIAGE_MODEL, so a
model change = a new comparable run (EVAL.md §3.6).

  SF_TRIAGE_MODEL=deepseek/deepseek-v4-pro python3 score.py 3
"""
import collections
import json
import os
import sys

import config
import triage


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
    if unlabeled:
        print(f"UNLABELED (skipped — fill ground_truth): {len(unlabeled)}  {unlabeled[:8]}")
    if not labeled:
        print("no labeled fixtures yet — nothing to score. Fill ground_truth in the fixtures.")
        return
    print(f"scoring {len(labeled)} labeled fixtures · k={k} · model={config.TRIAGE_MODEL}\n")

    total = escalate = false_dismiss = should_not_dismiss = 0
    consistency = collections.defaultdict(set)
    confusion = collections.Counter()

    for f in labeled:
        gt = f["ground_truth"]["disposition"]      # dismiss | file | escalate
        for _ in range(k):
            d = triage.triage(f["signal"], f["evidence"])
            got = d["disposition"]
            total += 1
            confusion[(gt, got)] += 1
            consistency[f["id"]].add(got)
            if got == "escalate":
                escalate += 1
            if gt in ("file", "escalate"):        # a real defect / genuinely-hard
                should_not_dismiss += 1
                if got == "dismiss":
                    false_dismiss += 1             # the expensive error

    fd_rate = false_dismiss / should_not_dismiss if should_not_dismiss else 0.0
    esc_rate = escalate / total if total else 0.0
    inconsistent = [fid for fid, s in consistency.items() if len(s) > 1]

    print(f"=== RESULT · model={config.TRIAGE_MODEL} · prompt={triage.PROMPT_SHA} ===")
    print(f"FALSE-DISMISS rate : {false_dismiss}/{should_not_dismiss} = {fd_rate:.2f}   ⭐ the gate metric")
    print(f"escalate rate      : {escalate}/{total} = {esc_rate:.2f}")
    print(f"inconsistent (varied across k): {len(inconsistent)}/{len(labeled)}  {inconsistent[:8]}")
    print("confusion (ground_truth -> got):")
    for (gt, got), n in sorted(confusion.items()):
        flag = "  <-- FALSE-DISMISS" if gt in ("file", "escalate") and got == "dismiss" else ""
        print(f"  {gt:>8} -> {got:<8} {n}{flag}")


if __name__ == "__main__":
    score(int(sys.argv[1]) if len(sys.argv) > 1 else 3)
