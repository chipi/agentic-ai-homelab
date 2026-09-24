#!/usr/bin/env python3
"""Derive the run inputs for a dataset, verifying every item against its hash.

`materialized/` is DERIVED and regenerable from `sources/` + the dataset. If it
cannot be rebuilt, it does not belong there.

The hash check is the point. A dataset records what the bytes were when it was
frozen; if a source file has changed underneath it, every number measured on
that dataset is describing something that no longer exists. That is a hard
failure, not a warning.

    python scripts/materialize.py --dataset-id smoke_v1
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import (  # noqa: E402
    MATERIALIZED,
    die,
    load_dataset,
    now,
    sha256,
    write_json,
)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dataset-id", required=True)
    ap.add_argument("--force", action="store_true", help="rebuild even if it exists")
    args = ap.parse_args()

    ds = load_dataset(args.dataset_id)
    src_root = Path(ds.get("source_dir", "data/sources"))
    out = MATERIALIZED / args.dataset_id

    if out.exists() and not args.force:
        print(f"{out} exists — nothing to do (--force to rebuild)")
        return 0
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)

    drifted, missing = [], []
    for item in ds["items"]:
        rel = item.get("source_path") or item["item_id"]
        src = src_root / rel
        if not src.is_file():
            missing.append(rel)
            continue
        actual = sha256(src)
        if actual != item["source_sha256"]:
            drifted.append((rel, item["source_sha256"][:12], actual[:12]))
            continue
        dst = out / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)

    if missing or drifted:
        for rel in missing:
            print(f"  MISSING  {rel}")
        for rel, was, now_ in drifted:
            print(f"  CHANGED  {rel}  frozen={was} actual={now_}")
        die(
            f"{len(missing)} missing, {len(drifted)} changed since the dataset was frozen.\n"
            "  sources/ is immutable. If an input genuinely changed, that is a NEW\n"
            "  dataset (_v2) — every number already published was measured on the old bytes."
        )

    write_json(
        out / "meta.json",
        {
            "dataset_id": args.dataset_id,
            "materialized_at": now(),
            "n_items": len(ds["items"]),
            "verified": "every item matched its frozen sha256",
        },
    )
    print(f"{out}  ({len(ds['items'])} item(s), all hashes verified)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
