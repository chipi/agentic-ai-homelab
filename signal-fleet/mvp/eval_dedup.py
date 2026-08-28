"""Deterministic dedup-efficacy eval (EVAL.md companion, #1 regression guard).

score.py measures the LLM triager; eval_hardening.py measures the deterministic
classifier gates; THIS measures the DETERMINISTIC FILING STAGE — how much the
normalized dedup key (#1) + operational gate + low-signal rollup actually collapse a
real signal corpus into distinct GitHub issues. It replays a frozen, scrubbed sample
of 100 real GlitchTip signals (reference-dedup/corpus.json) and ASSERTS the collapse,
so the ~40% volume win the 2026-08-27 cleanup pass asked for can't silently regress.
No LLM, no network, no flakes: same corpus -> same numbers, every run.

  python3 eval_dedup.py            # print the report, exit non-zero if below floor

Cultivate: refreeze the corpus (build from a fresh GlitchTip pull, scrub.py) when the
signal mix changes materially; keep the thresholds a margin below the live number.
"""
import json
import os
import sys

os.environ.setdefault("SF_OBSERV_DISABLED", "1")

import filing
import sources
import triage

CORPUS = os.path.join(os.path.dirname(__file__), "..", "reference-dedup", "corpus.json")

# floors — a margin below the 2026-08-28 measured numbers (collapse 55%, top cluster
# x12). If a change drops dedup below these, the incident becomes a red test.
MIN_COLLAPSE_PCT = 40      # norm_key must cut fileable issues by >= this
MIN_TOP_CLUSTER = 8        # the largest logical bug must merge >= this many fingerprints


def _is_test(s):
    r = s.get("raw") or {}
    m = r.get("metadata") or {}
    return sources._is_test_signal(s.get("alertname"), r.get("culprit"),
                                   r.get("shortId"), m.get("value"), m.get("type"))


def measure(signals):
    operational = sum(1 for s in signals if triage.operational_class(s))
    test = sum(1 for s in signals if _is_test(s))
    fileable = [s for s in signals
                if not triage.operational_class(s) and not _is_test(s)]
    old_units = len({s["fingerprint"] for s in fileable})       # 1 issue / fingerprint
    keys = {}
    for s in fileable:
        keys.setdefault(filing.normalized_key(s) or s["fingerprint"], []).append(s)
    low = sum(1 for s in fileable if filing.low_signal(s))
    top = max((len(v) for v in keys.values()), default=0)
    collapse = (old_units - len(keys)) / old_units * 100 if old_units else 0.0
    return {"total": len(signals), "operational": operational, "test": test,
            "fileable": len(fileable), "old_units": old_units, "new_units": len(keys),
            "collapse_pct": collapse, "low_signal": low, "top_cluster": top, "keys": keys}


def main():
    data = json.load(open(CORPUS))
    signals = data["signals"]
    m = measure(signals)
    print(f"dedup-efficacy eval — {m['total']} frozen real signals (deterministic, no LLM)\n")
    print(f"  operational (dismissed)         : {m['operational']}")
    print(f"  test/synthetic (suppressed)     : {m['test']}")
    print(f"  FILEABLE (reach filing)         : {m['fileable']}")
    print(f"  OLD (per-fingerprint) issues    : {m['old_units']}")
    print(f"  NEW (per-norm_key)   issues     : {m['new_units']}")
    print(f"  low-signal (folded to rollups)  : {m['low_signal']}")
    print(f"  COLLAPSE                        : {m['old_units']} -> {m['new_units']} "
          f"= {m['collapse_pct']:.0f}% fewer issues")
    print("\n  biggest merges (norm_key -> fingerprints collapsed):")
    for k, v in sorted(m["keys"].items(), key=lambda kv: -len(kv[1]))[:6]:
        if len(v) > 1:
            print(f"    x{len(v):2}  {v[0]['alertname'][:58]}")

    fails = []
    if m["collapse_pct"] < MIN_COLLAPSE_PCT:
        fails.append(f"collapse {m['collapse_pct']:.0f}% < floor {MIN_COLLAPSE_PCT}%")
    if m["top_cluster"] < MIN_TOP_CLUSTER:
        fails.append(f"top cluster x{m['top_cluster']} < floor x{MIN_TOP_CLUSTER}")
    print()
    if fails:
        print("FAIL: " + "; ".join(fails))
        return 1
    print(f"PASS (collapse {m['collapse_pct']:.0f}% >= {MIN_COLLAPSE_PCT}%, "
          f"top cluster x{m['top_cluster']} >= x{MIN_TOP_CLUSTER})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
