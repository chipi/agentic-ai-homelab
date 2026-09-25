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
import importlib.util
import statistics
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _fingerprint import build_fingerprint  # noqa: E402
from _common import (  # noqa: E402
    MATERIALIZED,
    REFERENCES,
    ROOT,
    RUNS,
    CostCapExceeded,
    build_info,
    die,
    env_float,
    load_dataset,
    now,
    read_json,
    write_json,
)

try:
    import yaml
except ImportError:  # pragma: no cover
    die("pyyaml is required — pip install -r requirements.txt")





def _adapter_metric_kinds(adapter_id: str, adapter_path: Optional[Path]) -> Dict[str, str]:
    """`METRIC_KINDS` from the loaded adapter module, or {}."""
    module = sys.modules.get(f"eval_adapter_{adapter_path.stem}") if adapter_path else None
    if module is None:
        try:
            import adapter as module  # noqa: PLC0415
        except ImportError:
            return {}
    kinds = getattr(module, "METRIC_KINDS", None)
    return dict(kinds) if isinstance(kinds, dict) else {}


def _adapter_primary_metric(adapter_path: Optional[Path]) -> Optional[str]:
    """`PRIMARY_METRIC` from the adapter, or None.

    WHICH quality facet heads the table is a judgement the adapter author makes, not
    something to settle alphabetically. Without this the leaderboard sorted by whichever
    quality metric sorted first by name -- which, for a summariser declaring `coverage`
    and `concision`, is `concision`: brevity, quietly promoted to the headline. The same
    shape of accident once ranked a ten-model sweep by `compression`.
    """
    module = sys.modules.get(f"eval_adapter_{adapter_path.stem}") if adapter_path else None
    if module is None:
        try:
            import adapter as module  # noqa: PLC0415
        except ImportError:
            return None
    value = getattr(module, "PRIMARY_METRIC", None)
    return value if isinstance(value, str) and value else None

def _score_wants_source(score: Any) -> bool:
    """Whether this adapter's `score()` takes the source text as a third argument.

    Arity, not configuration: the bundled adapter scores output against reference and has
    no use for the input, while a summarisation adapter needs it to measure grounding.
    Inspected once per run rather than guessed, so an adapter that does not want it is
    never handed an argument it cannot take.
    """
    import inspect  # noqa: PLC0415

    try:
        params = inspect.signature(score).parameters
    except (TypeError, ValueError):
        return False
    positional = [
        p for p in params.values()
        if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)
    ]
    return len(positional) >= 3 or any(p.kind is p.VAR_POSITIONAL for p in params.values())


def _portable_id(path: Path) -> str:
    """A path safe to write into a run record: relative, resolved, never a home directory.

    This is recorded in `metrics.json` and hashed into the fingerprint, so an absolute
    path both leaks the author's username into anything published and makes two identical
    runs on two machines look different.

    The old version tried `relative_to(ROOT)` on an UNRESOLVED path. Adapters live in
    sibling example directories, so that never matched -- `configs/../adapter.py` is not
    under the harness root -- and every run silently fell back to the absolute path.
    Resolve first, then widen the base one level so a sibling example resolves cleanly,
    and if even that fails keep only the last two components rather than emit a home path.
    """
    resolved = path.resolve()
    for base in (ROOT, ROOT.parent):
        try:
            return str(resolved.relative_to(base))
        except ValueError:
            continue
    return str(Path(*resolved.parts[-2:]))


