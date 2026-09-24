#!/usr/bin/env python3
"""Promote a run to a baseline.

A baseline is frozen: never edited, only superseded. It is the number future
work is judged against, so promoting one is a decision, not a copy.

Two things are refused, because both produce a baseline nobody can act on:

  * a run whose build is unknown or dirty — you cannot later say WHICH code
    earned the number
  * a promotion with no reason — six months on, "why is this the baseline?"
    has no answer, and the number gets cargo-culted

    python scripts/promote_baseline.py --run <run_id> --reason "beat prev by 4% on n=40"
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import BASELINES, RUNS, die, now, read_json, write_json  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--run", required=True)
    ap.add_argument("--reason", required=True, help="why this run earned promotion")
    ap.add_argument("--baseline-id", help="default: <dataset_id>_baseline")
    ap.add_argument("--allow-dirty", action="store_true", help="promote from a dirty tree anyway")
    ap.add_argument(
        "--allow-unknown-build",
        action="store_true",
        help="promote a run whose build could not be identified — a DIFFERENT and worse "
        "problem than a dirty tree, so it takes its own flag",
    )
    args = ap.parse_args()

    src = RUNS / args.run / "metrics.json"
    if not src.is_file():
        die(f"no run {args.run!r} (looked for {src})")
    m = read_json(src)

    build = m.get("build") or {}
    if build.get("ref", "unknown") == "unknown" and not args.allow_unknown_build:
        die(
            "REFUSED — this run does not identify its build.\n"
            "  A baseline whose build is unknown cannot be attributed to any code.\n"
            "  Declare it and re-run:  EVAL_BUILD_REF=<version|digest|sha> make experiment-run ...\n"
            "  (--allow-unknown-build overrides, but then the baseline names no system.)"
        )
    if build.get("dirty") and not args.allow_dirty:
        die(
            f"REFUSED — run {args.run} was produced by a DIRTY tree.\n"
            f"  build.ref={build.get('ref', '?')[:12]} does not describe what actually ran.\n"
            "  Commit, re-run, and promote that — or --allow-dirty and say why in --reason."
        )
    if len(args.reason.split()) < 3:
        die("REFUSED — --reason must be a sentence, not a word. It is the answer to "
            '"why is this the baseline?" in six months.')

    baseline_id = args.baseline_id or f"{m['dataset_id']}_baseline"
    out = BASELINES / f"{baseline_id}.json"
    supersedes = None
    if out.is_file():
        prev = read_json(out)
        supersedes = prev.get("promoted_from")
        archive = BASELINES / "superseded" / f"{baseline_id}_{prev['promoted_at'].replace(':', '')}.json"
        write_json(archive, prev)
        print(f"  previous baseline archived -> {archive.relative_to(BASELINES)}")

    write_json(
        out,
        {
            "baseline_id": baseline_id,
            "dataset_id": m["dataset_id"],
            "promoted_from": m["run_id"],
            "promoted_at": now(),
            "reason": args.reason,
            "scores": m["scores"],
            "build": build,
            "supersedes": supersedes,
        },
    )
    print(f"{out}")
    w = max([len(k) for k in m["scores"]] + [6])
    for k, v in sorted(m["scores"].items()):
        print(f"    {k:{w}} {v}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
