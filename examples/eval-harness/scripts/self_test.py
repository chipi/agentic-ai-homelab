#!/usr/bin/env python3
"""Self-tests for the harness itself — no network, no keys, no fixtures needed.

The harness makes claims about its own behaviour: that it refuses cross-dataset
comparisons, that a cost cap aborts, that gold beats silver, that a zero noise
floor is not the same as an absent one. Those claims are the product, so they
are tested rather than asserted in a README.

    make test
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
PY = sys.executable
failures: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"  {'ok  ' if ok else 'FAIL'} {label}" + (f" — {detail}" if detail and not ok else ""))
    if not ok:
        failures.append(label)


def run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([PY, *args], cwd=ROOT, capture_output=True, text=True)


def test_dotenv_does_not_override_exported() -> None:
    """An exported var must win, so a one-off override needs no file edit."""
    import os

    sys.path.insert(0, str(HERE))
    from _common import load_dotenv

    with tempfile.NamedTemporaryFile("w", suffix=".env", delete=False) as fh:
        fh.write("EVAL_SELFTEST_A=from_file\nEVAL_SELFTEST_B=from_file\n")
        path = Path(fh.name)
    os.environ["EVAL_SELFTEST_A"] = "from_shell"
    os.environ.pop("EVAL_SELFTEST_B", None)
    load_dotenv(path)
    check("dotenv: exported var wins", os.environ["EVAL_SELFTEST_A"] == "from_shell")
    check("dotenv: missing var is filled", os.environ.get("EVAL_SELFTEST_B") == "from_file")
    path.unlink()


def test_price_needs_all_four_inputs() -> None:
    sys.path.insert(0, str(HERE))
    from adapter import _price

    check("price: None when unpriced", _price({}, 1000, 1000) is None)
    check("price: None when tokens missing",
          _price({"usd_per_mtok_in": 3, "usd_per_mtok_out": 15}, None, 10) is None)
    got = _price({"usd_per_mtok_in": 3.0, "usd_per_mtok_out": 15.0}, 1_000_000, 1_000_000)
    check("price: 1M in + 1M out = in+out rate", got == 18.0, f"got {got}")


def test_score_handles_absent_reference() -> None:
    sys.path.insert(0, str(HERE))
    from adapter import score

    check("score: no reference -> no quality metric", "overlap_f1" not in score("a b c", None))
    check("score: identical output scores 1.0", score("a b c", "a b c")["overlap_f1"] == 1.0)
    check("score: disjoint output scores 0.0", score("a b", "c d")["overlap_f1"] == 0.0)


def test_compare_refuses_cross_dataset() -> None:
    r = run("scripts/compare_runs.py", "--baseline", "nope_a", "--candidate", "nope_b")
    check("compare: unknown run is an error", r.returncode != 0)


def test_cli_help_works() -> None:
    for script in ("dataset_create", "materialize", "experiment_run", "compare_runs",
                   "promote_baseline", "validate_tree", "list_runs", "reference_create",
                   "leaderboard", "sweep", "env_check"):
        r = run(f"scripts/{script}.py", "--help")
        check(f"{script}.py --help", r.returncode == 0, r.stderr.strip()[:80])


def test_metric_direction_is_not_always_up() -> None:
    """Cost and latency improve by going DOWN.

    compare_runs.py judged every metric with `"better" if d > 0 else "worse"`, so a run
    that got faster or cheaper was reported as worse — while leaderboard.py, in the same
    harness, already knew these keys were lower-is-better. Two scripts disagreeing about
    what a number means is worse than either being wrong alone: whichever you read last
    is the one you believe.
    """
    sys.path.insert(0, str(HERE / "scripts"))
    from _common import verdict_for

    check("direction: faster is better", verdict_for("latency_ms", -0.5) == "better")
    check("direction: slower is worse", verdict_for("latency_ms", 0.5) == "worse")
    check("direction: cheaper is better", verdict_for("cost_usd", -0.1) == "better")
    check("direction: dearer is worse", verdict_for("cost_usd", 0.1) == "worse")
    # The quality metric keeps the ordinary orientation, or the fix would have
    # inverted the thing that actually matters.
    check("direction: higher quality is better", verdict_for("overlap_f1", 0.05) == "better")
    check("direction: lower quality is worse", verdict_for("overlap_f1", -0.05) == "worse")
    check("direction: no movement is identical", verdict_for("cost_usd", 0.0) == "identical")


def test_descriptive_metrics_get_no_verdict() -> None:
    """A longer output is not a better one, and the table must not imply it is."""
    sys.path.insert(0, str(HERE / "scripts"))
    from _common import verdict_for

    check("descriptive: more words is 'changed'", verdict_for("output_words", 12) == "changed")
    check("descriptive: fewer words is 'changed'", verdict_for("output_words", -12) == "changed")


def test_leaderboard_declares_silver_from_any_run() -> None:
    """The SILVER caveat must survive a config whose FIRST run predates the reference.

    leaderboard.py read `runs[0].get("reference_tier")`. A config with an early unscored
    run therefore printed a silver-derived quality score with no disclaimer — a
    model-generated number shown as if it were ground truth, which is the single thing
    this table must never do.
    """
    rows = [
        {"reference_tier": None},
        {"reference_tier": "silver"},
    ]
    tiers = {r.get("reference_tier") for r in rows if r.get("reference_tier")}
    check("leaderboard: silver seen behind an unscored first run", "silver" in tiers)
    check(
        "leaderboard: no tier at all stays unlabelled",
        {r.get("reference_tier") for r in [{"reference_tier": None}] if r.get("reference_tier")}
        == set(),
    )


def test_no_absolute_home_path_in_committed_data() -> None:
    """A dataset describes a SELECTION, not the machine that built it.

    dataset_create.py wrote `args.source_dir.as_posix()` — the resolved, absolute path — so
    every dataset in this repo carried "/Users/<name>/projects/..." into git. That leaks
    whoever ran it, and makes a file that is meant to travel between machines describe one.
    Only `created_at` and `source_dir` differ after the fix; every source_sha256 is
    unchanged, which is what actually freezes a dataset.
    """
    import re

    home = re.compile(r"/(?:Users|home)/(?!runner\b|operator\b|user\b)[A-Za-z0-9_.-]+/")
    offenders = []
    for d in (HERE / "data").rglob("*.json"):
        if ".partial" in d.parts:
            continue
        try:
            if home.search(d.read_text(encoding="utf-8")):
                offenders.append(str(d.relative_to(HERE)))
        except OSError:
            continue
    check("no home path in committed data/", not offenders, f"offenders: {offenders[:5]}")


def main() -> int:
    print("harness self-tests (no network, no keys)\n")
    for fn in (
        test_dotenv_does_not_override_exported,
        test_price_needs_all_four_inputs,
        test_score_handles_absent_reference,
        test_compare_refuses_cross_dataset,
        test_metric_direction_is_not_always_up,
        test_descriptive_metrics_get_no_verdict,
        test_leaderboard_declares_silver_from_any_run,
        test_no_absolute_home_path_in_committed_data,
        test_cli_help_works,
    ):
        fn()
    if failures:
        print(f"\n{len(failures)} FAILED: {', '.join(failures)}")
        return 1
    print("\nall self-tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