def load_adapter(
    spec: Optional[str], config_path: Optional[Path] = None
) -> tuple[Any, Any, str, Optional[Path], Any, Any]:
    """``(call_system, score, adapter_id)`` for the adapter a config names.

    Defaults to ``scripts/adapter.py`` — the single seam, unchanged for anyone who has one
    system to measure. A config may name its own instead:

        adapter: examples/summarization-cnn-dailymail/adapter.py

    That exists because an example is not just a different model, it is a different TASK:
    summarisation scores ROUGE, classification scores macro-F1, and neither is the token
    overlap the bundled adapter computes. One adapter file per task, selected by the arm,
    keeps "an arm is a YAML file" true.

    The returned id is recorded on the run. It has to be: a scorer is half of what a number
    means, so two runs sharing a config_id but scored by different adapters are no more
    comparable than two runs on different datasets. run-compare refuses across it.
    """
    if not spec:
        from adapter import call_system, score  # noqa: PLC0415
        import adapter as _default  # noqa: PLC0415

        return (
            call_system,
            score,
            "scripts/adapter.py",
            Path(__file__).resolve().parent / "adapter.py",
            getattr(_default, "warmup", None),
            getattr(_default, "fingerprint", None),
        )

    # Relative to the CONFIG first, then the harness root. An example's arm sits beside its
    # adapter and should be able to say `adapter: adapter.py` — the two travel together, and
    # a path written from the harness's point of view breaks the moment the example moves.
    path = Path(spec)
    candidates = []
    if path.is_absolute():
        candidates = [path]
    else:
        if config_path is not None:
            candidates.append(config_path.resolve().parent / path)
        candidates.append(ROOT / path)
    for candidate in candidates:
        if candidate.is_file():
            path = candidate
            break
    else:
        die(
            f"adapter not found: {spec}\n"
            + "".join(f"  looked in: {c}\n" for c in candidates)
        )
    module_spec = importlib.util.spec_from_file_location(f"eval_adapter_{path.stem}", path)
    if module_spec is None or module_spec.loader is None:
        die(f"adapter is not importable: {path}")
    module = importlib.util.module_from_spec(module_spec)
    # Register BEFORE exec: @dataclass resolves its own module via sys.modules[cls.__module__],
    # and an unregistered module makes that None — the decorator then dies on a Result class
    # that is perfectly valid. Any module-level dataclass in an adapter would hit this.
    sys.modules[module_spec.name] = module
    module_spec.loader.exec_module(module)
    for required in ("call_system", "score"):
        if not hasattr(module, required):
            die(f"adapter {spec} defines no {required}()")
    adapter_id = _portable_id(path)
    return (
        module.call_system,
        module.score,
        adapter_id,
        path,
        getattr(module, "warmup", None),
        getattr(module, "fingerprint", None),
    )

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


def one_pass(
    ds: Dict[str, Any],
    cfg: Dict[str, Any],
    idx: int,
    resume_dir: Optional[Path] = None,
    *,
    call_system: Any,
    score: Any,
) -> Dict[str, Any]:
    """One pass over the dataset. ``call_system``/``score`` are INJECTED rather than
    imported at module scope, because which adapter runs is a property of the arm now."""
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
    spent = 0.0
    cap = env_float("EVAL_MAX_COST_USD")
    capped_at: Optional[str] = None

    for item in ds["items"]:
        # Resume: an item already produced by this run is not paid for twice.
        # A sweep that died at item 15 of 20 resumes at 16.
        done = resume_dir / f"{item['item_id']}.txt" if resume_dir else None
        if done is not None and done.is_file():
            outputs[item["item_id"]] = done.read_text(encoding="utf-8")
            continue

        # Check BEFORE the call: the cap is a ceiling on spend, not a report of
        # having exceeded it.
        if cap is not None and spent >= cap:
            capped_at = item["item_id"]
            break

        rel = item.get("source_path") or item["item_id"]
        src = mat / rel
        source_text = src.read_text(encoding="utf-8", errors="replace")
        res = call_system(source_text, params)
        outputs[item["item_id"]] = res.output
        if res.cost_usd:
            spent += res.cost_usd

        reference = None
        if ref_dir is not None:
            rf = ref_dir / f"{item['item_id']}.txt"
            if rf.is_file():
                reference = rf.read_text(encoding="utf-8", errors="replace")

        # Pass the SOURCE when the scorer wants it. Facets that compare the output to the
        # INPUT — grounding, compression — cannot be computed from output+reference alone,
        # and a scorer asking for a third argument used to get None silently: the
        # hallucination check simply never ran and nothing said so.
        scored = (
            score(res.output, reference, source_text)
            if _score_wants_source(score)
            else score(res.output, reference)
        )
        row: Dict[str, Any] = {"item_id": item["item_id"], **scored}
        for field_name in ("latency_ms", "tokens_in", "tokens_out", "cost_usd"):
            v = getattr(res, field_name)
            if v is not None:
                row[field_name] = float(v)
        row.update({k: float(v) for k, v in res.extra.items()})
        # Raw provider metadata rides along under a `_`-prefixed key. Everything
        # `_`-prefixed is excluded from the aggregation below, so an adapter can record
        # a nested dict (a usage object, a finish_reason) without the mean-of-every-key
        # loop trying to average it.
        if res.meta:
            row["_meta"] = res.meta
        predictions.append(row)

    keys = sorted(
        {k for p in predictions for k in p if k != "item_id" and not k.startswith("_")}
    )
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
        "capped_at": capped_at,
        "spent_usd": round(spent, 8),
    }


