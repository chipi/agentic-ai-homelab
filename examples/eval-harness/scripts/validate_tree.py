#!/usr/bin/env python3
"""Integrity checks over the eval tree. Run it before you trust any number.

Each check exists because its absence let a real defect through somewhere:

  V1  schemas        a document that violates its own contract
  V2  dataset_id     a run citing a dataset that does not exist — the number
                     cannot be attributed to any data
  V3  provenance     a run with no build ref — the number cannot be attributed
                     to any code
  V4  materialized   a dataset whose materialized copy drifted from its hashes
  V5  duplicates     two runs reporting byte-identical scores on the same
                     dataset. Independent arms do not agree to full float
                     precision; one of them is not its own measurement
  V6  baselines      a baseline pointing at a run that no longer exists

Exit 1 on any failure, so it can gate.

    python scripts/validate_tree.py
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import (  # noqa: E402
    BASELINES,
    DATASETS,
    MATERIALIZED,
    ROOT,
    RUNS,
    read_json,
    sha256,
)

try:
    import jsonschema
except ImportError:
    jsonschema = None

SCHEMAS = ROOT / "schemas"
problems: list[str] = []
notes: list[str] = []


def check(ok: bool, label: str, detail: str = "") -> None:
    if ok:
        print(f"  ok   {label}")
    else:
        print(f"  FAIL {label}" + (f" — {detail}" if detail else ""))
        problems.append(label)


def v1_schemas() -> None:
    if jsonschema is None:
        notes.append("V1 skipped: jsonschema not installed (pip install -r requirements.txt)")
        print("  --   V1 schemas (jsonschema not installed)")
        return
    pairs = [
        (DATASETS.glob("*.json"), "dataset.schema.json"),
        ((p / "metrics.json" for p in RUNS.iterdir()) if RUNS.is_dir() else [], "metrics.schema.json"),
        ((p for p in BASELINES.glob("*.json")), "baseline.schema.json"),
    ]
    bad = 0
    n = 0
    for files, schema_name in pairs:
        schema = json.loads((SCHEMAS / schema_name).read_text())
        for f in files:
            if not Path(f).is_file():
                continue
            n += 1
            try:
                jsonschema.validate(read_json(Path(f)), schema)
            except jsonschema.ValidationError as exc:
                bad += 1
                print(f"       {Path(f).name}: {exc.message[:90]}")
    check(bad == 0, f"V1 schemas — {n} document(s) validated", f"{bad} violation(s)")


def v2_dataset_ids() -> None:
    known = {p.stem for p in DATASETS.glob("*.json")}
    dangling = []
    for run in (RUNS.iterdir() if RUNS.is_dir() else []):
        m = run / "metrics.json"
        if m.is_file():
            did = read_json(m).get("dataset_id")
            if did not in known:
                dangling.append(f"{run.name} -> {did}")
    for d in dangling:
        print(f"       {d}")
    check(not dangling, f"V2 every run's dataset_id resolves ({len(known)} dataset(s) known)",
          f"{len(dangling)} dangling")


def v3_provenance() -> None:
    missing = []
    for run in (RUNS.iterdir() if RUNS.is_dir() else []):
        m = run / "metrics.json"
        if m.is_file():
            b = read_json(m).get("build") or {}
            if b.get("ref", "unknown") == "unknown":
                missing.append(run.name)
    for r in missing:
        print(f"       {r}")
    check(not missing, "V3 every run identifies its build", f"{len(missing)} without a ref")


def v4_materialized() -> None:
    drifted = []
    for ds_file in DATASETS.glob("*.json"):
        ds = read_json(ds_file)
        mat = MATERIALIZED / ds["dataset_id"]
        if not mat.is_dir():
            continue
        for item in ds["items"]:
            rel = item.get("source_path") or item["item_id"]
            f = mat / rel
            if f.is_file() and sha256(f) != item["source_sha256"]:
                drifted.append(f"{ds['dataset_id']}/{rel}")
    for d in drifted:
        print(f"       {d}")
    check(not drifted, "V4 materialized copies match their frozen hashes", f"{len(drifted)} drifted")


def v5_duplicate_scores() -> None:
    by_key = defaultdict(list)
    for run in (RUNS.iterdir() if RUNS.is_dir() else []):
        m = run / "metrics.json"
        if m.is_file():
            d = read_json(m)
            key = (d.get("dataset_id"), json.dumps(d.get("scores"), sort_keys=True))
            by_key[key].append((run.name, d.get("config_id")))
    dupes = [v for v in by_key.values() if len({c for _, c in v}) > 1]
    for group in dupes:
        print(f"       identical scores: {', '.join(n for n, _ in group)}")
    check(
        not dupes,
        "V5 no two configs report byte-identical scores",
        f"{len(dupes)} suspicious group(s) — independent arms do not agree to full precision",
    )


def v6_baselines() -> None:
    broken = []
    for b in BASELINES.glob("*.json"):
        d = read_json(b)
        if not (RUNS / d.get("promoted_from", "")).is_dir():
            broken.append(f"{b.name} -> {d.get('promoted_from')}")
    for x in broken:
        print(f"       {x}")
    check(not broken, "V6 every baseline's source run still exists", f"{len(broken)} broken")


def main() -> int:
    print(f"eval tree: {ROOT / 'data'}\n")
    for fn in (v1_schemas, v2_dataset_ids, v3_provenance, v4_materialized, v5_duplicate_scores, v6_baselines):
        fn()
    for n in notes:
        print(f"\n  note: {n}")
    if problems:
        print(f"\nVALIDATION FAILED — {len(problems)} check(s): {', '.join(problems)}")
        return 1
    print("\nVALIDATION PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
