#!/usr/bin/env python3
"""Compare two runs — and REFUSE when the comparison would be meaningless.

The refusals are the feature. A tool that always produces a number teaches you
to trust numbers that mean nothing:

  * different `dataset_id`  -> refused outright. Two metrics measured on
    different data are not comparable; the result would be a coincidence
    wearing a delta's clothes.
  * same build on both sides -> reported. If the code did not change, the
    delta is instrument or noise, not an improvement.
  * a delta smaller than the arm's own spread -> flagged as noise, with the
    command that measures that spread.

    python scripts/compare_runs.py --baseline <run_id> --candidate <run_id>
    python scripts/compare_runs.py --baseline <run_id> --candidate <run_id> --noise 0.01
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import RUNS, die, read_json  # noqa: E402


def load(run_id: str) -> dict:
    p = RUNS / run_id / "metrics.json"
    if not p.is_file():
        die(f"no run {run_id!r} (looked for {p})")
    return read_json(p)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--baseline", required=True)
    ap.add_argument("--candidate", required=True)
    ap.add_argument(
        "--noise",
        type=float,
        default=None,
        help="the arm's own spread; deltas at or below it are reported as noise. "
        "0 is a real answer — it means the arm is deterministic — so it is not "
        "the same as omitting the flag.",
    )
    args = ap.parse_args()

    a, b = load(args.baseline), load(args.candidate)

    if a["dataset_id"] != b["dataset_id"]:
        die(
            "REFUSED — different dataset_id:\n"
            f"    {args.baseline:32} {a['dataset_id']}\n"
            f"    {args.candidate:32} {b['dataset_id']}\n"
            "  A metric compared across two datasets is not a comparison, it is a\n"
            "  coincidence. Re-run one arm on the other's dataset_id."
        )

    print(f"dataset_id : {a['dataset_id']}")
    print(f"baseline   : {args.baseline}  build={a['build']['ref'][:12]}")
    print(f"candidate  : {args.candidate}  build={b['build']['ref'][:12]}")
    if a["build"]["ref"] == b["build"]["ref"]:
        print("\n  NOTE: identical build on both sides — any delta here is the")
        print("  instrument or run-to-run noise, not a code change.")
    if a["build"].get("dirty") or b["build"].get("dirty"):
        print("\n  NOTE: a build was DIRTY — its ref does not identify what ran.")

    keys = sorted(set(a["scores"]) | set(b["scores"]))
    w = max([len(k) for k in keys] + [6])
    print(f"\n  {'metric':{w}} {'baseline':>12} {'candidate':>12} {'delta':>12}   verdict")
    worth = 0
    for k in keys:
        if k not in a["scores"] or k not in b["scores"]:
            print(f"  {k:{w}} {'—':>12} {'—':>12} {'—':>12}   only on one side")
            continue
        av, bv = a["scores"][k], b["scores"][k]
        d = bv - av
        # `is not None`, not truthiness: NOISE=0 is the correct floor for a
        # deterministic arm, and treating it as "not given" nagged the user for
        # doing exactly the right thing.
        if args.noise is not None and abs(d) <= args.noise:
            verdict = f"NOISE (<= {args.noise})"
        elif d == 0:
            verdict = "identical"
        else:
            verdict = "better" if d > 0 else "worse"
            worth += 1
        print(f"  {k:{w}} {av:12.6f} {bv:12.6f} {d:+12.6f}   {verdict}")

    if args.noise is None:
        print(
            "\n  --noise was not given, so nothing was judged against the arm's own\n"
            "  spread. Measure it first:  make experiment-run CONFIG=... REPEAT=3"
        )
    print(f"\n  {worth} metric(s) moved beyond the stated noise floor")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
