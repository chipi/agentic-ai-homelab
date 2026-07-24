"""Score the triager over the frozen reference fixtures (EVAL.md, SIGNALS §7.3).

Replays each fixture's FROZEN probe->response table k times through the investigation
loop. Every probe the model requests is intercepted against the frozen table (no live
correlation — that's the point), so variation across k is the MODEL's judgement, not
evidence drift. The model is attributed via SF_TRIAGE_MODEL, so a model change = a new
comparable run (EVAL.md §3.6).

DUAL-LABEL scoring (review R7). Each fixture carries TWO ground truths:
- true_nature (ground_truth.disposition): the signal's real nature — scores the
  SAFETY metric. A dismissed real defect is a lost defect no matter what was citable,
  so false-dismiss is measured here and relabeling would blind it.
- correct_autonomous (ground_truth.correct_autonomous): the disposition a perfectly
  intent-gated triager SHOULD reach given only what it can cite — scores the AUTONOMY
  gate. For a defect whose intent only the operator knows, the correct autonomous act
  is escalate, so an escalate there is a CORRECT action, not a miss.

Metrics:
- FALSE-DISMISS (⭐ safety): true_nature=file but got dismiss — a real defect dropped.
- file-recall: of true_nature=file runs, how many filed.
- SILENT-DROP (⭐ autonomy): correct_autonomous=escalate but got dismiss — something a
  human had to see, silently dropped. The dangerous autonomy error.
- over-reach: correct_autonomous=escalate but got file/cleanup — acted when it should
  have asked (cheaper error than silent-drop).
- autonomy-hit: got == correct_autonomous.
- escalate-rate / inconsistency as before.
- TABLE-MISS runs are counted as EVAL NOISE and excluded from the model-behavior
  metrics (a replay that hit an unfrozen probe arg is a coverage artifact, not model
  judgement).

  SF_OBSERV_DISABLED=1 SF_TRIAGE_MODEL=deepseek/deepseek-v4-pro python3 score.py 3
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

    scored = noise = escalate = 0
    false_dismiss = file_gt = file_hit = 0
    silent_drop = over_reach = autonomy_hit = esc_gt = 0
    consistency = collections.defaultdict(set)
    confusion = collections.Counter()          # (true_nature -> got)
    autonomy_confusion = collections.Counter()  # (correct_autonomous -> got)

    for f in labeled:
        gt = f["ground_truth"]
        true_nature = gt["disposition"]
        correct_auto = gt.get("correct_autonomous") or true_nature
        table = f["probes"]
        for _ in range(k):
            d = triage.investigate(f["signal"], probe_table=table)
            if d.get("_meta", {}).get("table_miss"):
                noise += 1
                continue                        # coverage artifact — not model behavior
            got = d["disposition"]
            scored += 1
            confusion[(true_nature, got)] += 1
            autonomy_confusion[(correct_auto, got)] += 1
            consistency[f["id"]].add(got)
            if got == "escalate":
                escalate += 1
            # safety (vs true_nature)
            if true_nature == "file":
                file_gt += 1
                if got == "file":
                    file_hit += 1
                if got == "dismiss":
                    false_dismiss += 1
            # autonomy gate (vs correct_autonomous)
            if got == correct_auto:
                autonomy_hit += 1
            if correct_auto == "escalate":
                esc_gt += 1
                if got == "dismiss":
                    silent_drop += 1
                elif got in ("file", "cleanup"):
                    over_reach += 1

    inconsistent = [fid for fid, s in consistency.items() if len(s) > 1]
    pct = lambda a, b: f"{a}/{b} = {a / b:.2f}" if b else f"{a}/{b} = n/a"

    print(f"=== RESULT · model={config.TRIAGE_MODEL} · prompt={triage.PROMPT_SHA} · k={k} ===")
    print(f"scored runs: {scored}   table-miss noise (excluded): {noise}\n")
    print("SAFETY (vs true_nature):")
    print(f"  FALSE-DISMISS   : {pct(false_dismiss, file_gt)}   ⭐ real defect dropped")
    print(f"  file-recall     : {pct(file_hit, file_gt)}")
    print("AUTONOMY GATE (vs correct_autonomous):")
    print(f"  SILENT-DROP     : {pct(silent_drop, esc_gt)}   ⭐ needed-a-human, dropped")
    print(f"  over-reach      : {pct(over_reach, esc_gt)}   (acted when should ask)")
    print(f"  autonomy-hit    : {pct(autonomy_hit, scored)}")
    print(f"escalate rate     : {pct(escalate, scored)}")
    print(f"inconsistent (varied across k): {len(inconsistent)}/{len(labeled)}  {inconsistent[:8]}")
    print("confusion (true_nature -> got):")
    for (g, got), n in sorted(confusion.items()):
        flag = "  <-- FALSE-DISMISS" if g == "file" and got == "dismiss" else ""
        print(f"  {g:>8} -> {got:<8} {n}{flag}")
    print("autonomy confusion (correct_autonomous -> got):")
    for (g, got), n in sorted(autonomy_confusion.items()):
        flag = "  <-- SILENT-DROP" if g == "escalate" and got == "dismiss" else ""
        print(f"  {g:>8} -> {got:<8} {n}{flag}")


if __name__ == "__main__":
    score(int(sys.argv[1]) if len(sys.argv) > 1 else 3)
