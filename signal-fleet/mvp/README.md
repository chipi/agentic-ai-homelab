# signal-fleet/mvp — the triage fleet's cycle code

The code fleetd runs every 10 minutes on the Mac mini (`python3 orchestrator.py --cycle --limit 10
--no-dry-run`, from the git checkout). The directory keeps its MVP name; the code has been the live
fleet since August 2026.

- **How it works and why:** [Triage fleet guide](../../docs/signal-fleet-guide.md).
- **How to run, deploy, review and change it:** [Triage fleet runbook](../../docs/recipes/signal-fleet-runbook.md).

Stdlib-only Python (3.9 on the mini). No secrets in the repo: credentials come from
`~/signal-fleet/fleet-gateway.env` on the host; state lives in `~/signal-fleet/` (ledgers, queue).

## Files

| File | Role |
|---|---|
| `orchestrator.py` | one cycle: Grafana pass, GlitchTip pass, triager-down, inbox, stale pass, GitHub → GlitchTip sync, spend |
| `sources.py` | read firing Grafana alerts and unresolved GlitchTip issues; normalize to signals |
| `correlate.py` | probe evidence for the triager: VictoriaLogs, VictoriaMetrics, VictoriaTraces (by the OTel trace id) |
| `triage.py` | deterministic gates (operational states, intent gate), then the LLM investigation and decision |
| `actions.py` | the dispositions ledger, idempotency, recurrence rows |
| `filing.py` | the filed ledger and the GitHub decision tree (dedup keys, storm groups, rollups, duplicates, reused short ids) |
| `glitchtip_sync.py` | mirror the operator's GitHub closes onto the fleet-filed GlitchTip issues (#100) |
| `stale.py` | the daily "looks resolved?" nudge |
| `inbox.py` | operator-inbox metrics; ships audit events to VictoriaLogs |
| `observ.py` | metrics and the Langfuse trace per triage |
| `config.py`, `http_util.py`, `scrub.py`, `freeze.py` | settings from env, HTTP helpers, scrubbing and freezing corpora |
| `probe.py`, `probes.py`, `triage_probe.py`, `score.py` | live probes and the triager scorer over frozen fixtures |
| `eval_*.py`, `test_units.py` | the deterministic gates `deploy/deploy.sh` runs; the runbook's §5 lists what each guards |

## Run by hand (on the mini)

```sh
cd ~/agentic-ai-homelab/signal-fleet/mvp
set -a; . ~/signal-fleet/fleet-gateway.env; set +a
python3 glitchtip_sync.py                           # the sync's dry run: reads only
```

A cycle by hand is not read-only, even without `--no-dry-run`: it calls the LLM (cost),
appends to the dispositions ledger and can queue proposals. To push one signal through, follow the runbook's §3
("Run one signal through by hand"), right after a fleetd cycle ends.
