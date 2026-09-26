#!/usr/bin/env python3
"""Download a slice of CNN/DailyMail into the harness, sources and GOLD references.

    python examples/summarization-cnn-dailymail/fetch.py --n 50

STDLIB ONLY. It reads the HuggingFace datasets-server rows API over HTTPS rather than
using the `datasets` library, so getting the data costs no pyarrow, no pandas and no
2GB of transitive dependencies. For a 50-row eval slice that is the whole job.

WHY THIS DATASET
  abisee/cnn_dailymail is apache-2.0 — the only clearly-licensed option among the usual
  summarisation benchmarks (XSum's licence is listed "unknown") — and it is the most-cited
  summarisation baseline, so published ROUGE numbers exist to sanity-check ours against.
  That is the point of using a standard set instead of inventing data: somebody else's
  baseline is a check on our instrument.

WHY THE REFERENCE IS GOLD
  `highlights` are the bullet summaries written by the journalists who filed the article.
  Human-authored, so `references/gold/`. Every run scored against them says tier=gold,
  which is a stronger claim than this harness's bundled demo can make — that one authors
  a silver reference with a model, because its placeholder items have no human summary to
  use. Here there is one.

NOTHING IS COMMITTED
  The fetched slice is gitignored. Redistributing a third-party corpus is a licence
  question nobody should inherit by cloning a repo, so each example downloads its own.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

# parents[1] is examples/, so this resolves to examples/eval-harness — the harness this
# example feeds. parents[2] would be the repo root and silently create a second data tree
# one level up, which is exactly what it did the first time.
ROOT = Path(__file__).resolve().parents[1] / "eval-harness"
ROWS_API = "https://datasets-server.huggingface.co/rows"
DATASET = "abisee/cnn_dailymail"
CONFIG = "1.0.0"

#: The API caps a single request; ask in pages rather than assuming one call is enough.
PAGE = 100


def fetch_rows(n: int, split: str) -> list[dict]:
    """`n` rows from the datasets-server, paged."""
    rows: list[dict] = []
    while len(rows) < n:
        want = min(PAGE, n - len(rows))
        query = urllib.parse.urlencode(
            {"dataset": DATASET, "config": CONFIG, "split": split,
             "offset": len(rows), "length": want}
        )
        try:
            with urllib.request.urlopen(f"{ROWS_API}?{query}", timeout=60) as resp:
                payload = json.loads(resp.read())
        except Exception as exc:  # noqa: BLE001 - one message, not a traceback
            sys.exit(
                f"could not reach the datasets-server: {type(exc).__name__}: {exc}\n"
                "  it is an HTTPS API; check connectivity, then retry."
            )
        page = payload.get("rows") or []
        if not page:
            break  # the split ran out before n — say so below rather than loop forever
        rows.extend(r["row"] for r in page)
    return rows[:n]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--n", type=int, default=50, help="items to fetch (default: 50)")
    ap.add_argument("--split", default="test", help="dataset split (default: test)")
    ap.add_argument("--dataset-id", default=None, help="harness dataset_id (default: cnn_dailymail_<n>)")
    ap.add_argument("--force", action="store_true", help="overwrite an existing slice")
    args = ap.parse_args()

    dataset_id = args.dataset_id or f"cnn_dailymail_{args.n}"
    sources = ROOT / "data" / "sources" / dataset_id
    golds = ROOT / "data" / "references" / "gold" / dataset_id

    if sources.exists() and not args.force:
        print(f"{sources} already exists — pass --force to refetch")
        return 0

    rows = fetch_rows(args.n, args.split)
    if len(rows) < args.n:
        print(f"  NOTE: asked for {args.n}, the split gave {len(rows)}")
    if not rows:
        sys.exit("no rows returned — nothing written")

    sources.mkdir(parents=True, exist_ok=True)
    golds.mkdir(parents=True, exist_ok=True)
    for row in rows:
        # The dataset's own id, so an item is traceable back to the published row rather
        # than to our enumeration order.
        item = str(row["id"])
        (sources / f"{item}.txt").write_text(row["article"], encoding="utf-8")
        (golds / f"{item}.txt").write_text(row["highlights"], encoding="utf-8")

    article_words = sum(len(r["article"].split()) for r in rows) / len(rows)
    summary_words = sum(len(r["highlights"].split()) for r in rows) / len(rows)
    print(f"{len(rows)} item(s) written")
    print(f"  articles   {sources}      (mean {article_words:.0f} words)")
    print(f"  gold refs  {golds}  (mean {summary_words:.0f} words)")
    print(f"\n  Long inputs are the point: a {article_words:.0f}-word article is where a local")
    print("  model's context limit and an LLM's price per token both start to bite.")
    print("\nNext:")
    print(f"  make dataset-create DATASET_ID={dataset_id} ARGS='--source-dir data/sources/{dataset_id}'")
    print(f"  make dataset-materialize DATASET_ID={dataset_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
