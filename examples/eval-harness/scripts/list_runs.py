#!/usr/bin/env python3
"""List runs (or baselines) with the three things that make a number mean something.

    python scripts/list_runs.py
    python scripts/list_runs.py --baselines
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import BASELINES, RUNS, read_json  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--baselines", action="store_true")
    args = ap.parse_args()

    if args.baselines:
        files = sorted(BASELINES.glob("*.json"))
        if not files:
            print("no baselines yet — promote a run:  make promote RUN=<id> REASON=\"...\"")
            return 0
        for f in files:
            b = read_json(f)
            print(f"{b['baseline_id']}")
            print(f"    dataset  {b['dataset_id']}")
            print(f"    from     {b['promoted_from']}   build={b['build'].get('ref', '?')[:12]}")
            print(f"    why      {b.get('reason', '(none recorded)')}")
            print("    scores   " + "  ".join(f"{k}={v}" for k, v in sorted(b["scores"].items())))
        return 0

    dirs = sorted(p for p in RUNS.iterdir() if (p / "metrics.json").is_file()) if RUNS.is_dir() else []
    if not dirs:
        print("no runs yet — try:  make demo")
        return 0
    print(f"{'run_id':44} {'dataset_id':18} {'build':14} scores")
    for d in dirs:
        m = read_json(d / "metrics.json")
        scores = "  ".join(f"{k}={v}" for k, v in sorted(m["scores"].items()))
        dirty = "*" if m["build"].get("dirty") else " "
        print(f"{m['run_id']:44} {m['dataset_id']:18} {m['build'].get('ref','?')[:12]}{dirty} {scores}")
    print("\n  * = produced by a dirty tree; its build ref does not describe what ran")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
