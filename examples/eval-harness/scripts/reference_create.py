#!/usr/bin/env python3
"""Establish ground truth for a dataset, so later runs have something to be scored against.

THE CHICKEN AND EGG: you cannot measure quality without something to measure
against, and most projects have no ground truth for the thing they actually
ship. The usual answers:

  gold    a human wrote it. Expensive, slow, and the only thing you can
          honestly call correct.
  silver  a model you trust wrote it. Cheap, plentiful, and NOT the same
          thing — it encodes that model's opinion, including its mistakes.

This script produces SILVER by default and says so in the manifest. That is a
legitimate starting point: a consistent reference lets you rank arms against
each other today, and you can replace items with human-authored gold later
without changing anything downstream.

What it must never do is let you forget which you have. `make validate` reads
the manifest, and every run scored against silver carries that fact.

    make reference-create DATASET_ID=my_v1 CONFIG=data/configs/golden.yaml
    make reference-create DATASET_ID=my_v1 CONFIG=... TIER=gold   # human-reviewed

Cost: one call per item, against whatever the config names. Start with a small
dataset — a 10-item golden pass is enough to rank four arms.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import MATERIALIZED, REFERENCES, die, load_dataset, now, write_json  # noqa: E402

try:
    import yaml
except ImportError:  # pragma: no cover
    die("pyyaml is required — pip install -r requirements.txt")

from adapter import call_system  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dataset-id", required=True)
    ap.add_argument("--config", required=True, type=Path, help="which model authors the reference")
    ap.add_argument(
        "--tier",
        choices=["gold", "silver"],
        default="silver",
        help="gold = human-authored or human-reviewed; silver = model-generated (default)",
    )
    ap.add_argument("--limit", type=int, help="only the first N items — keep the first pass cheap")
    ap.add_argument("--force", action="store_true", help="overwrite existing references")
    args = ap.parse_args()

    ds = load_dataset(args.dataset_id)
    cfg = yaml.safe_load(args.config.read_text(encoding="utf-8")) or {}
    params = dict(cfg.get("params") or {})
    mat = MATERIALIZED / args.dataset_id
    if not mat.is_dir():
        die(f"materialize first:  make dataset-materialize DATASET_ID={args.dataset_id}")

    out_dir = REFERENCES / args.tier / args.dataset_id
    if out_dir.exists() and not args.force:
        die(
            f"{out_dir} already exists.\n"
            "  References are frozen — every score already reported was measured\n"
            "  against these. Use a new dataset version, or --force if nothing cites them."
        )
    # Author into a sibling .partial/ and rename at the end, so a run that dies midway leaves
    # NOTHING. It used to mkdir here and write per item: a crash on item 1 — a missing client
    # library, a bad key — left an empty frozen directory, and the (correct) refusal above then
    # blocked the retry. The first thing a new user hit was a freeze guard protecting nothing.
    final_dir = out_dir
    out_dir = out_dir.with_name(out_dir.name + ".partial")
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    items = ds["items"][: args.limit] if args.limit else ds["items"]
    total_cost, n_priced = 0.0, 0
    print(f"authoring {len(items)} {args.tier} reference(s) with {cfg.get('config_id', args.config.name)}")

    for i, item in enumerate(items, 1):
        rel = item.get("source_path") or item["item_id"]
        src = mat / rel
        if not src.is_file():
            die(f"missing materialized item: {src}")
        res = call_system(src.read_text(encoding="utf-8", errors="replace"), params)
        (out_dir / f"{item['item_id']}.txt").write_text(res.output, encoding="utf-8")
        if res.cost_usd is not None:
            total_cost += res.cost_usd
            n_priced += 1
        print(f"  [{i}/{len(items)}] {item['item_id']}  {len(res.output.split())} words"
              + (f"  ${res.cost_usd:.5f}" if res.cost_usd is not None else ""))

    write_json(
        out_dir / "manifest.json",
        {
            "dataset_id": args.dataset_id,
            "tier": args.tier,
            "authored_by": cfg.get("config_id", str(args.config)),
            "model": params.get("model", params.get("provider", "unknown")),
            "created_at": now(),
            "n_items": len(items),
            "cost_usd": round(total_cost, 6) if n_priced else None,
            "caveat": (
                "GOLD: human-authored or human-reviewed."
                if args.tier == "gold"
                else "SILVER: model-generated. It encodes that model's opinion, including "
                "its mistakes. Good enough to RANK arms against each other; not the same "
                "thing as correct. Say so wherever a number scored against it is published."
            ),
        },
    )
    # Only now is it a reference set. Rename is atomic on the same filesystem, so the directory
    # either does not exist or is complete — never half-authored.
    if final_dir.exists():
        shutil.rmtree(final_dir)
    out_dir.rename(final_dir)
    out_dir = final_dir

    print(f"\n{out_dir}  ({len(items)} item(s), tier={args.tier}"
          + (f", ${total_cost:.4f}" if n_priced else "") + ")")
    print("Runs against this dataset will now be scored against it automatically.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
