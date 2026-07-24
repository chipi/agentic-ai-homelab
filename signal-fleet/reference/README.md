# reference/ — frozen eval fixtures (EVAL.md §4)

Frozen `{signal, evidence, ground_truth}` fixtures the scorer replays k times to
measure the triager. `mvp/freeze.py` builds them; `mvp/score.py` runs them.

**Ground truth is the operator's *independent* label — the human oracle — never
the triager's.** The model is the thing under test; if it labels its own exam the
eval is circular. So freeze.py leaves `ground_truth` blank for the operator.

## Status (data hygiene)
Fixtures live on the homelab mini (`~/signal-fleet/reference/`) — they hold real
signal evidence (IPv4-redacted by freeze.py). They are **not committed here yet**,
pending an operator decision on committing real logs. The machinery
(`mvp/freeze.py`, `mvp/score.py`) is version-controlled.

## Label vocabulary
- `disposition`: `dismiss` | `file` | `escalate`
- `work_type` (only if `file`): `bug` | `config-enhancement`

## Flow
1. `python3 freeze.py` → fixtures (on the mini; deterministic, no LLM).
2. **Operator fills each fixture's `ground_truth`** independently of the model.
3. `SF_TRIAGE_MODEL=<model> python3 score.py <k>` → **false-dismiss rate** ⭐ +
   escalate-rate + consistency + confusion, attributed to the model + prompt hash.
   Sweep models per EVAL.md §3.6.

## The current frozen set (2026-07-24)
Spans the disposition space + the adversarial cases:
- real client defects: `ORRERY-5/6` (null-deref), `ORRERY-8` (dynamic-import),
  `ORRERY-A` (sw.js load)
- real backend defect: `PODCAST-4` (span-export timeout, n=42)
- noise/test: `ORRERY-D` (delete-me), `ORRERY-DEV-1` (`x`), `PLAYER-3` (test event)
- consistency pair: `PLAYER-4` vs `PLAYER-5` (same `SyntaxError`)
- miscalibrated alert: `grafana-orrery-stale`

**Missing (needs seeding — EVAL.md §3.2):** real defects from Fleet-1's bug set at
`<fix>^`, for the executable File-quality class. The current File-class members are
observed errors, not oracle-backed.
