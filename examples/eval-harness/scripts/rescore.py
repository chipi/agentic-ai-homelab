#!/usr/bin/env python3
"""Re-score finished runs from their stored outputs. No API calls, no money.

The outputs are the expensive part of a run; the scores are arithmetic over them. But
scores were only ever computed at run time, so every change to a metric meant re-running
the whole sweep — ~$1.45 and 80 minutes to answer "what would this look like under a
different measure". That is backwards, and it is why a scorer bug survived two sweeps:
checking it would have cost another one.

    make rescore DATASET_ID=my_v1 MATCH=_v2 OUT=data/runs-rescored
    EVAL_RUNS_DIR=data/runs-rescored make leaderboard DATASET_ID=my_v1

Rescored runs are written to a SEPARATE directory, never over the originals. Two reasons:
the originals are the record of what was actually measured and paid for, and a rescored
run grouped under the same `config_id` as its source would average two different metrics
into one row. Point the leaderboard at the new directory with EVAL_RUNS_DIR.

What is recomputed: everything `score()` returns. What is carried across untouched:
latency, cost, token counts and the raw provider `_meta` — those are properties of the
call that happened, not of how it was later measured, and re-deriving them would be
inventing them.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import MATERIALIZED, REFERENCES, RUNS, ROOT, die, now, read_json, write_json  # noqa: E402
from experiment_run import load_adapter, _score_wants_source  # noqa: E402

try:
    import yaml
except ImportError:  # pragma: no cover
    die("pyyaml is required — pip install -r requirements.txt")

#: Carried across from the original run rather than recomputed: these describe the CALL,
#: not the measurement. A rescore that recomputed a latency would be reporting a number
#: no clock ever produced.
#:
#: This is a FLOOR, not the whole list. Anything else the original row carried that the
#: new scorer does not produce is carried too — `truncated` and `reasoning_tokens` come
#: from the adapter's `Result.extra` at call time and are unrecoverable afterwards, and a
#: fixed list silently dropped them on the first run of this script.
CARRY = ("latency_ms", "tokens_in", "tokens_out", "cost_usd")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dataset-id", required=True)
    ap.add_argument("--match", help="only runs whose config_id contains this substring")
    ap.add_argument("--out", type=Path, default=ROOT / "data/runs-rescored")
    ap.add_argument("--config-dir", type=Path,
                    help="where to find the arm configs naming the adapter "
                         "(default: alongside each run's recorded adapter path)")
    args = ap.parse_args()

    srcs = [
        d for d in (RUNS.iterdir() if RUNS.is_dir() else [])
        if (d / "metrics.json").is_file()
    ]
    todo = []
    for d in srcs:
        m = read_json(d / "metrics.json")
        if m.get("dataset_id") != args.dataset_id:
            continue
        if args.match and args.match not in m.get("config_id", ""):
            continue
        todo.append((d, m))
    if not todo:
        die(f"no runs on {args.dataset_id!r}" + (f" matching {args.match!r}" if args.match else ""))

    mat = MATERIALIZED / args.dataset_id
    print(f"rescoring {len(todo)} run(s) -> {args.out}")
    args.out.mkdir(parents=True, exist_ok=True)

    adapters: Dict[str, Any] = {}
    written = 0
    for d, m in sorted(todo, key=lambda t: t[0].name):
        spec = m.get("adapter")
        if not spec:
            print(f"  SKIP {d.name}: the run records no adapter")
            continue
        if spec not in adapters:
            # Adapter ids are relative to the HARNESS root for its own bundled adapter
            # ("scripts/adapter.py") and to the examples root for an example's
            # ("summarization-cnn-dailymail/adapter.py"). Assuming one broke the other:
            # `make rescore DATASET_ID=smoke_v1` died looking for examples/scripts/adapter.py.
            for base in (ROOT, ROOT.parent):
                cand = Path(spec) if Path(spec).is_absolute() else base / spec
                if cand.is_file():
                    adapters[spec] = load_adapter(str(cand), None)
                    break
            else:
                die(f"adapter not found for {d.name}: {spec!r} is under neither "
                    f"{ROOT} nor {ROOT.parent}")
        _call, score, adapter_id, adapter_path, _warm, _fp = adapters[spec]
        wants_source = _score_wants_source(score)

        tier = m.get("reference_tier")
        ref_dir = (REFERENCES / m["fingerprint"]["data"]["reference_id"]) \
            if (m.get("fingerprint", {}).get("data", {}) or {}).get("reference_id") else None

        rows: List[Dict[str, Any]] = []
        # Keys the ADAPTER attached at call time (Result.extra) rather than at score time:
        # `truncated`, `reasoning_tokens`. Unrecoverable afterwards, so they ride along.
        extra_keys = set(m.get("metric_kinds", {})) & {"truncated", "reasoning_tokens"}
        extra_keys |= {"truncated", "reasoning_tokens"}
        dropped: set = set()
        for line in (d / "predictions.jsonl").read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            old = json.loads(line)
            item_id = old["item_id"]
            out_f = d / "outputs" / f"{item_id}.txt"
            if not out_f.is_file():
                die(f"{d.name}: no stored output for {item_id} — cannot rescore")
            output = out_f.read_text(encoding="utf-8")
            reference = None
            if ref_dir:
                rf = ref_dir / f"{item_id}.txt"
                if rf.is_file():
                    reference = rf.read_text(encoding="utf-8", errors="replace")
            source_text = None
            # `source_path` is the dataset's own name for the file; it only happens to
            # equal "<item_id>.txt" here. Ignoring it means source_text is silently None
            # on any dataset that names files differently -- and a scorer that wanted the
            # source then measures nothing, quietly.
            rel = (old.get("source_path") or f"{item_id}.txt")
            for cand in (mat / rel, mat / f"{item_id}.txt", mat / item_id):
                if cand.is_file():
                    source_text = cand.read_text(encoding="utf-8", errors="replace")
                    break
            scored = (score(output, reference, source_text) if wants_source
                      else score(output, reference))
            row: Dict[str, Any] = {"item_id": item_id, **scored}
            for k, v in old.items():
                if k == "item_id" or k in scored:
                    continue
                # Carry ONLY things that describe the call. "Keep everything the new
                # scorer does not produce" was too generous: it carried the previous
                # scorer's metrics (`rouge2`, `rougeL`) into the rescored run, where the
                # leaderboard showed them as live quality columns beside the new ones.
                # A rescored run must not report a number the current scorer never
                # computed.
                if k in CARRY or k in extra_keys or k.startswith("_"):
                    row[k] = v
                else:
                    dropped.add(k)
            rows.append(row)

        import statistics
        keys = sorted({k for r in rows for k in r if k != "item_id" and not k.startswith("_")})
        scores = {k: round(statistics.fmean([float(r[k]) for r in rows if k in r]), 10)
                  for k in keys}
        for k in ("cost_usd", "tokens_in", "tokens_out"):
            vals = [float(r[k]) for r in rows if k in r]
            if vals:
                scores[f"total_{k}"] = round(sum(vals), 8)

        run_dir = args.out / d.name
        (run_dir / "outputs").mkdir(parents=True, exist_ok=True)
        for f in (d / "outputs").glob("*.txt"):
            shutil.copy2(f, run_dir / "outputs" / f.name)
        (run_dir / "predictions.jsonl").write_text(
            "".join(json.dumps(r, sort_keys=True) + "\n" for r in rows), encoding="utf-8")
        new = dict(m)
        new["scores"] = scores
        new["metric_kinds"] = _kinds(adapter_path) or m.get("metric_kinds") or {}
        new["primary_metric"] = _primary(adapter_path) or m.get("primary_metric")
        # Provenance of the RESCORE itself: which run it came from, and which scorer
        # produced these numbers. Without this a rescored run is indistinguishable from
        # a measured one, which is the whole risk of having this script at all.
        new["rescored_from"] = d.name
        new["rescored_at"] = now()
        new["rescored_with"] = {
            "adapter": adapter_id,
            "sha256": _sha(adapter_path),
        }
        # The fingerprint is copied from the source run, and its `instrument.adapter`
        # identifies the scorer that produced the ORIGINAL numbers -- not these. Left
        # alone, a rescored run asserts the old scorer in the one field meant to identify
        # it, and every downstream tool (compare_runs, validate_tree, promote_baseline)
        # believes it. Overwrite it and invalidate the hash, which no longer describes
        # anything that was computed together.
        fp = new.get("fingerprint")
        if isinstance(fp, dict):
            fp = json.loads(json.dumps(fp))
            fp.setdefault("instrument", {})["adapter"] = {
                "id": adapter_id, "sha256": _sha(adapter_path),
            }
            fp["hash"] = None
            fp["hash_invalid_because"] = (
                "scores were recomputed by a different scorer than the one this "
                "fingerprint was built from; see rescored_with"
            )
            new["fingerprint"] = fp
        if dropped:
            new["rescore_dropped_metrics"] = sorted(dropped)
        write_json(run_dir / "metrics.json", new)
        written += 1
        print(f"  {d.name}  -> {len(rows)} item(s)")

    print(f"\n{written} run(s) rescored into {args.out}")
    print(f"  EVAL_RUNS_DIR={args.out} make leaderboard DATASET_ID={args.dataset_id}")
    return 0


def _kinds(path):
    from experiment_run import _adapter_metric_kinds
    return _adapter_metric_kinds("", path)


def _primary(path):
    from experiment_run import _adapter_primary_metric
    return _adapter_primary_metric(path)


def _sha(path):
    import hashlib
    return hashlib.sha256(Path(path).read_bytes()).hexdigest() if path else None


if __name__ == "__main__":
    raise SystemExit(main())
