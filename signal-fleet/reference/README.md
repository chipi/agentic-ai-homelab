# reference/ — frozen eval fixtures (EVAL.md §4)

> **Superseded for measuring the triager (2026-11-05).** The fleet's decisions are now measured in eval-harness on
> real production decisions with the operator's labels (Hugging Face `chipi-nbgd/orrery-triage`, revisions `v1`
> and `v2`; built by `../datasets/`): see `EVAL-LESSONS-0.6.0.md` section 7 and the runbook's §5. These 23
> curated fixtures stay as a small hand-made set; `score.py` still runs them.

Frozen `{signal, evidence, ground_truth}` fixtures the scorer replays k times to
measure the triager. `mvp/freeze.py` builds them; `mvp/score.py` runs them.

**Ground truth is the operator's *independent* label — the human oracle — never
the triager's.** The model is the thing under test; if it labels its own exam the
eval is circular. So freeze.py leaves `ground_truth` blank for the operator.

## Status (data hygiene) — COMMITTED + SCRUBBED (operator-approved 2026-08-20)
These fixtures **are now versioned here** (previously mini-only). The operator
approved committing them to the public repo *after a thorough scrub*. Every fixture
passes through `mvp/scrub.py` — a two-tier reproducible scrubber: **secrets**
hard-redacted (with a `--scan` gate that fails on any), **identifiers** (real
domains, operator paths/handle, host topology, git shas, long hashes) mapped to
stable synthetic equivalents that preserve shape + semantics, so the triager's
dispositions are unchanged. `freeze.py` applies it automatically, so future fixtures
are auto-scrubbed. Validated: 0 leaks, `score.py` replays them without table-miss.

See also the deterministic hardening eval:
[`../reference-hardening/`](../reference-hardening/README.md).

## Label vocabulary
- `disposition`: `dismiss` | `file` | `escalate`
- `work_type` (only if `file`): `bug` | `config-enhancement`

## Flow
1. `python3 freeze.py` → fixtures (on the mini; deterministic, no LLM).
2. **Operator fills each fixture's `ground_truth`** independently of the model.
3. `SF_TRIAGE_MODEL=<model> python3 score.py <k>` → **false-dismiss rate** ⭐ +
   escalate-rate + consistency + confusion, attributed to the model + prompt hash.
   (The model sweep of EVAL.md §3.6 has since run in eval-harness: no model beat production's.)

## The frozen set (23 fixtures; the first 10 frozen 2026-07-24)
Spans the disposition space + the adversarial cases:
- real client defects: `ORRERY-5/6` (null-deref), `ORRERY-8` (dynamic-import),
  `ORRERY-A` (sw.js load)
- real backend defect: `PODCAST-4` (span-export timeout, n=42)
- noise/test: `ORRERY-D` (delete-me), `ORRERY-DEV-1` (`x`), `PLAYER-3` (test event)
- consistency pair: `PLAYER-4` vs `PLAYER-5` (same `SyntaxError`)
- miscalibrated alert: `grafana-orrery-stale`
- added later: `ORRERY-E`, `ORRERY-STAGING-1..4` (STAGING-2/3/4 still have no `ground_truth.disposition`),
  `PODCAST-6`, `PODCAST-7`, `PODCAST-ANCHOR-1`, `PODCAST-CARGO-1`, `PODCAST-DEEPGRAM-1`, `PODCAST-INSPECT-1`,
  `PODCAST-RECOVER-1`

**Missing (needs seeding — EVAL.md §3.2):** real defects from Fleet-1's bug set at
`<fix>^`, for the executable File-quality class. The current File-class members are
observed errors, not oracle-backed.
