"""Eval harness — promote, judge, aggregate, report.

Run:
    python runner.py --config config.example.yaml                  # real Claude
    python runner.py --config config.example.yaml --use-fake-judge # no API
"""

from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import yaml

from judges import ItemScore, build_judge


logger = logging.getLogger("eval-harness")


# ---------------------------------------------------------------------------
# Domain types — kept narrow for clarity. Adapt as needed.


@dataclass
class RunCandidate:
    """One candidate run. `primary_score` is the cheap metric used for triage."""

    run_id: str
    stratum: str
    primary_score: float


@dataclass
class StratumPromotion:
    """Per-stratum promotion summary, for traceability in the report."""

    name: str
    leader_score: float
    floor: float
    promoted: List[str] = field(default_factory=list)
    rejected: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class FinalistAggregate:
    """Per-finalist aggregate after judging."""

    run_id: str
    stratum: str
    primary_judge: str
    cross_judge: Optional[str]
    n_items: int
    primary_mean_per_dim: Dict[str, float] = field(default_factory=dict)
    cross_mean_per_dim: Dict[str, float] = field(default_factory=dict)
    primary_overall_mean: float = 0.0
    cross_overall_mean: Optional[float] = None
    agreement_rate: Optional[float] = None
    contested: bool = False
    total_cost_usd: float = 0.0
    errors: int = 0


# ---------------------------------------------------------------------------
# Step 1 — Promote


def promote_finalists(
    candidates: Iterable[RunCandidate],
    *,
    per_stratum_top_k: int,
    floor_fraction: float,
    overall_cap: int,
    carte_blanche: Iterable[str] = (),
) -> Tuple[List[RunCandidate], List[StratumPromotion]]:
    """Top-K per stratum, drop below floor, cap globally, carte-blanche overrides.

    The carte-blanche override exists because the cheap metric is the very
    thing the LLM judging is supposed to bypass — excluding a candidate on
    a metric you don't trust is the bias you're trying to fix.
    """
    carte_blanche_terms = tuple(s for s in carte_blanche if s)
    by_stratum: Dict[str, List[RunCandidate]] = {}
    for c in candidates:
        by_stratum.setdefault(c.stratum, []).append(c)

    promoted: List[RunCandidate] = []
    summary: List[StratumPromotion] = []
    for name, runs in by_stratum.items():
        runs_sorted = sorted(runs, key=lambda r: r.primary_score, reverse=True)
        if not runs_sorted:
            continue
        leader = runs_sorted[0].primary_score
        floor = floor_fraction * leader
        promo = StratumPromotion(name=name, leader_score=leader, floor=floor)

        for run in runs_sorted[:per_stratum_top_k]:
            if run.primary_score >= floor:
                promoted.append(run)
                promo.promoted.append(run.run_id)
            else:
                promo.rejected.append(
                    {
                        "run_id": run.run_id,
                        "reason": f"below_floor ({run.primary_score:.4f} < {floor:.4f})",
                        "primary_score": run.primary_score,
                    }
                )
        for rank, run in enumerate(runs_sorted[per_stratum_top_k:], start=per_stratum_top_k + 1):
            promo.rejected.append(
                {
                    "run_id": run.run_id,
                    "reason": f"not_top_{per_stratum_top_k} (rank={rank})",
                    "primary_score": run.primary_score,
                }
            )
        summary.append(promo)

    if len(promoted) > overall_cap:
        promoted = sorted(promoted, key=lambda r: r.primary_score, reverse=True)[:overall_cap]
        kept = {r.run_id for r in promoted}
        for s in summary:
            s.promoted = [rid for rid in s.promoted if rid in kept]

    if carte_blanche_terms:
        promoted_ids = {r.run_id for r in promoted}
        all_candidates = [c for cs in by_stratum.values() for c in cs]
        for cand in all_candidates:
            if cand.run_id in promoted_ids:
                continue
            if any(term in cand.run_id for term in carte_blanche_terms):
                promoted.append(cand)
                promoted_ids.add(cand.run_id)
                for s in summary:
                    if s.name == cand.stratum:
                        s.promoted.append(cand.run_id)
                        s.rejected = [r for r in s.rejected if r.get("run_id") != cand.run_id]
                        break

    return promoted, summary


# ---------------------------------------------------------------------------
# Step 2 — Judge (with cost cap, partial-result preservation)


