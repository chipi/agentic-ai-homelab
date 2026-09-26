#!/usr/bin/env python3
"""One pre-registered pair, tested on its own: sign-flip permutation on paired deltas.

    python scripts/pair_test.py --dataset-id cnn_dailymail_200 \
        --a cnn_deepseek_m_n200_v1 --b cnn_anthropic_m_n200_v1 --metric coverage

WHY A SECOND TEST, WHEN leaderboard.py ALREADY HAS ONE
  `_significance` answers "which of all k(k-1)/2 pairs differ?" and pays the Nemenyi
  multiplicity price for every one of them. That is the right price for that question and
  the wrong question for a decision. A comparison fixed BEFORE looking -- "is the 67x
  dearer arm better?" -- is one test, and correcting it for 275 comparisons nobody made
  is throwing away power to answer a question that was never asked.

  The honesty condition is that the pair is named in advance. Six pairs picked after
  reading the table are a search, not a test; EVAL_REPORT.md section 3.1b says so about its
  own six and Holm-corrects them. --family N applies BONFERRONI (alpha/N) here, which is
  Holm's strictest step applied to every member: conservative, never the reverse. Holm's
  step-down needs every p-value in the family at once, which one pair does not have.

THE TEST
  Per item, delta = A - B (items both arms scored, means over repeats). Under the null the
  sign of each delta is a coin flip, so: flip each sign at random, recompute the mean,
  repeat. p = how often |mean| of a flipped sample reaches the observed |mean|. No
  distributional assumption, and it keeps the pairing -- which matters here, where ~74% of
  the variance is between articles.
"""

from __future__ import annotations

import argparse
import json
import random
import statistics
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from _common import DATA, SOURCES, read_json  # noqa: E402


def per_item(runs_dir: Path, dataset_id: str, config_id: str, metric: str) -> dict[str, float]:
    acc: dict[str, list[float]] = defaultdict(list)
    for d in sorted(runs_dir.glob("*")):
        mj, pj = d / "metrics.json", d / "predictions.jsonl"
        if not (mj.is_file() and pj.is_file()):
            continue
        m = read_json(mj)
        if m.get("dataset_id") != dataset_id or m.get("config_id") != config_id:
            continue
        for line in pj.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                if metric in row:
                    acc[row["item_id"]].append(float(row[metric]))
    return {k: statistics.fmean(v) for k, v in acc.items() if v}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dataset-id", required=True)
    ap.add_argument("--a", required=True, help="config_id of the arm under test")
    ap.add_argument("--b", required=True, help="config_id it is compared against")
    ap.add_argument("--metric", default="coverage")
    ap.add_argument("--runs-dir", default=None, help="default: data/runs")
    ap.add_argument("--exclude-dataset", help="drop items this dataset also contains")
    ap.add_argument("--permutations", type=int, default=20000)
    ap.add_argument("--family", type=int, default=1,
                    help="how many pairs were tested together (Bonferroni: alpha/family)")
    ap.add_argument("--seed", type=int, default=20260926)
    args = ap.parse_args()

    runs_dir = Path(args.runs_dir) if args.runs_dir else DATA / "runs"
    A = per_item(runs_dir, args.dataset_id, args.a, args.metric)
    B = per_item(runs_dir, args.dataset_id, args.b, args.metric)
    items = sorted(set(A) & set(B))
    if args.exclude_dataset:
        prior = {p.stem for p in (SOURCES / args.exclude_dataset).glob("*.txt")}
        items = [i for i in items if i not in prior]
    if len(items) < 3:
        print(f"  only {len(items)} shared item(s) — nothing to test")
        return 1

    deltas = [A[i] - B[i] for i in items]
    obs = statistics.fmean(deltas)
    wins = sum(1 for d in deltas if d > 0)
    ties = sum(1 for d in deltas if d == 0)

    rng = random.Random(args.seed)
    hits = sum(
        1 for _ in range(args.permutations)
        if abs(statistics.fmean(d if rng.random() < 0.5 else -d for d in deltas)) >= abs(obs)
    )
    p = (hits + 1) / (args.permutations + 1)
    # BONFERRONI, not Holm. One pair cannot do Holm: the step-down procedure compares the
    # smallest p to alpha/m, the next to alpha/(m-1), and so on, which needs the whole
    # family's p-values at once. alpha/m applied to every member is the strictest step
    # applied throughout -- always conservative relative to Holm, never anti-conservative,
    # so a pair that clears this has cleared Holm too. A pair that does NOT clear it may
    # still clear Holm; run the family's p-values through the step-down to find out.
    thresh = 0.05 / args.family

    print(f"  {args.a}  vs  {args.b}    metric={args.metric}  N={len(items)}")
    print(f"    delta (A - B)      {obs:+.4f}")
    print(f"    items A wins       {wins}/{len(items)}" + (f" ({ties} exact tie(s))" if ties else ""))
    print(f"    sign-flip p        {p:.4f}  ({args.permutations} permutations)")
    if args.family > 1:
        verdict = "SEPARATED" if p < thresh else "NOT-SEPARATED"
        print(f"    Bonferroni/{args.family}     threshold {thresh:.4f} -> {verdict}")
        if p >= thresh:
            print("    (conservative: Holm's later steps are looser — check the family)")
    else:
        print(f"    verdict            {'SEPARATED' if p < 0.05 else 'NOT-SEPARATED'} at 0.05")
        print("    (uncorrected: valid only if this pair was named before the table was read)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
