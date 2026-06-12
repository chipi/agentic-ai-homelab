"""Bake-off runner — provider × task × item, score, report.

Run via the Makefile:
    make bakeoff                  # use providers whose env vars are set
    make bakeoff-fake             # FakeProvider only, no API calls
    make bakeoff TASK=commit-message
    make bakeoff PROVIDERS=claude,deepseek,kimi

Output:
    out/<task>_<timestamp>/
        results.jsonl   — per-(provider, item) raw response + score
        report.json     — structured aggregate
        report.md       — human-readable summary table

The Markdown report is what you'll look at to pick a provider.
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from providers import (
    ClaudeProvider,
    Provider,
    Reply,
    discover_providers,
    FakeProvider,
)
from score import Score, score_item
from tasks import Item, TASKS, load_task


# ---------------------------------------------------------------------------
# Judge wiring for commit-message scoring.


def _build_judge():
    """Construct the LLM judge used by score.py for commit-message scoring.

    Anthropic is the default judge if ANTHROPIC_API_KEY is set. Falls back
    to a stub judge that returns a fixed "acceptable" verdict — so the
    bake-off still runs without an Anthropic key (the resulting commit-
    message numbers will just be uninformative).
    """
    if os.environ.get("ANTHROPIC_API_KEY"):
        judge = ClaudeProvider()

        def _call(*, prompt: str, system: str):
            r = judge.generate(prompt=prompt, system=system)
            return r.text, r.cost_usd

        return _call

    def _stub(*, prompt: str, system: str):
        stub = json.dumps(
            {
                "format_ok": True,
                "accuracy": 3,
                "specificity": 3,
                "verdict": "acceptable",
                "rationale": "stub judge — set ANTHROPIC_API_KEY for real scoring",
            }
        )
        return stub, 0.0

    return _stub


# ---------------------------------------------------------------------------
# Per-(provider, item) execution


def run_one(*, provider: Provider, item: Item, system_prompt: str) -> Reply:
    return provider.generate(prompt=item.user_prompt, system=system_prompt)


# ---------------------------------------------------------------------------
# Aggregation


def aggregate(rows: List[Dict]) -> Dict[str, Dict]:
    """Group rows by provider; compute mean score, total cost, mean latency."""
    by_provider: Dict[str, List[Dict]] = {}
    for row in rows:
        by_provider.setdefault(row["provider_label"], []).append(row)

    summary: Dict[str, Dict] = {}
    for label, rows_for_p in by_provider.items():
        scores = [r["score"] for r in rows_for_p if r["score"] is not None]
        latencies = [r["latency_s"] for r in rows_for_p]
        costs = [r["cost_usd"] for r in rows_for_p]
        errors = sum(1 for r in rows_for_p if r["error"])
        summary[label] = {
            "org": rows_for_p[0]["provider_org"],
            "flag": rows_for_p[0]["provider_flag"],
            "n_items": len(rows_for_p),
            "n_errors": errors,
            "mean_score": statistics.mean(scores) if scores else 0.0,
            "total_cost_usd": sum(costs),
            "mean_latency_s": statistics.mean(latencies) if latencies else 0.0,
        }
    return summary


def write_report(*, output_dir: Path, task_name: str, rows: List[Dict], summary: Dict) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)

    with (output_dir / "results.jsonl").open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, default=str) + "\n")

    (output_dir / "report.json").write_text(
        json.dumps({"task": task_name, "providers": summary}, indent=2, default=str)
    )

    md = _markdown_report(task_name=task_name, summary=summary, rows=rows)
    (output_dir / "report.md").write_text(md)

    print(f"\n  → report written to {output_dir}")


def _markdown_report(*, task_name: str, summary: Dict, rows: List[Dict]) -> str:
    lines = [f"# Provider bake-off — `{task_name}`", ""]

    ranked = sorted(summary.items(), key=lambda kv: -kv[1]["mean_score"])
    lines.append("## Summary (ranked by mean score)")
    lines.append("")
    lines.append("| Provider | Org | Score | Cost (total) | Mean latency | Errors |")
    lines.append("|---|---|---|---|---|---|")
    for label, s in ranked:
        lines.append(
            f"| `{label}` | {s['org']} | **{s['mean_score']:.2f}** | "
            f"${s['total_cost_usd']:.4f} | {s['mean_latency_s']:.2f}s | {s['n_errors']} |"
        )
    lines.append("")

    by_item: Dict[str, Dict[str, float]] = {}
    for row in rows:
        by_item.setdefault(row["item_id"], {})[row["provider_label"]] = row["score"]

    lines.append("## Per-item breakdown")
    lines.append("")
    provider_order = [label for label, _ in ranked]
    header = "| Item | " + " | ".join(f"`{p}`" for p in provider_order) + " |"
    align = "|---|" + "|".join(["---"] * len(provider_order)) + "|"
    lines.append(header)
    lines.append(align)
    for item_id in sorted(by_item.keys()):
        row_scores = by_item[item_id]
        cells = []
        for p in provider_order:
            v = row_scores.get(p)
            cells.append(f"{v:.2f}" if v is not None else "—")
        lines.append(f"| `{item_id}` | " + " | ".join(cells) + " |")
    lines.append("")

    lines.append("## Notes")
    lines.append("")
    lines.append("- Score is the per-item mean (0-1).")
    lines.append("- Cost is illustrative — pricing constants live in `providers.py`.")
    lines.append("- Latency includes network round-trip; not directly comparable across regions.")
    lines.append("- Errors are exceptions / parse failures — they pull down the mean.")
    lines.append("")

    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# main


def main(argv: List[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--task", default="json-extraction", choices=list(TASKS))
    ap.add_argument("--providers", help="Comma list to whitelist; default = all available")
    ap.add_argument("--use-fake", action="store_true", help="FakeProvider only — no API calls")
    ap.add_argument("--out", default="out")
    args = ap.parse_args(argv)

    task_spec = TASKS[args.task]
    data_dir = Path(__file__).parent / "data"
    items = load_task(args.task, data_dir)
    print(f"task: {args.task}   items: {len(items)}")

    providers = discover_providers(use_fake=args.use_fake)
    if args.providers:
        wanted = {p.strip() for p in args.providers.split(",") if p.strip()}
        providers = [p for p in providers if p.label in wanted or _short(p) in wanted]
        if not providers:
            print(f"  no provider matched --providers={args.providers}; falling back to fake")
            providers = [FakeProvider()]

    print(f"providers: {len(providers)}")
    for p in providers:
        print(f"  - {p.org}  ({p.label})")
    print()

    judge_callable = _build_judge()
    rows: List[Dict] = []

    for provider in providers:
        print(f"running {provider.org} ...", end="", flush=True)
        for item in items:
            reply = run_one(
                provider=provider, item=item, system_prompt=task_spec.system_prompt
            )
            if reply.error:
                row = {
                    "item_id": item.id,
                    "provider_label": provider.label,
                    "provider_org": provider.org,
                    "provider_flag": provider.flag,
                    "score": None,
                    "primary_kind": task_spec.primary_scorer,
                    "secondary_score": None,
                    "cost_usd": reply.cost_usd,
                    "latency_s": reply.latency_s,
                    "error": reply.error,
                    "response_text": "",
                }
                rows.append(row)
                continue

            score = score_item(
                task_name=args.task,
                response_text=reply.text,
                gold=item.gold,
                judge_callable=judge_callable,
            )
            row = {
                "item_id": item.id,
                "provider_label": provider.label,
                "provider_org": provider.org,
                "provider_flag": provider.flag,
                "score": score.primary_score,
                "primary_kind": score.primary_kind,
                "secondary_score": score.secondary_score,
                "cost_usd": reply.cost_usd,
                "latency_s": reply.latency_s,
                "error": None,
                "response_text": reply.text,
                "score_breakdown": score.breakdown,
                "score_note": score.note,
            }
            rows.append(row)
        print(" done")

    summary = aggregate(rows)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%SZ")
    output_dir = Path(args.out) / f"{args.task}_{timestamp}"
    write_report(output_dir=output_dir, task_name=args.task, rows=rows, summary=summary)

    print("\n  Top 3:")
    ranked = sorted(summary.items(), key=lambda kv: -kv[1]["mean_score"])[:3]
    for label, s in ranked:
        print(f"    {s['org']:35s}  score={s['mean_score']:.2f}  cost=${s['total_cost_usd']:.4f}")

    return 0


def _short(p: Provider) -> str:
    return p.label.split("/")[-1].split("-")[0].lower()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
