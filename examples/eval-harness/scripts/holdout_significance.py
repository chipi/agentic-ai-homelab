#!/usr/bin/env python3
"""The significance block, restricted to items a previous dataset did NOT contain.

    python scripts/holdout_significance.py --dataset-id cnn_dailymail_200 \
        --exclude-dataset cnn_dailymail_20 --metric coverage

WHY THIS EXISTS
  `fetch.py --n 200` pages from offset 0 of the same split, so the 20-article slice is
  NESTED inside the 200. Arms chosen because they ranked high on those 20 are being
  re-measured on a set that still contains them — 10% of the new sample is the sample
  that selected them. A replication claim has to be read on the 180 items that did not
  take part in the selection, and "all 200" cannot make that claim.

  It reuses leaderboard.py's own `_significance`, deliberately. A second implementation
  of the same test is a second set of numbers to reconcile; the point here is the item
  set, not the statistics.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import leaderboard as lb  # noqa: E402
from _common import RUNS, SOURCES, read_json  # noqa: E402


def _matrix(dataset_id: str, metric: str, keep: set[str] | None, match: str | None):
    """config_id -> item_id -> mean score over that config's repeats."""
    acc: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    runs = 0
    for d in sorted(RUNS.glob("*")):
        mj = d / "metrics.json"
        pj = d / "predictions.jsonl"
        if not (mj.is_file() and pj.is_file()):
            continue
        m = read_json(mj)
        if m.get("dataset_id") != dataset_id:
            continue
        cid = m.get("config_id", d.name)
        if match and match not in cid:
            continue
        runs += 1
        for line in pj.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            if metric not in row:
                continue
            if keep is not None and row["item_id"] not in keep:
                continue
            acc[cid][row["item_id"]].append(float(row[metric]))
            lb._RAW_SEEN.append(row[metric])
    return {a: {i: statistics.fmean(v) for i, v in items.items()} for a, items in acc.items()}, runs


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dataset-id", required=True)
    ap.add_argument("--exclude-dataset", help="drop every item this dataset also contains")
    ap.add_argument("--metric", default="coverage")
    ap.add_argument("--match", help="only config_ids containing this substring")
    args = ap.parse_args()

    keep = None
    if args.exclude_dataset:
        prior = {p.stem for p in (SOURCES / args.exclude_dataset).glob("*.txt")}
        if not prior:
            print(f"  no items found under data/sources/{args.exclude_dataset} — nothing excluded")
        all_items = {p.stem for p in (SOURCES / args.dataset_id).glob("*.txt")}
        keep = all_items - prior
        print(f"  {args.dataset_id}: {len(all_items)} items, "
              f"{len(prior & all_items)} shared with {args.exclude_dataset}, "
              f"{len(keep)} held out")

    matrix, runs = _matrix(args.dataset_id, args.metric, keep, args.match)
    if not matrix:
        print("  no runs matched")
        return 1
    print(f"  {runs} run(s), {len(matrix)} arm(s)")
    lb._significance(matrix, args.metric)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
