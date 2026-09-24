#!/usr/bin/env python3
"""Freeze a selection of source items into a dataset.

A dataset is not "the data". It is a NAMED, FROZEN selection plus the hash of
every item in it — which is what makes two runs comparable. The `dataset_id` is
the comparison contract:

    A metric compared across two different dataset_ids is not a comparison.
    It is a coincidence.

Sources are immutable. If an item changes, that is a NEW dataset (`_v2`), never
an edit in place — every number already published was measured on the old bytes.

    python scripts/dataset_create.py --dataset-id smoke_v1
    python scripts/dataset_create.py --dataset-id smoke_v1 --limit 3 --tag quick
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import DATASETS, SOURCES, die, now, sha256, write_json  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dataset-id", required=True, help="lowercase_with_underscores")
    ap.add_argument("--source-dir", type=Path, default=SOURCES)
    ap.add_argument("--glob", default="*", help="which files under --source-dir are items")
    ap.add_argument("--limit", type=int, help="take only the first N (sorted) — a smoke cut")
    ap.add_argument("--tag", action="append", default=[], help="tag every item (repeatable)")
    ap.add_argument("--description", default="")
    ap.add_argument(
        "--include-docs",
        action="store_true",
        help="also treat README files as items (they are skipped by default)",
    )
    ap.add_argument("--force", action="store_true", help="overwrite an existing dataset")
    args = ap.parse_args()

    out = DATASETS / f"{args.dataset_id}.json"
    if out.exists() and not args.force:
        die(
            f"{out} already exists.\n"
            "  A dataset is FROZEN — runs cite it by id and were measured on these bytes.\n"
            "  Make a new version (e.g. _v2) instead, or pass --force if nothing cites it yet."
        )

    if not args.source_dir.is_dir():
        die(f"no source dir at {args.source_dir} — put your raw inputs there first")

    # Skip the directory's own documentation and dotfiles. Every data dir here
    # ships a README explaining what belongs in it, and the first cold drop-in
    # of this skeleton froze `sources/README.md` as a data item — "1 item, all
    # hashes verified" — which is exactly the kind of quiet wrong answer this
    # tooling exists to prevent.
    def is_item(p: Path) -> bool:
        if not p.is_file() or p.name.startswith("."):
            return False
        return args.include_docs or p.name.lower() not in {"readme.md", "readme.txt", "readme"}

    files = sorted(p for p in args.source_dir.rglob(args.glob) if is_item(p))
    if args.limit:
        files = files[: args.limit]
    if not files:
        die(
            f"no items matched {args.glob!r} under {args.source_dir}\n"
            "  Put your inputs in that directory first. READMEs are skipped by\n"
            "  design — pass --include-docs if documentation really is your data."
        )

    items = [
        {
            "item_id": p.relative_to(args.source_dir).as_posix().rsplit(".", 1)[0],
            "source_path": p.relative_to(args.source_dir).as_posix(),
            "source_sha256": sha256(p),
            **({"tags": list(args.tag)} if args.tag else {}),
        }
        for p in files
    ]

    write_json(
        out,
        {
            "dataset_id": args.dataset_id,
            "version": "1.0",
            "description": args.description or f"{len(items)} item(s) from {args.source_dir.name}/",
            "created_at": now(),
            "source_dir": args.source_dir.as_posix(),
            "items": items,
        },
    )
    print(f"{out.relative_to(DATASETS.parents[1])}  ({len(items)} item(s))")
    print("Next: make dataset-materialize DATASET_ID=" + args.dataset_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
