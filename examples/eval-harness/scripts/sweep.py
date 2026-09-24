#!/usr/bin/env python3
"""Run several arms over one dataset, then rank them.

Comparing four models should be one command, not four invocations and six
pairwise comparisons. This runs each config in turn, keeps going when one arm
fails — a provider outage on arm 3 should not throw away arms 1 and 2 — and
ends with the leaderboard.

    python scripts/sweep.py --configs data/configs/arm_*.yaml --repeat 2
    python scripts/sweep.py --configs data/configs/arm_*.yaml --dry-run

Always dry-run first. It costs nothing and tells you what the sweep will.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import List

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import ROOT, die  # noqa: E402

try:
    import yaml
except ImportError:  # pragma: no cover
    die("pyyaml is required — pip install -r requirements.txt")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--configs", nargs="+", required=True, type=Path)
    ap.add_argument("--repeat", type=int, default=1)
    ap.add_argument("--dry-run", action="store_true", help="cost it without calling anything")
    ap.add_argument("--sort", help="leaderboard metric")
    args = ap.parse_args()

    configs = [c for c in args.configs if c.is_file()]
    if not configs:
        die(f"no config files matched: {' '.join(str(c) for c in args.configs)}")

    # Every arm must sit on the SAME dataset, or the leaderboard is a list of
    # unrelated numbers. Refuse up front rather than producing one.
    datasets = {}
    for c in configs:
        cfg = yaml.safe_load(c.read_text(encoding="utf-8")) or {}
        datasets.setdefault(cfg.get("dataset_id"), []).append(c.name)
    if len(datasets) != 1:
        lines = "\n".join(f"    {d or '(missing)'}: {', '.join(n)}" for d, n in datasets.items())
        die("REFUSED — the arms do not share one dataset_id:\n" + lines +
            "\n  A leaderboard across datasets ranks nothing. Re-run the odd ones out.")
    dataset_id = next(iter(datasets))

    py = sys.executable
    print(f"sweep: {len(configs)} arm(s) on {dataset_id}, repeat={args.repeat}\n")

    failed: List[str] = []
    for i, c in enumerate(configs, 1):
        print(f"── [{i}/{len(configs)}] {c.name} " + "─" * max(0, 50 - len(c.name)))
        cmd = [py, str(ROOT / "scripts/experiment_run.py"), "--config", str(c),
               "--repeat", str(args.repeat)]
        if args.dry_run:
            cmd.append("--dry-run")
        r = subprocess.run(cmd, cwd=ROOT)
        if r.returncode != 0:
            # Keep going: one provider's outage should not discard the arms
            # that already succeeded and were paid for.
            failed.append(c.name)
            print(f"   ARM FAILED (exit {r.returncode}) — continuing with the rest")
        print()

    if failed:
        print(f"  {len(failed)} arm(s) failed: {', '.join(failed)}")
        print("  The rest still ran; their results are on the leaderboard below.\n")

    if args.dry_run:
        print("Dry run — nothing was called and nothing was spent.")
        return 0

    lb = [py, str(ROOT / "scripts/leaderboard.py"), "--dataset-id", dataset_id]
    if args.sort:
        lb += ["--sort", args.sort]
    subprocess.run(lb, cwd=ROOT)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
