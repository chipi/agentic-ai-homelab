"""Shared helpers. Deliberately tiny — the skeleton should be readable in one sitting."""

from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

ROOT = Path(__file__).resolve().parents[1]


def load_dotenv(path: Optional[Path] = None) -> int:
    """Read `.env` into the environment. No dependency, no surprises.

    Loaded by every script, so keys are never exported by hand and never pasted
    into a command that lands in shell history. An already-exported variable
    WINS — so `ANTHROPIC_API_KEY=... make experiment-run` overrides the file
    for one call without editing it.

    Copy `.env.example` to `.env` to start. `.env` is gitignored.
    """
    import os

    env_path = path or (ROOT / ".env")
    if not env_path.is_file():
        return 0
    loaded = 0
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key, val = key.strip(), val.strip().strip('"').strip("'")
        if key and val and key not in os.environ:
            os.environ[key] = val
            loaded += 1
    return loaded


DOTENV_LOADED = load_dotenv()


def env_float(name: str, default: Optional[float] = None) -> Optional[float]:
    import os

    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        raise SystemExit(f"ERROR: {name}={raw!r} is not a number")


def env_int(name: str, default: int) -> int:
    v = env_float(name, float(default))
    return int(v) if v is not None else default
DATA = ROOT / "data"
SOURCES = DATA / "sources"
DATASETS = DATA / "datasets"
MATERIALIZED = DATA / "materialized"
CONFIGS = DATA / "configs"
RUNS = DATA / "runs"
BASELINES = DATA / "baselines"
REFERENCES = DATA / "references"


class CostCapExceeded(RuntimeError):
    """Raised mid-run when EVAL_MAX_COST_USD is reached.

    Deliberately an abort rather than a pre-flight estimate: estimates are
    usually wrong (token counts vary, cache hits change pricing), and an abort
    stops the bill the moment the cap is hit. Callers catch it and write
    whatever they have, so a capped run still yields a usable partial report.
    """


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


# ── what a metric MEANS ──────────────────────────────────────────────────────
# These lived in leaderboard.py, which used them to pick a sort key and to warn
# when someone ranked on a descriptive metric. compare_runs.py had no idea they
# existed and judged every metric with one hardcoded direction:
#
#     verdict = "better" if d > 0 else "worse"
#
# So a run that got FASTER was reported "worse", and one that got more EXPENSIVE
# would have been reported "better". Two scripts in the same harness disagreed
# about what a number means, which is worse than either being wrong alone —
# whichever one you read last is the one you believe.

#: Lower is better. Cost and token counts.
COST_KEYS = (
    "total_cost_usd",
    "cost_usd",
    "total_tokens_in",
    "total_tokens_out",
    "tokens_in",
    "tokens_out",
)
#: Lower is better. Wall time.
SPEED_KEYS = ("latency_ms",)
#: Neither better nor worse: they say what the output WAS, not whether it was
#: good. Ranking by one puts the most verbose arm on top — which is how a
#: leaderboard ends up confidently answering the wrong question. Comparing two
#: of them and calling the bigger one "better" is the same error, per-metric.
DESCRIPTIVE_KEYS = ("output_words", "output_chars", "lines", "chars", "n_items")


def lower_is_better(metric: str) -> bool:
    """Whether a DECREASE in ``metric`` is an improvement (cost, tokens, latency)."""
    return metric in COST_KEYS or metric in SPEED_KEYS or metric.startswith("total_tokens")


def is_descriptive(metric: str) -> bool:
    """Whether ``metric`` describes the output rather than judging it.

    A direction cannot be assigned to these, so callers must say "changed"
    rather than "better" or "worse".
    """
    return metric in DESCRIPTIVE_KEYS


def verdict_for(metric: str, delta: float) -> str:
    """"better" / "worse" / "changed" / "identical" for ``delta`` on ``metric``.

    The one place that decides what a movement MEANS. Descriptive metrics get
    "changed" on purpose: calling a longer output "better" is a claim the number
    cannot support, and it is exactly the claim a reader will take away.
    """
    if delta == 0:
        return "identical"
    if is_descriptive(metric):
        return "changed"
    improved = delta < 0 if lower_is_better(metric) else delta > 0
    return "better" if improved else "worse"
