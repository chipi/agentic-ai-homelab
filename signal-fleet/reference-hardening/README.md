# reference-hardening/ — deterministic flood-hardening eval dataset

A **versioned, reproducible end-to-end eval** for the deterministic hardening that
guards against the 2026-08 escalation flood. Companion to `EVAL.md` /`score.py`
(which measure the *LLM triager's* judgement, probabilistically); this measures the
**deterministic** guards — the operational classifier (#5), fail-closed (#2), and
test-suppression (#7) — so the same input yields the same verdict every run.

> The incident that happened, turned into the test that guarantees it can't silently
> recur. Root-cause + design: [`docs/wip/signal-fleet-flood-hardening.md`](../../docs/wip/signal-fleet-flood-hardening.md).

## Run

```sh
python3 mvp/eval_hardening.py     # deterministic, no LLM, no creds — runs anywhere
```

Exits non-zero on any failure (wire it into a pre-deploy / CI gate). It sets
`SF_OBSERV_DISABLED=1` itself, so it never touches the live backend.

## The dataset — `hardening-cases.json`

An array of `cases`, each a real (scrubbed) production signal + its expected
behavior. Three kinds:

| kind | asserts | via |
|---|---|---|
| `operational` | cost-cap / provider-budget / provider-fallback → **dismiss** (no ticket), tagged with the class | `triage.triage()` (the gate) |
| `negative-control` | a genuine defect is **NOT** swallowed by the gate | `triage.operational_class()` is `None` |
| `test-suppression` | `agentE2E*`/synthetic suppressed; real signals not | `sources._is_test_signal()` |

Strings are the **real error titles** from the flood (chipi/podcast_scraper
#1734–#1784), **scrubbed** — no secrets/PII (`mvp/scrub.py`).

## Cultivate it (the point — this grows with the fleet)

When a new incident class appears, or the hardening evolves, **add a case** — no code
change needed, the dataset drives the runner:

1. Grab the real signal's strings (alertname/summary/labels). Run them through the
   scrubber if they carry anything sensitive: `python3 mvp/scrub.py <file>`.
2. Append a `case` with `kind`, the `signal`, the `expect`, and a `provenance` line
   pointing at the source incident/issue.
3. `python3 mvp/eval_hardening.py` → it must stay green (add the behavior first if the
   case is a new guard).

Keep negative controls in step with new operational patterns — every widening of the
operational regex needs a real-defect control proving it didn't start over-dismissing.
