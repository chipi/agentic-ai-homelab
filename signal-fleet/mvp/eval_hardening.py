"""Deterministic end-to-end eval for the flood-hardening (EVAL.md companion).

score.py measures the LLM *triager's* judgement (probabilistic, k>=3). This measures
the DETERMINISTIC hardening that guards against the 2026-08 escalation flood — the
operational classifier (#5), the fail-closed path (#2), and test-suppression (#7).
No LLM, no cost, no flakes: same input -> same verdict, every run. It replays a
VERSIONED dataset of the real (scrubbed) flood signals and asserts behavior, so the
incident that happened becomes the test that guarantees it can't silently recur.

  python3 eval_hardening.py            # run all cases, exit non-zero on any failure

Cultivate: when a new incident class appears, add a case to
reference-hardening/hardening-cases.json with its real (scrubbed) strings + expected
behavior. This file needs no change — the dataset drives it.
"""
import json
import os
import sys

# self-contained + portable: this eval is DETERMINISTIC (no LLM, no network). Force
# observ off BEFORE importing triage so an operational-gate dismissal never tries to
# push telemetry — the eval then runs anywhere (CI, a fresh clone) with no creds.
os.environ.setdefault("SF_OBSERV_DISABLED", "1")

import sources
import triage

DATASET = os.path.join(os.path.dirname(__file__), "..", "reference-hardening",
                       "hardening-cases.json")


def _check(case):
    """Return (passed, detail). Deterministic — routes by case kind."""
    kind = case["kind"]
    sig = case["signal"]
    exp = case["expect"]

    if kind == "test-suppression":
        # #7 — suppressed at ingestion, before triage (holds even if triager is down)
        got = sources._is_test_signal(sig.get("alertname"), sig.get("summary"),
                                      (sig.get("labels") or {}).get("run_id"))
        want = exp["suppressed"]
        return got == want, f"suppressed={got} (want {want})"

    if kind == "negative-control":
        # the operational gate MUST NOT classify a real defect as operational
        got = triage.operational_class(sig)
        return got == exp["operational_class"], f"operational_class={got!r} (want {exp['operational_class']!r})"

    if kind == "operational":
        # #5 — the operational gate dismisses (no LLM) and tags the class
        cls = triage.operational_class(sig)
        disp = triage.triage(sig)  # goes through the gate; no LLM for operational
        d = disp.get("disposition")
        got_cls = (disp.get("_meta") or {}).get("operational_class")
        ok = (d == exp["disposition"] and cls == exp["operational_class"]
              and got_cls == exp["operational_class"])
        return ok, f"disposition={d} class={got_cls!r} (want {exp['disposition']}/{exp['operational_class']!r})"

    return False, f"unknown case kind {kind!r}"


def main():
    data = json.load(open(DATASET))
    cases = data["cases"]
    print(f"hardening eval — {len(cases)} cases (deterministic, no LLM)\n")
    fails = 0
    by_kind = {}
    for c in cases:
        passed, detail = _check(c)
        by_kind.setdefault(c["kind"], [0, 0])
        by_kind[c["kind"]][0] += passed
        by_kind[c["kind"]][1] += 1
        if not passed:
            fails += 1
        print(f"  {'PASS' if passed else 'FAIL'}  [{c['kind']:16}] {c['id']:26} {detail}")
    print("\n  by kind: " + " · ".join(f"{k} {v[0]}/{v[1]}" for k, v in sorted(by_kind.items())))
    print(f"\n{'ALL PASS' if not fails else str(fails) + ' FAILURE(S)'} "
          f"({len(cases) - fails}/{len(cases)})")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
