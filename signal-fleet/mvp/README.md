# signal-fleet MVP — first vertical slice

The smallest end-to-end proof of the signal-to-action spine (SIGNALS §13.3):

```
poll (Grafana alert) → correlate (VictoriaLogs/Metrics) → triage (LLM, structured)
  → intent gate (deterministic) → act (Dismiss / File-dry-run / Escalate) → ledger
```

Stdlib-only Python. Runs on the mini (`homelab`), reads every source over
localhost/tailnet. No secrets in the repo — creds come from the deployed stack
`.env`s (see `run.sh`).

## The slice
The one signal wired: the **orrery launch-data-stale** Grafana alert. The triager
reads the correlated `orrery-data-refresh` logs and decides Dismiss (data actually
fresh → false alarm, with a config-enhancement recommendation) vs File. Verified
live 2026-07-24: it dismissed on real evidence and recommended the alert fix.

## Files
| File | Role |
|---|---|
| `config.py` | endpoints + creds from env (homelab defaults) |
| `http_util.py` | stdlib HTTP helpers |
| `sources.py` | trigger — poll Grafana Alerting; normalize to a signal |
| `correlate.py` | correlation reads — VictoriaLogs / VictoriaMetrics evidence bundle |
| `triage.py` | the triager — OpenRouter structured output + validate-retry + **deterministic intent gate** |
| `actions.py` | Dismiss / File (dry-run) / Escalate + append-only ledger + idempotency |
| `orchestrator.py` | the deterministic loop tying it together |
| `probe.py`, `triage_probe.py` | live probes for the trigger/correlate/triage halves |

## Run (on the mini)
```sh
./run.sh --synthetic          # drive with a synthetic staleness signal
./run.sh                      # act on the live alert (if firing)
```
Ledger: `~/signal-fleet/results/dispositions.tsv`.

## Reused from Fleet 1 (SIGNALS §13.4)
directAdapter structured-output + validate-retry pattern; the deterministic
intent-source gate (`triage._intent_gate`); the append-only ledger; the shared
`intent_source` vocabulary.

## NOT done (MVP boundaries)
- **File is dry-run** — real GitHub issue creation is blocked on the target-repo
  decision (SIGNALS §13.1 #3).
- **Poll is single-shot** (`run_once`) — no daemon loop / schedule yet.
- **One signal only** (orrery staleness). GlitchTip errors + trace correlation are
  Phase B.
- **Not yet TypeScript** — this prototype reuses Fleet-1 *patterns*; sharing the
  actual `src/worker` seam + GitHub App is the productionization step.
- Langfuse tracing of the triager call is not wired yet.
