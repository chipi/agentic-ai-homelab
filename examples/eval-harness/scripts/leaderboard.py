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
import json
import math
import random
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



# ── is the ordering above real? ──────────────────────────────────────────────
# A leaderboard sorted by a mean always produces an ordering. Whether that ordering
# survives re-running the experiment is a different question, and it is the only one
# that matters -- so the answer is printed, not left to the reader.
#
# THREE readings, all order-independent, all computed over the whole table at once.
# What is NOT used: any walk down the table comparing each arm to a running "leader".
# That is a sorting algorithm, not a comparison -- its answer depends on whether you
# walk top-down or bottom-up, and on this data those two directions disagree about
# whether the top arm is separated from the field at all.

#: Two per-item values closer than this count as tied.
#:
#: 1e-9 is right for scores stored at full precision and WRONG for scores rounded on the
#: way to disk: at 6 decimals, arms that genuinely tie can land ~1e-6 apart and get
#: strictly ordered. The previous comment here claimed this tolerance "absorbs the
#: 6-decimal rounding". It does not.
#:
#: The fix is not a looser constant -- 1e-6 would merge a real gap (the closest distinct
#: rouge1 means on this data are 8.8e-7 apart). It is to notice the precision and say so,
#: so low-precision runs get rescored rather than quietly mis-tied.
_TIE_TOL = 1e-9

#: Below this many decimals, stored scores cannot be tie-detected reliably.
_MIN_TIE_DECIMALS = 8


#: Raw per-item values as they came off disk, before any averaging. Precision has to be
#: measured HERE: `fmean` returns full float precision whatever it was given, so checking
#: the means reports 17 decimals for scores that were stored with 6.
_RAW_SEEN: List[float] = []


def _stored_decimals(values: List[float]) -> int:
    """How many decimal places the stored values actually carry."""
    best = 0
    for v in values[:500]:
        t = f"{v!r}"
        if "." in t and "e" not in t:
            best = max(best, len(t.split(".")[1].rstrip("0")))
    return best

_NEMENYI_Q05 = {  # Demsar 2006, alpha = 0.05: studentised range / sqrt(2)
    2: 1.960, 3: 2.343, 4: 2.569, 5: 2.728, 6: 2.850, 7: 2.949, 8: 3.031, 9: 3.102,
    10: 3.164, 11: 3.219, 12: 3.268, 13: 3.313, 14: 3.354, 15: 3.391, 16: 3.426,
    17: 3.458, 18: 3.489, 19: 3.517, 20: 3.544, 21: 3.569, 22: 3.593, 23: 3.616,
    24: 3.637, 25: 3.658,
}


def _per_item(runs: List[dict], run_dirs: Dict[int, Path], metric: str) -> Dict[str, float]:
    """One value per item for one arm: the mean over that arm's repeats."""
    acc: Dict[str, List[float]] = defaultdict(list)
    for r in runs:
        d = run_dirs.get(id(r))
        if not d:
            continue
        pj = d / "predictions.jsonl"
        if not pj.is_file():
            continue
        for line in pj.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            if metric in row:
                acc[row["item_id"]].append(float(row[metric]))
                _RAW_SEEN.append(row[metric])
    return {k: statistics.fmean(v) for k, v in acc.items() if v}


