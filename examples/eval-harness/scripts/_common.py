"""Shared helpers. Deliberately tiny — the skeleton should be readable in one sitting."""

from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
SOURCES = DATA / "sources"
DATASETS = DATA / "datasets"
MATERIALIZED = DATA / "materialized"
CONFIGS = DATA / "configs"
RUNS = DATA / "runs"
BASELINES = DATA / "baselines"
REFERENCES = DATA / "references"


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def build_info() -> Dict[str, Any]:
    """Identify the SYSTEM UNDER TEST.

    Three inputs decide what an eval means: the system under test, the
    instrument (this harness), and the data (`dataset_id`). Record the first
    here, or a delta cannot be attributed to a code change rather than an
    instrument change.

    Replace this with whatever identifies YOUR system — a package version, an
    image digest, a model id. The git SHA is only the default because most
    skeletons start life inside a repo.
    """
    # A drop-in often lives outside a git repo — a copied directory, a mounted
    # folder, a container. The first cold walk of this skeleton produced four
    # runs with ref="unknown" for exactly that reason, and `make validate`
    # (correctly) refused them. So identity is CONFIGURABLE, not code:
    #
    #     EVAL_BUILD_REF=v2.3.1              a release
    #     EVAL_BUILD_REF=sha256:ab12…        an image digest
    #     EVAL_BUILD_REF=$(pip show pkg …)   an installed version
    #
    # Falling back to this tree's git SHA only when nothing is declared.
    import os

    declared = os.environ.get("EVAL_BUILD_REF")
    if declared:
        return {"ref": declared, "dirty": False, "source": "EVAL_BUILD_REF"}

    def git(*args: str) -> Optional[str]:
        try:
            out = subprocess.run(
                ["git", *args], cwd=ROOT, capture_output=True, text=True, timeout=5
            )
            return out.stdout.strip() if out.returncode == 0 else None
        except (OSError, subprocess.SubprocessError):
            return None

    ref = git("rev-parse", "HEAD")
    status = git("status", "--porcelain")
    return {
        "ref": ref or "unknown",
        "dirty": bool(status),
        "source": "git",
    }


def load_dataset(dataset_id: str) -> Dict[str, Any]:
    path = DATASETS / f"{dataset_id}.json"
    if not path.is_file():
        raise SystemExit(
            f"no such dataset: {dataset_id}\n"
            f"  expected {path}\n"
            f"  create one with: make dataset-create DATASET_ID={dataset_id}"
        )
    return read_json(path)


def iter_runs() -> Iterable[Path]:
    if not RUNS.is_dir():
        return []
    return sorted(p for p in RUNS.iterdir() if (p / "metrics.json").is_file())


def die(msg: str) -> "NoReturn":  # type: ignore[valid-type]
    raise SystemExit(f"ERROR: {msg}")