def judge_finalist(
    *,
    finalist: RunCandidate,
    judge,
    items: List[Dict[str, Any]],
    dimensions: List[str],
    cost_budget_remaining: Optional[float],
) -> Tuple[List[ItemScore], float, int]:
    """Score every item of `finalist` with `judge`.

    Aborts mid-finalist if cost cap drops to <= 0. Caller's responsibility
    to track cumulative spend across finalists.
    """
    scores: List[ItemScore] = []
    total_cost = 0.0
    errors = 0
    remaining = cost_budget_remaining

    for item in items:
        score = judge.score(
            run_id=finalist.run_id,
            item_id=str(item.get("item_id", f"item_{len(scores)}")),
            item_content=str(item.get("content", "")),
            dimensions=dimensions,
        )
        scores.append(score)
        total_cost += score.total_cost_usd
        errors += len(score.errors)
        if remaining is not None:
            remaining -= score.total_cost_usd
            if remaining <= 0:
                logger.warning(
                    "Cost budget exhausted mid-finalist %s after %d items",
                    finalist.run_id,
                    len(scores),
                )
                break
    return scores, total_cost, errors


# ---------------------------------------------------------------------------
# Step 3 — Aggregate


def aggregate_finalist(
    *,
    finalist: RunCandidate,
    primary_judge_name: str,
    primary_scores: List[ItemScore],
    cross_judge_name: Optional[str] = None,
    cross_scores: Optional[List[ItemScore]] = None,
    contested_threshold: float = 0.5,
    agreement_tolerance: int = 1,
    dimensions: List[str] = (),
) -> FinalistAggregate:
    """Reduce per-item scores to per-dimension means + contested flag."""

    def _per_dim_mean(scores: List[ItemScore], dim: str) -> Optional[float]:
        vals = [s.per_dimension[dim] for s in scores if dim in s.per_dimension]
        return (sum(vals) / len(vals)) if vals else None

    primary_per_dim_raw = {d: _per_dim_mean(primary_scores, d) for d in dimensions}
    primary_per_dim = {d: v for d, v in primary_per_dim_raw.items() if v is not None}
    primary_overall = (
        sum(primary_per_dim.values()) / len(primary_per_dim) if primary_per_dim else 0.0
    )
    total_cost = sum(s.total_cost_usd for s in primary_scores)
    n_err = sum(len(s.errors) for s in primary_scores)

    cross_per_dim: Dict[str, float] = {}
    cross_overall: Optional[float] = None
    agree_rate: Optional[float] = None
    contested = False
    if cross_scores is not None:
        cross_per_dim_raw = {d: _per_dim_mean(cross_scores, d) for d in dimensions}
        cross_per_dim = {d: v for d, v in cross_per_dim_raw.items() if v is not None}
        if cross_per_dim:
            cross_overall = sum(cross_per_dim.values()) / len(cross_per_dim)
            contested = abs(primary_overall - cross_overall) > contested_threshold
        agree_rate = _pairwise_agreement_rate(
            primary_scores, cross_scores, tolerance=agreement_tolerance
        )
        total_cost += sum(s.total_cost_usd for s in cross_scores)
        n_err += sum(len(s.errors) for s in cross_scores)

    return FinalistAggregate(
        run_id=finalist.run_id,
        stratum=finalist.stratum,
        primary_judge=primary_judge_name,
        cross_judge=cross_judge_name,
        n_items=len(primary_scores),
        primary_mean_per_dim=primary_per_dim,
        cross_mean_per_dim=cross_per_dim,
        primary_overall_mean=primary_overall,
        cross_overall_mean=cross_overall,
        agreement_rate=agree_rate,
        contested=contested,
        total_cost_usd=total_cost,
        errors=n_err,
    )


def _pairwise_agreement_rate(
    primary: List[ItemScore],
    cross: List[ItemScore],
    *,
    tolerance: int,
) -> Optional[float]:
    """Per-(item, dim) agreement (exact-or-adjacent within tolerance)."""
    cross_by_item = {s.item_id: s for s in cross}
    total = 0
    agree = 0
    for ps in primary:
        cs = cross_by_item.get(ps.item_id)
        if cs is None:
            continue
        for dim, p_score in ps.per_dimension.items():
            c_score = cs.per_dimension.get(dim)
            if c_score is None:
                continue
            total += 1
            if abs(p_score - c_score) <= tolerance:
                agree += 1
    return (agree / total) if total else None


# ---------------------------------------------------------------------------
# Step 4 — Report


def write_report(
    *,
    output_dir: Path,
    finalists: List[FinalistAggregate],
    promotion_summary: List[StratumPromotion],
    config: Dict[str, Any],
) -> None:
    """Write finalists.jsonl + report.json + report.md."""
    output_dir.mkdir(parents=True, exist_ok=True)

    with (output_dir / "finalists.jsonl").open("w", encoding="utf-8") as fh:
        for fin in finalists:
            fh.write(json.dumps(asdict(fin), default=str) + "\n")

    report = {
        "config": config,
        "git_sha": _git_sha(),
        "promotion": [asdict(p) for p in promotion_summary],
        "finalists": [asdict(f) for f in finalists],
    }
    (output_dir / "report.json").write_text(json.dumps(report, indent=2, default=str))

    md = _markdown_report(finalists, promotion_summary)
    (output_dir / "report.md").write_text(md)

    logger.info("Report written to %s", output_dir)