def _significance(matrix: Dict[str, Dict[str, float]], metric: str, seed: int = 20260925) -> None:
    """Print the global test, the critical difference, and per-arm rank intervals."""
    arms = sorted(matrix)
    items = sorted(set.intersection(*(set(matrix[a]) for a in arms))) if arms else []
    k, N = len(arms), len(items)
    if k < 2 or N < 3:
        print(f"\n  Not enough paired data for a significance test "
              f"({k} arm(s), {N} shared item(s)). Ordering above is a mean, nothing more.")
        return
    V = {a: [matrix[a][i] for i in items] for a in arms}

    # Within-item ranks: 1 = best on THAT item. Ranking inside the item is what removes
    # the item effect -- on a real dataset most of the variance is "some items are hard
    # for everyone", and an unpaired comparison leaves all of it in the noise.
    ranks: Dict[str, List[float]] = {a: [] for a in arms}
    for j in range(N):
        col = sorted(((V[a][j], a) for a in arms), reverse=True)
        i = 0
        while i < len(col):
            grp = [i]
            # TIES NEED A TOLERANCE, not exact equality. These values are means of scores
            # that were rounded to 6 decimals on the way to disk, and several of these
            # metrics are ratios of small integers -- so two arms that genuinely tied on an
            # item come back differing by ~1e-7 and get strictly ordered. Exact equality
            # found 179 tied pairs where 216 were real, and that alone moved one reported
            # p-value from 0.110 to 0.138. `fmean` adds its own ~5e-17 on top.
            while (
                grp[-1] + 1 < len(col)
                and abs(col[grp[-1] + 1][0] - col[i][0]) <= _TIE_TOL
            ):
                grp.append(grp[-1] + 1)
            shared = statistics.fmean(x + 1 for x in grp)
            for x in grp:
                ranks[col[x][1]].append(shared)
            i = grp[-1] + 1
    avg_rank = {a: statistics.fmean(ranks[a]) for a in arms}

    decimals = _stored_decimals(_RAW_SEEN)
    if decimals and decimals < _MIN_TIE_DECIMALS:
        print(f"\n  NOTE: these runs store scores to ~{decimals} decimals, so arms that\n"
              f"        genuinely tie on an item can differ by rounding alone and be\n"
              f"        ordered anyway — which inflates the p-value. `make rescore` "
              f"regenerates\n        them at full precision.")

    # Friedman, as a permutation test: shuffle which arm got which rank WITHIN each item
    # -- exactly the world where arms do not matter -- and see how often chance beats the
    # observed spread. No distributional assumption, no scipy.
    rng = random.Random(seed)
    stat = lambda rk: sum(statistics.fmean(rk[a]) ** 2 for a in arms)  # noqa: E731
    observed = stat(ranks)
    by_item = [[ranks[a][j] for a in arms] for j in range(N)]
    B, hits = 5000, 0
    for _ in range(B):
        perm: Dict[str, List[float]] = {a: [] for a in arms}
        for j in range(N):
            row = by_item[j][:]
            rng.shuffle(row)
            for a, v in zip(arms, row):
                perm[a].append(v)
        if stat(perm) >= observed:
            hits += 1
    p = (hits + 1) / (B + 1)

    cd = _NEMENYI_Q05.get(k, 3.658) * math.sqrt(k * (k + 1) / (6.0 * N))
    span = max(avg_rank.values()) - min(avg_rank.values())
    pairs = [(a, b) for a in arms for b in arms if avg_rank[b] - avg_rank[a] > cd]

    print(f"\n  IS THE ORDERING REAL?   metric={metric}  k={k} arms  N={N} items")
    print(f"    global test (permutation on within-item ranks): p = {p:.4f}"
          f"  ->  {'an arm effect exists' if p < 0.05 else 'NO detectable arm effect'}")
    print(f"    Nemenyi critical difference = {cd:.2f} rank positions; observed span = {span:.2f}")
    print(f"    pairs distinguishable: {len(pairs)} of {k * (k - 1) // 2}")
    if p >= 0.05:
        print("    The table above is sorted, but these runs do not show the arms differ.\n"
              "    Do not report an ordering from it.")
    elif not pairs:
        print("    An effect exists, but NO PAIR is distinguishable once all comparisons\n"
              "    are accounted for. 'Which arm is better than which' has no answer here.")

    # Resample ITEMS, re-rank the whole table each time, and report PROBABILITIES rather
    # than an interval.
    #
    # This used to print a 95% rank interval per arm. Those are MARGINAL: each is correct
    # on its own, but jointly they cover only ~57% of resamples, and two non-overlapping
    # intervals read as "this pair is separated" when that is exactly the claim they
    # cannot make -- the critical-difference line above is the only thing that can. A
    # simultaneous band would be honest but useless here: its half-width is 14-17 rank
    # positions out of 24.
    #
    # P(top 5) and P(bottom 5) answer the question people actually bring to a leaderboard
    # -- "is this one of the good ones" -- and cannot be misread as a pairwise verdict.
    R = 2000
    top_n = max(1, min(5, k // 4))
    tally: Dict[str, List[int]] = {a: [] for a in arms}
    for _ in range(R):
        idx = [rng.randrange(N) for _ in range(N)]
        mu = {a: statistics.fmean(V[a][j] for j in idx) for a in arms}
        for pos, a in enumerate(sorted(arms, key=lambda x: -mu[x]), 1):
            tally[a].append(pos)
    width = max(len(a) for a in arms) + 2
    print(f"\n    {'arm':{width}} {'avg rank':>9} {'P(1st)':>8} "
          f"{f'P(top {top_n})':>10} {f'P(bot {top_n})':>10}")
    for a in sorted(arms, key=lambda x: avg_rank[x]):
        t = tally[a]
        p1 = sum(1 for x in t if x == 1) / R
        pt = sum(1 for x in t if x <= top_n) / R
        pb = sum(1 for x in t if x > k - top_n) / R
        print(f"    {a:{width}} {avg_rank[a]:9.2f} {p1:8.2f} {pt:10.2f} {pb:10.2f}")
    print(f"    Probabilities over resampled items: how often this arm lands 1st, in the\n"
          f"    top {top_n}, in the bottom {top_n}. NOT a pairwise claim -- the\n"
          f"    critical-difference line above is the only pairwise verdict here.")



def _frontier(rows: List[dict], quality: str, kinds: Dict[str, str]) -> None:
    """Which arms are on the menu at all, across quality, cost and speed together.

    An arm is DOMINATED when some other arm is at least as good on quality AND costs no
    more AND is no slower. A dominated arm is off the table whatever your budget is --
    there is simply a better version of the same trade. What is left is the real choice.

    The frontier is only as meaningful as the quality metric handed to it: computed on a
    length-sensitive facet it ranks verbosity, and swapping that facet for its opposite
    produced a completely different frontier once -- with the same runs. So the facet is
    named in the output, every time.
    """
    cost = next((k for k in rows[0] if kinds.get(k) == "cost" and k.startswith("total_")), None)
    cost = cost or next((k for k in rows[0] if kinds.get(k) == "cost"), None)
    speed = next((k for k in rows[0] if kinds.get(k) == "speed"), None)
    if not (cost and speed):
        print("\n  No frontier: needs a cost and a speed metric alongside quality.")
        return
    pts = {r["config_id"]: (r.get(quality), r.get(cost), r.get(speed)) for r in rows}
    pts = {a: v for a, v in pts.items() if None not in v}
    if len(pts) < 2:
        return

    def dominated(a: str) -> bool:
        qa, ca, la = pts[a]
        return any(
            qb >= qa and cb <= ca and lb <= la and (qb, -cb, -lb) != (qa, -ca, -la)
            for b, (qb, cb, lb) in pts.items()
            if b != a
        )

    front = sorted((a for a in pts if not dominated(a)), key=lambda a: -pts[a][0])
    beaten = sorted(a for a in pts if dominated(a))
    w = max(len(a) for a in pts) + 2
    print(f"\n  FRONTIER on {quality} / {cost} / {speed} — {len(front)} of {len(pts)} arms")
    print(f"    {'arm':{w}} {quality:>12} {cost:>12} {speed:>12}")
    for a in front:
        q, c, l = pts[a]
        print(f"    {a:{w}} {q:12.6f} {c:12.6f} {l:12.1f}")
    if beaten:
        print(f"    dominated (worse on all three than some other arm): {', '.join(beaten)}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dataset-id", required=True)
    ap.add_argument("--sort", help="metric to rank by (default: the first quality metric)")
    ap.add_argument("--asc", action="store_true", help="lower is better for the sort metric")
    # A dataset accumulates arms across config VERSIONS -- v1 and v2 of the same arm are
    # different measurements and must not share a row, but they do share a dataset. Without
    # a way to scope the table, the only ways to get a readable leaderboard are to delete
    # the older runs or to read past them. Deleting paid-for results to tidy a table is how
    # 18 arms were lost once; this is the alternative.
    ap.add_argument("--match", help="only arms whose config_id contains this substring")
    args = ap.parse_args()

    by_config: Dict[str, List[dict]] = defaultdict(list)
    # Where each run's artifacts live, so the significance test can reach its
    # predictions.jsonl. Per-item scores are what make a PAIRED comparison possible, and
    # a comparison that is not paired throws away the fact that every arm was graded on
    # the same items.
    run_dirs: Dict[int, Path] = {}
    for run in (RUNS.iterdir() if RUNS.is_dir() else []):
        m = run / "metrics.json"
        if m.is_file():
            d = read_json(m)
            if d.get("dataset_id") == args.dataset_id and (
                not args.match or args.match in d.get("config_id", "")
            ):
                by_config[d["config_id"]].append(d)
                run_dirs[id(d)] = run

    if not by_config:
        die(
            f"no runs on dataset {args.dataset_id!r}"
            + (f" matching {args.match!r}" if args.match else "")
            + ".\n  make runs-list   to see what exists"
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
    # The adapter's declared headline facet wins over alphabetical order. Explicit
    # --sort still overrides both.
    primary = next(
        (r.get("primary_metric") for runs in by_config.values() for r in runs
         if r.get("primary_metric") in all_keys),
        None,
    )
    sort_key = args.sort or primary or (
        quality[0] if quality else (descriptive[0] if descriptive else all_keys[0])
    )
    # SAY SO when the headline metric was picked alphabetically. Runs written before
    # adapters declared PRIMARY_METRIC carry none, so this falls through to whichever
    # quality metric sorts first by name -- for one set of runs here that is `grounding`,
    # an extractiveness measure, silently promoted to the ranking metric.
    if not args.sort and not primary:
        print(f"  NOTE: no run declares a primary metric, so {sort_key!r} was chosen by\n"
              f"        sort order, not by meaning. Pass --sort explicitly, or re-run with\n"
              f"        an adapter that sets PRIMARY_METRIC.")
    # SAY SO when the table mixes config versions. v1 and v2 of one arm are different
    # measurements -- often different scorers -- and listing them side by side reads as
    # 48 models. The fix is to scope the view, never to delete the older runs.
    import re as _re
    versions = {m.group(0) for c in by_config for m in [_re.search(r"_v\d+$", c)] if m}
    if len(versions) > 1:
        print(f"  NOTE: this table mixes config versions ({', '.join(sorted(versions))}) —"
              f" {len(by_config)} rows.\n"
              f"        Those are different measurements, not repeats. Scope with"
              f" --match <version>.")
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

    matrix = {
        cid: _per_item(runs, run_dirs, sort_key)
        for cid, runs in by_config.items()
    }
    matrix = {c: v for c, v in matrix.items() if v}
    if matrix:
        _significance(matrix, sort_key)
    _frontier(rows, sort_key, kinds)
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
