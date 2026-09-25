#!/usr/bin/env python3
"""Rank every arm that ran on one dataset — quality, cost and speed together.

`run-compare` answers "is B better than A". When you sweep four models you want
one table, not six pairwise comparisons, and you want the three axes side by
side because they trade against each other:

    the best output is often the slowest and dearest, and the decision is
    usually "which is good ENOUGH per dollar", not "which scores highest"

Runs are grouped by `config_id`, so repeats of the same arm collapse into one
row and their spread is shown — an arm whose own spread exceeds the gap to its
neighbour is not distinguishable from it, and the table says so.

    python scripts/leaderboard.py --dataset-id my_v1
    python scripts/leaderboard.py --dataset-id my_v1 --sort overlap_f1
"""

from __future__ import annotations

import argparse
import statistics
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import (  # noqa: E402
    RUNS,
    classify_metrics,
    die,
    read_json,
)

# COST_KEYS / SPEED_KEYS / DESCRIPTIVE_KEYS now live in _common, so that
# compare_runs.py judges direction the same way this ranks it.


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dataset-id", required=True)
    ap.add_argument("--sort", help="metric to rank by (default: the first quality metric)")
    ap.add_argument("--asc", action="store_true", help="lower is better for the sort metric")
    args = ap.parse_args()

    by_config: Dict[str, List[dict]] = defaultdict(list)
    for run in (RUNS.iterdir() if RUNS.is_dir() else []):
        m = run / "metrics.json"
        if m.is_file():
            d = read_json(m)
            if d.get("dataset_id") == args.dataset_id:
                by_config[d["config_id"]].append(d)

    if not by_config:
        die(
            f"no runs on dataset {args.dataset_id!r}.\n"
            "  make runs-list   to see what exists"
        )

    all_keys = sorted({k for runs in by_config.values() for r in runs for k in r["scores"]})
    # An adapter may declare what ITS metrics mean; runs carry the declaration. Without
    # this the sort key falls to whatever sorts first among the unclassified, which ranked
    # a ten-model sweep by `compression` — a length ratio — and called it quality.
    declared: dict[str, str] = {}
    for runs in by_config.values():
        for r in runs:
            declared.update(r.get("metric_kinds") or {})
    kinds = classify_metrics(declared)
    quality = [
        k for k in all_keys
        if kinds.get(k, "quality") == "quality" and not k.startswith("total_")
    ]
    descriptive = [k for k in all_keys if kinds.get(k) == "descriptive"]
    sort_key = args.sort or (quality[0] if quality else (descriptive[0] if descriptive else all_keys[0]))
    ranking_on_descriptive = kinds.get(sort_key) == "descriptive"
    if sort_key not in all_keys:
        die(f"no metric {sort_key!r} on these runs. Available: {', '.join(all_keys)}")

    rows = []
    for config_id, runs in by_config.items():
        # EVERY run's tier, not runs[0]'s. Taking the first one meant a config whose
        # earliest run predated the reference (reference_tier: None) suppressed the
        # SILVER warning below — while the quality column on that very row came only
        # from the silver-scored runs. A model-generated number, printed as if it were
        # ground truth, which is the one thing this table must never do.
        tiers = {r.get("reference_tier") for r in runs if r.get("reference_tier")}
        row = {
            "config_id": config_id,
            "n_runs": len(runs),
            "tier": "+".join(sorted(tiers)) if tiers else "—",
            "tiers": tiers,
        }
        for k in all_keys:
            vals = [r["scores"][k] for r in runs if k in r["scores"]]
            if vals:
                row[k] = statistics.fmean(vals)
                row[f"__spread_{k}"] = max(vals) - min(vals)
        rows.append(row)

    rows.sort(key=lambda r: r.get(sort_key, float("inf") if args.asc else float("-inf")),
              reverse=not args.asc)

    show = quality + descriptive + [k for k in all_keys if kinds.get(k) in ("cost", "speed")]
    show = [k for k in show if k in all_keys]
    w = max(len(r["config_id"]) for r in rows) + 2
    print(f"dataset: {args.dataset_id}   ranked by: {sort_key}"
          f" ({'lower' if args.asc else 'higher'} is better)\n")
    header = f"  {'arm':{w}} {'runs':>4}  " + "  ".join(f"{k:>16}" for k in show)
    print(header)
    print("  " + "-" * (len(header) - 2))
    for i, r in enumerate(rows, 1):
        cells = "  ".join(
            (f"{r[k]:16.6f}" if k in r else f"{'—':>16}") for k in show
        )
        print(f"  {r['config_id']:{w}} {r['n_runs']:>4}  {cells}")

    if ranking_on_descriptive:
        print(
            f"\n  RANKED ON A DESCRIPTIVE METRIC ({sort_key}) — it measures what the output\n"
            "  WAS, not whether it was good, so this ordering rewards verbosity. Author\n"
            "  references (make reference-create) so runs carry a quality score, or pass\n"
            "  --sort <metric> explicitly."
        )

    # The honest caveat: a gap smaller than an arm's own spread is not a ranking.
    spread = rows[0].get(f"__spread_{sort_key}", 0.0)
    if len(rows) > 1 and sort_key in rows[0] and sort_key in rows[1]:
        gap = abs(rows[0][sort_key] - rows[1][sort_key])
        if spread and gap <= spread:
            print(
                f"\n  TOP TWO ARE NOT SEPARATED: gap {gap:.6f} on {sort_key} is within the\n"
                f"  leader's own run-to-run spread ({spread:.6f}). Treat them as tied, or\n"
                f"  run more repeats before choosing."
            )
    if any("silver" in r["tiers"] for r in rows):
        print(
            "\n  Scored against SILVER references (model-generated). Good for ranking\n"
            "  these arms against each other; not a claim that any of them is correct."
        )
    if not any(kinds.get(k) == "cost" for k in show):
        print(
            "\n  No cost recorded. Add usd_per_mtok_in / usd_per_mtok_out to the configs\n"
            "  so the ranking can weigh quality against price."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
