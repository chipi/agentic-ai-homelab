#!/usr/bin/env python3
"""How good is a MODEL-AUTHORED reference as a stand-in for a trusted one?

Most of the time you have no gold. The usual move is to have a strong model write the
references — "silver" — and rank your candidates against those. This asks the question
nobody asks: **does that ranking match the one real ground truth would have given?**

It costs nothing. "Author silver with model X, same prompt and settings as the arms" is
exactly what X already produced on this dataset, so every arm on disk is a candidate
silver author and all of them can be tried at once.

For each candidate author A:
    use A's outputs as the reference set
    score every OTHER arm against them, and rank those arms
    compare that ranking to the one the TRUSTED reference gives for the same arms

A's own row is excluded throughout — an author that also competes scores itself first,
and that artifact is not the interesting part.

    make silver-calibrate DATASET_ID=my_v1 REF_MATCH=_v1 ARM_MATCH=_v2

Read the output against the CEILING it prints. Two runs of the same arms against the
same gold do not rank identically either, so the gold-vs-gold retest correlation is the
best any proxy could score. A silver at rho 0.5 against a ceiling of 0.93 is not "fairly
good"; it is about half of the available agreement.

`--group-by` (default `family`) reports the bias that matters most and that excluding the
author does NOT remove: whether a silver author systematically promotes models of its own
kind.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import statistics
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import REFERENCES, RUNS, ROOT, die, read_json  # noqa: E402
from experiment_run import load_adapter, _score_wants_source  # noqa: E402


def _spearman(a: List[float], b: List[float]) -> float:
    ra = {v: i for i, v in enumerate(sorted(a))}
    rb = {v: i for i, v in enumerate(sorted(b))}
    x = [ra[v] for v in a]
    y = [rb[v] for v in b]
    mx, my = statistics.fmean(x), statistics.fmean(y)
    num = sum((xi - mx) * (yi - my) for xi, yi in zip(x, y))
    den = (sum((xi - mx) ** 2 for xi in x) * sum((yi - my) ** 2 for yi in y)) ** 0.5
    return num / den if den else 0.0


def _collect(dataset_id: str, match: Optional[str]) -> Dict[str, Dict[str, Any]]:
    """arm -> {"texts": {item: [text, ...]}, "params": {...}, "adapter": str}"""
    acc: Dict[str, Dict[str, Any]] = {}
    for mp in glob.glob(str(RUNS / "*" / "metrics.json")):
        m = read_json(Path(mp))
        if m.get("dataset_id") != dataset_id:
            continue
        cid = m.get("config_id", "")
        if match and match not in cid:
            continue
        arm = cid
        for suffix in ("_v1", "_v2", "_v3"):
            if arm.endswith(suffix):
                arm = arm[: -len(suffix)]
        entry = acc.setdefault(arm, {"texts": defaultdict(list), "params": m.get("params") or {},
                                     "adapter": m.get("adapter")})
        for f in glob.glob(os.path.join(os.path.dirname(mp), "outputs", "*.txt")):
            entry["texts"][os.path.basename(f)[:-4]].append(
                Path(f).read_text(encoding="utf-8").strip())
    return acc


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dataset-id", required=True)
    ap.add_argument("--ref-match", help="config_id substring for runs used AS references")
    ap.add_argument("--arm-match", help="config_id substring for runs used AS arms")
    ap.add_argument("--reference-id", help="trusted reference dir under data/references "
                                           "(default: the one the runs recorded)")
    ap.add_argument("--metric", default=None, help="default: the adapter's PRIMARY_METRIC")
    ap.add_argument("--group-by", default="family",
                    help="params key for the sibling-bias report; '' to skip")
    args = ap.parse_args()

    refs_side = _collect(args.dataset_id, args.ref_match)
    arms_side = _collect(args.dataset_id, args.arm_match)
    arms = sorted(set(refs_side) & set(arms_side))
    if len(arms) < 3:
        die(f"need at least 3 arms present on both sides; found {len(arms)}")

    spec = arms_side[arms[0]]["adapter"]
    if not spec:
        die("runs record no adapter — cannot score")
    _call, score, _aid, adapter_path, _w, _fp = load_adapter(str(ROOT.parent / spec), None)
    wants_source = _score_wants_source(score)
    metric = args.metric
    if not metric:
        from experiment_run import _adapter_primary_metric
        metric = _adapter_primary_metric(adapter_path) or "overlap_f1"

    ref_id = args.reference_id
    if not ref_id:
        for mp in glob.glob(str(RUNS / "*" / "metrics.json")):
            m = read_json(Path(mp))
            if m.get("dataset_id") == args.dataset_id:
                ref_id = ((m.get("fingerprint") or {}).get("data") or {}).get("reference_id")
                if ref_id:
                    break
    if not ref_id:
        die("no trusted reference found — this measures a proxy AGAINST ground truth, "
            "so there is nothing to calibrate without one")
    trusted = {os.path.basename(f)[:-4]: Path(f).read_text(encoding="utf-8").strip()
               for f in glob.glob(str(REFERENCES / ref_id / "*.txt"))}
    mat = ROOT / "data/materialized" / args.dataset_id
    sources = {os.path.basename(f)[:-4]: Path(f).read_text(encoding="utf-8", errors="replace")
               for f in glob.glob(str(mat / "*.txt"))}
    items = sorted(trusted)

    def rank_against(refs: Dict[str, str], side: Dict[str, Dict[str, Any]],
                     subject: List[str]) -> Dict[str, float]:
        out = {}
        for a in subject:
            vals = []
            for i in items:
                if i not in refs:
                    continue
                for text in side[a]["texts"].get(i, []):
                    s = (score(text, refs[i], sources.get(i)) if wants_source
                         else score(text, refs[i]))
                    if metric in s:
                        vals.append(s[metric])
            if vals:
                out[a] = statistics.fmean(vals)
        return out

    print(f"silver calibration on {args.dataset_id}   metric={metric}   arms={len(arms)}")
    print(f"  trusted reference: {ref_id}")

    gold_arm = rank_against(trusted, arms_side, arms)
    gold_ref = rank_against(trusted, refs_side, arms)
    common = sorted(set(gold_arm) & set(gold_ref))
    ceiling = _spearman([gold_ref[a] for a in common], [gold_arm[a] for a in common])
    print(f"\n  CEILING — the same arms scored against the same trusted reference, from two\n"
          f"  different sets of runs, agree at rho = {ceiling:+.3f}. No proxy can beat this.")

    key = args.group_by or None
    group = {a: (arms_side[a]["params"].get(key) if key else None) for a in arms}

    rows = []
    for author in arms:
        refs = {i: t[0] for i, t in refs_side[author]["texts"].items() if t}
        subject = [a for a in arms if a != author]
        silver = rank_against(refs, arms_side, subject)
        subject = sorted(set(silver) & set(gold_arm))
        if len(subject) < 3:
            continue
        rho = _spearman([gold_arm[a] for a in subject], [silver[a] for a in subject])
        g = {a: i for i, a in enumerate(sorted(subject, key=lambda x: -gold_arm[x]), 1)}
        s = {a: i for i, a in enumerate(sorted(subject, key=lambda x: -silver[x]), 1)}
        sibs = [a for a in subject if key and group[a] and group[a] == group[author]]
        lift = statistics.fmean(g[a] - s[a] for a in sibs) if sibs else None
        rows.append((rho, lift, author, len(sibs)))

    rows.sort(key=lambda r: -r[0])
    w = max(len(r[2]) for r in rows) + 2
    print(f"\n  {'silver author':{w}}{'rho vs trusted':>16}{'sibling lift':>14}")
    print("  " + "-" * (w + 30))
    for rho, lift, author, n in rows:
        lift_s = f"{lift:+.1f}" if lift is not None else "—"
        print(f"  {author:{w}}{rho:>16.3f}{lift_s:>14}   ({n} sibling(s))")

    rr = [r[0] for r in rows]
    ll = [r[1] for r in rows if r[1] is not None]
    print(f"\n  rho: min {min(rr):+.3f}  mean {statistics.fmean(rr):+.3f}  max {max(rr):+.3f}"
          f"   (ceiling {ceiling:+.3f})")
    if ll:
        pos = sum(1 for x in ll if x > 0)
        print(f"  sibling lift: mean {statistics.fmean(ll):+.1f} rank positions, positive for"
              f" {pos} of {len(ll)} authors")
        if pos > len(ll) * 0.7:
            print(f"\n  A silver author systematically PROMOTES models grouped with it by"
                  f" {args.group_by!r}.\n"
                  "  Excluding the author's own row does not remove this: the bias is not an\n"
                  "  author scoring itself, it is an author rewarding its own kind's style.\n"
                  "  A silver-ranked leaderboard is therefore not merely noisier than a gold\n"
                  "  one -- it is biased in a direction you can predict from who wrote it.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