def _markdown_report(
    finalists: List[FinalistAggregate],
    promotion_summary: List[StratumPromotion],
) -> str:
    lines = ["# Eval report", ""]
    for s in promotion_summary:
        lines.append(f"## Stratum: {s.name}")
        lines.append(f"- Leader score: {s.leader_score:.4f} (floor: {s.floor:.4f})")
        lines.append(f"- Promoted: {', '.join(s.promoted) or '(none)'}")
        if s.rejected:
            lines.append("- Rejected:")
            for r in s.rejected:
                lines.append(f"  - {r['run_id']} — {r['reason']}")
        lines.append("")

    lines.append("## Finalists (by primary overall mean)")
    lines.append("")
    lines.append("| Run | Stratum | Primary | Cross | Agreement | Contested | Cost | Errors |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for f in sorted(finalists, key=lambda x: -x.primary_overall_mean):
        cross = f"{f.cross_overall_mean:.2f}" if f.cross_overall_mean is not None else "-"
        agree = f"{f.agreement_rate:.0%}" if f.agreement_rate is not None else "-"
        contested = "⚠" if f.contested else ""
        lines.append(
            f"| {f.run_id} | {f.stratum} | {f.primary_overall_mean:.2f} | "
            f"{cross} | {agree} | {contested} | ${f.total_cost_usd:.4f} | {f.errors} |"
        )
    return "\n".join(lines) + "\n"


def _git_sha() -> Optional[str]:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True
        ).strip()
    except (subprocess.SubprocessError, FileNotFoundError):
        return None


# ---------------------------------------------------------------------------
# main


def _synth_items(run_id: str, n: int = 5) -> List[Dict[str, Any]]:
    """Demo items for the FakeJudge run. Replace with your data loader."""
    return [
        {"item_id": f"{run_id}-{i}", "content": f"Synthetic item {i} for {run_id}"}
        for i in range(n)
    ]


def main(argv: List[str]) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--use-fake-judge", action="store_true")
    args = ap.parse_args(argv)

    cfg = yaml.safe_load(Path(args.config).read_text())

    candidates = [RunCandidate(**r) for r in cfg["runs"]]
    promoted, promo_summary = promote_finalists(
        candidates,
        per_stratum_top_k=cfg["promotion"]["per_stratum_top_k"],
        floor_fraction=cfg["promotion"]["floor_fraction"],
        overall_cap=cfg["promotion"]["overall_cap"],
        carte_blanche=cfg["promotion"].get("carte_blanche", []),
    )
    logger.info("Promoted %d finalists across %d strata", len(promoted), len(promo_summary))

    primary = build_judge(cfg["judging"]["primary_judge"], use_fake=args.use_fake_judge)
    cross = build_judge(cfg["judging"].get("cross_judge"), use_fake=args.use_fake_judge)
    dims = cfg["judging"]["dimensions"]
    cost_remaining = float(cfg["judging"]["cost_cap_usd"])
    max_items = int(cfg["judging"]["max_items_per_finalist"])

    aggregates: List[FinalistAggregate] = []
    for finalist in promoted:
        items = _synth_items(finalist.run_id, n=max_items)

        primary_scores, primary_cost, _ = judge_finalist(
            finalist=finalist,
            judge=primary,
            items=items,
            dimensions=dims,
            cost_budget_remaining=cost_remaining,
        )
        cost_remaining -= primary_cost

        cross_scores = None
        if cross is not None and cost_remaining > 0:
            cross_scores, cross_cost, _ = judge_finalist(
                finalist=finalist,
                judge=cross,
                items=items,
                dimensions=dims,
                cost_budget_remaining=cost_remaining,
            )
            cost_remaining -= cross_cost

        aggregates.append(
            aggregate_finalist(
                finalist=finalist,
                primary_judge_name=primary.name,
                primary_scores=primary_scores,
                cross_judge_name=cross.name if cross else None,
                cross_scores=cross_scores,
                contested_threshold=cfg["aggregation"]["contested_threshold"],
                agreement_tolerance=cfg["aggregation"]["agreement_tolerance"],
                dimensions=dims,
            )
        )
        if cost_remaining <= 0:
            logger.warning("Global cost cap hit after %d/%d finalists", len(aggregates), len(promoted))
            break

    output_dir = Path(cfg["output_root"]) / cfg["tag"]
    write_report(
        output_dir=output_dir,
        finalists=aggregates,
        promotion_summary=promo_summary,
        config=cfg,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
