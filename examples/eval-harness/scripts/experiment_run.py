#!/usr/bin/env python3
"""Run one experiment config against one dataset; emit a run directory.

A run records THREE things, and is worthless without all of them:

    system under test   which build produced these numbers  (build.ref)
    instrument          which config was used               (config_id)
    data                what it was measured on             (dataset_id)

Drop any one and the number cannot be attributed to anything.

REPEAT is not a convenience. Before believing a delta between two arms you must
know the arm's own run-to-run spread — otherwise you are promoting noise. A real
example: one ASR model showed 0.058 WER spread on BYTE-IDENTICAL input, wider
than most deltas anyone was arguing about.

    python scripts/experiment_run.py --config data/configs/demo.yaml
    python scripts/experiment_run.py --config data/configs/demo.yaml --repeat 3

WIRING YOUR SYSTEM IN: edit `scripts/adapter.py`. Nothing in this file needs to
change — it times the call, records what it cost, scores the output against the
reference if one exists, and aggregates. That split is the point: the generic
half stays generic.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parent))
from adapter import call_system, score  # noqa: E402
from _common import (  # noqa: E402
    MATERIALIZED,
    REFERENCES,
    RUNS,
    build_info,
    die,
    load_dataset,
    now,
    read_json,
    write_json,
)

try:
    import yaml
except ImportError:  # pragma: no cover
    die("pyyaml is required — pip install -r requirements.txt")


def _reference_for(dataset_id: str) -> tuple[Path | None, str | None]:
    """Prefer gold over silver, and report which was used.

    A score against silver is not a score against gold, and a report that does
    not say which is unreadable six months later.
    """
    for tier in ("gold", "silver"):
        d = REFERENCES / tier / dataset_id
        if d.is_dir():
            return d, tier
    return None, None


def one_pass(ds: Dict[str, Any], cfg: Dict[str, Any], idx: int) -> Dict[str, Any]:
    mat = MATERIALIZED / ds["dataset_id"]
    if not mat.is_dir():
        die(
            f"{ds['dataset_id']} is not materialized.\n"
            f"  make dataset-materialize DATASET_ID={ds['dataset_id']}"
        )
    params = dict(cfg.get("params") or {})
    params.setdefault("seed", idx)
    ref_dir, ref_tier = _reference_for(ds["dataset_id"])

    predictions: List[Dict[str, Any]] = []
    outputs: Dict[str, str] = {}
    for item in ds["items"]:
        rel = item.get("source_path") or item["item_id"]
        src = mat / rel
        res = call_system(src.read_text(encoding="utf-8", errors="replace"), params)
        outputs[item["item_id"]] = res.output

        reference = None
        if ref_dir is not None:
            rf = ref_dir / f"{item['item_id']}.txt"
            if rf.is_file():
                reference = rf.read_text(encoding="utf-8", errors="replace")

        row: Dict[str, Any] = {"item_id": item["item_id"], **score(res.output, reference)}
        for field_name in ("latency_ms", "tokens_in", "tokens_out", "cost_usd"):
            v = getattr(res, field_name)
            if v is not None:
                row[field_name] = float(v)
        row.update({k: float(v) for k, v in res.extra.items()})
        predictions.append(row)

    keys = sorted({k for p in predictions for k in p if k != "item_id"})
    scores = {
        k: round(statistics.fmean([float(p[k]) for p in predictions if k in p]), 6) for k in keys
    }
    # Totals, not means, for the things you are billed for.
    for k in ("cost_usd", "tokens_in", "tokens_out"):
        vals = [float(p[k]) for p in predictions if k in p]
        if vals:
            scores[f"total_{k}"] = round(sum(vals), 8)
    return {
        "predictions": predictions,
        "scores": scores,
        "outputs": outputs,
        "reference_tier": ref_tier,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--config", required=True, type=Path)
    ap.add_argument("--repeat", type=int, default=1, help="run N times to measure the arm's spread")
    ap.add_argument("--run-id", help="default: <config_id>_<timestamp>")
    args = ap.parse_args()

    if not args.config.is_file():
        die(f"no config at {args.config}")
    cfg = yaml.safe_load(args.config.read_text(encoding="utf-8")) or {}
    for required in ("config_id", "dataset_id"):
        if required not in cfg:
            die(f"{args.config} is missing required key: {required}")

    ds = load_dataset(cfg["dataset_id"])
    stamp = now().replace(":", "").replace("-", "")
    base_id = args.run_id or f"{cfg['config_id']}_{stamp}"
    build = build_info()
    ref_dir, ref_tier = _reference_for(cfg["dataset_id"])
    if ref_tier:
        print(f"  scoring against {ref_tier.upper()} references for {cfg['dataset_id']}")
    else:
        print(f"  no references for {cfg['dataset_id']} — quality cannot be scored.")
        print(f"  make reference-create DATASET_ID={cfg['dataset_id']} CONFIG=<a model you trust>")
    if build["ref"] == "unknown":
        print("  WARNING: could not identify the build — this run is not attributable")

    made: List[Path] = []
    per_repeat: List[Dict[str, float]] = []
    for i in range(args.repeat):
        run_id = base_id if args.repeat == 1 else f"{base_id}_r{i + 1}"
        result = one_pass(ds, cfg, i)
        run_dir = RUNS / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "predictions.jsonl").write_text(
            "".join(json.dumps(p, sort_keys=True) + "\n" for p in result["predictions"]),
            encoding="utf-8",
        )
        (run_dir / "outputs").mkdir(exist_ok=True)
        for item_id, text in result["outputs"].items():
            (run_dir / "outputs" / f"{item_id}.txt").write_text(text, encoding="utf-8")

        metrics = {
            "run_id": run_id,
            "dataset_id": cfg["dataset_id"],
            "config_id": cfg["config_id"],
            "created_at": now(),
            "build": build,
            "scores": result["scores"],
            "n_items": len(result["predictions"]),
        }
        if result["reference_tier"]:
            metrics["reference_tier"] = result["reference_tier"]
        if args.repeat > 1:
            metrics["repeat_index"] = i + 1
        write_json(run_dir / "metrics.json", metrics)
        made.append(run_dir)
        per_repeat.append(result["scores"])
        print(f"  {run_id}  " + "  ".join(f"{k}={v}" for k, v in result["scores"].items()))

    if args.repeat > 1:
        print("\n  Arm spread over %d repeats (max - min on identical input):" % args.repeat)
        w = max(len(k) for k in per_repeat[0])
        for k in sorted(per_repeat[0]):
            vals = [r[k] for r in per_repeat]
            spread = max(vals) - min(vals)
            verdict = "deterministic" if spread == 0 else f"treat deltas below {spread:.6f} as noise"
            print(f"    {k:{w}} spread={spread:.6f}   {verdict}")

    print(f"\n{len(made)} run(s) under {RUNS}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