def _dry_run(ds: Dict[str, Any], cfg: Dict[str, Any], repeat: int) -> int:
    """Shape and cost the sweep without calling anything.

    A pre-flight estimate is not a substitute for the mid-run cap — token
    counts vary and cache hits change pricing, so this is an order of
    magnitude, not a quote. Its job is to stop you discovering that an arm
    is 40x another one's price AFTER the invoice.
    """
    params = dict(cfg.get("params") or {})
    items = ds["items"]
    mat = MATERIALIZED / ds["dataset_id"]
    chars = sum(
        len((mat / (i.get("source_path") or i["item_id"])).read_text(errors="replace"))
        for i in items
        if (mat / (i.get("source_path") or i["item_id"])).is_file()
    )
    # ~4 chars per token is the usual English rule of thumb; it is a rule of
    # thumb, and the number below inherits that.
    est_in = chars / 4
    est_out = int(params.get("max_tokens", 600)) * len(items)
    calls = len(items) * repeat

    print(f"DRY RUN — nothing was called\n")
    print(f"  config      {cfg['config_id']}  ({params.get('provider', 'echo')}"
          + (f" / {params['model']}" if params.get("model") else "") + ")")
    print(f"  dataset     {ds['dataset_id']}  ({len(items)} items)")
    print(f"  repeats     {repeat}")
    print(f"  API calls   {calls}")
    print(f"  input       ~{est_in / 1000:.1f}k tokens/pass (from {chars / 1000:.0f}k chars)")
    print(f"  output      <= {est_out / 1000:.1f}k tokens/pass (max_tokens x items)")

    pin, pout = params.get("usd_per_mtok_in"), params.get("usd_per_mtok_out")
    if pin is None or pout is None:
        print("\n  No price in the config, so no estimate. Add usd_per_mtok_in /")
        print("  usd_per_mtok_out and the run will record what it actually cost.")
    else:
        est = (est_in / 1e6 * float(pin) + est_out / 1e6 * float(pout)) * repeat
        print(f"\n  ESTIMATE    ~${est:.4f}  (upper bound: assumes max_tokens every time)")
    cap = env_float("EVAL_MAX_COST_USD")
    print(f"  cap         " + (f"${cap:.2f} (EVAL_MAX_COST_USD)" if cap else "NONE — set EVAL_MAX_COST_USD"))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--config", required=True, type=Path)
    ap.add_argument("--repeat", type=int, default=1, help="run N times to measure the arm's spread")
    ap.add_argument("--run-id", help="default: <config_id>_<timestamp>")
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="cost and shape the sweep WITHOUT calling anything",
    )
    ap.add_argument(
        "--resume",
        metavar="RUN_ID",
        help="reuse outputs already produced by RUN_ID; only pay for what is missing",
    )
    args = ap.parse_args()

    if not args.config.is_file():
        die(f"no config at {args.config}")
    cfg = yaml.safe_load(args.config.read_text(encoding="utf-8")) or {}
    call_system, score, adapter_id, adapter_path, warmup, model_fingerprint = load_adapter(
        cfg.get("adapter"), Path(args.config)
    )
    metric_kinds = _adapter_metric_kinds(adapter_id, adapter_path)
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

    if args.dry_run:
        return _dry_run(ds, cfg, args.repeat)

    # WARM UP once per arm, before anything is timed. Two jobs in one:
    #
    #   measurement — a local model's first call includes loading its weights. Left in the
    #   timed path that cost lands in latency_ms and gets amortised over the dataset, so
    #   the arm looks catastrophically slow on 5 items and fine on 500: the metric would
    #   be measuring dataset size.
    #
    #   pre-flight — a bad key or an absent model fails HERE, before any item is paid for,
    #   instead of on item 34 of 50 after you have already paid for 33.
    #
    # Once per ARM, not per repeat: REPEAT exists to measure the arm's own jitter, and
    # letting load variance into that measures the wrong thing.
    warmup_ms: Optional[float] = None
    if warmup is not None:
        started = time.perf_counter()
        try:
            warmup(dict(cfg.get("params") or {}))
        except Exception as exc:  # noqa: BLE001 - fail before spending, with the reason
            die(
                f"warm-up failed for {cfg['config_id']}: {type(exc).__name__}: {exc}\n"
                "  nothing was run and nothing was spent."
            )
        warmup_ms = round((time.perf_counter() - started) * 1000, 3)
        print(f"  warmed up in {warmup_ms:.0f}ms — timing below excludes it")

    fingerprint = build_fingerprint(
        root=ROOT,
        dataset=ds,
        reference_id=(str(ref_dir.relative_to(REFERENCES)) if ref_dir else None),
        reference_tier=ref_tier,
        config_id=cfg["config_id"],
        params=dict(cfg.get("params") or {}),
        adapter_id=adapter_id,
        adapter_path=adapter_path,
        model_hook=model_fingerprint,
    )
    print(f"  fingerprint {fingerprint['hash'][:12]}")
    # A DIRTY TREE IS NOT A VERSION. The fingerprint records it, but a field nobody reads
    # is not a warning: a 72-run sweep completed with `harness.dirty: true` throughout, so
    # its `harness.commit` identified code that was never what ran, and nothing said so
    # until the runs were audited afterwards. Say it at the top of the run, where the
    # person paying for it will see it.
    if (fingerprint.get("instrument", {}).get("harness", {}) or {}).get("dirty"):
        print("  WARNING: harness tree is DIRTY — the recorded commit does not identify\n"
              "           the code that is about to run. Commit first for a reproducible\n"
              "           record, or accept that this run cannot be reproduced from its\n"
              "           own fingerprint.")

    resume_dir = (RUNS / args.resume / "outputs") if args.resume else None
    if args.resume and not resume_dir.is_dir():
        die(f"cannot resume: no outputs under {resume_dir}")

    made: List[Path] = []
    per_repeat: List[Dict[str, float]] = []
    for i in range(args.repeat):
        run_id = base_id if args.repeat == 1 else f"{base_id}_r{i + 1}"
        result = one_pass(
            ds, cfg, i, resume_dir=resume_dir, call_system=call_system, score=score
        )
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
            # The knobs this run ACTUALLY used, not just the config's name. A config_id
            # names a file, and a file can be edited after the run — so without this a run
            # cannot say what produced it, only which YAML was pointed at. It also lets V5
            # tell a deterministic repeat (same params, same scores — expected) from two
            # different configs landing on byte-identical output (worth a look).
            "params": dict(cfg.get("params") or {}),
            # WHICH scorer produced these numbers. A scorer is half of what a number means,
            # so a run that does not name it cannot be compared to one that used another.
            "adapter": adapter_id,
            # The adapter's own reading of its metrics, carried on the run so a leaderboard
            # built later does not have to guess what `compression` is.
            "metric_kinds": dict(metric_kinds or {}),
            "primary_metric": _adapter_primary_metric(adapter_path),
            # Outside `scores` on purpose: real, worth seeing, but not the arm's per-item
            # speed — and in scores it would reach the leaderboard's speed column and V5's
            # duplicate key, where it means something else.
            "warmup_ms": warmup_ms,
            # What this number depended on, and one hash over all of it. A comparison is
            # only valid if exactly one field moved; this is what makes that checkable
            # rather than asserted.
            "fingerprint": fingerprint,
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
        if result["capped_at"]:
            print(
                f"\n  COST CAP HIT at item {result['capped_at']} — "
                f"spent ${result['spent_usd']:.4f} of EVAL_MAX_COST_USD.\n"
                f"  Partial results kept. Raise the cap and resume without paying twice:\n"
                f"    make experiment-run CONFIG={args.config} ARGS=\"--resume {run_id}\""
            )
            break

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
