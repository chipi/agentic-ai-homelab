# fleetd — build, deploy, operate (Mac mini)

The fleet supervisor ([RFC-0004](../rfc/RFC-0004-fleetd-supervisor.md),
tech rationale [ADR-0008](../adr/ADR-0008-fleet-daemon-tech-and-framework-non-adoption.md))
as an operable service. Everything below is a `make` target in `fleetd/` —
one-liners with explicit PASS/FAIL, no Go knowledge needed.

## The surface

| Command | What it does |
|---|---|
| `make vet build` | vet + build with the git sha stamped into the binary (`fleetd <sha>` in logs + a `version` label on metrics — "what runs on the mini" is always answerable) |
| `make smoke` | end-to-end local check: cycle-run, spend accounting, STOP flag, budget pause (deploy/smoke.sh) |
| `make deploy` | keeps the previous binary as `fleetd.prev`, ships binary+config+plist, (re)loads launchd. **Ask the operator before running — deploys are shared-state.** |
| `make rollback` | swaps `fleetd.prev` back and reloads — the 30-second undo |
| `make status` / `make logs` | launchd state + log tail from the mini |
| `make stop` / `make start` | stop = STOP flags for both fleets **and** unload; start = flags removed + load |

## Config & secrets

- `fleetd/deploy/fleetd.json` is the deployed config — **secrets-free by
  construction**; each fleet block points at a mini-local `env_file`
  (`~/signal-fleet/fleet.env`, sops-managed per ADR-0006 conventions).
- Both fleet blocks ship `enabled: false` — deploying the daemon is safe
  and separate from enabling a fleet. Enabling = config edit + `make deploy`
  (a deliberate, auditable act per rollout-plan stage).
- `stage` (`shadow | propose | live`) is passed to cycles as `FLEETD_STAGE`;
  cycles in `shadow` must take no actions (the cycle contract in
  `fleetd/README.md`).

## Observability of the daemon itself

- **Metrics** (VictoriaMetrics, `service=fleetd, environment=operations`):
  `fleetd_cycle{fleet,outcome,stage,version}`, `fleetd_cycle_seconds`,
  `fleetd_spend_day`.
- **Logs**: stdout → `~/fleetd/fleetd.log` (launchd) **and** shipped
  directly to VictoriaLogs (best-effort, batched, drops rather than blocks)
  — query `service:fleetd` in Grafana.
- **Alert**: `fleetd-cycle-failing` (provisioned in
  `infra/observability/.../alerting/rules.yaml`) pages on any
  error/timeout cycle outcome; budget-pause skips are deliberately not
  alerts (the guard working is not an incident).
- **Correlation**: every cycle gets `FLEETD_CYCLE_ID` in its environment;
  fleet cores stamp it into their ledgers → a Grafana log line joins to the
  exact decisions of that cycle. No tracing infra (see RFC-0004 non-goals).
- **Errors→GlitchTip**: phase-2, only if error volume wants Sentry-grade
  grouping (would be fleetd's first dependency — ADR-0008 governs).

## Rollback + kill in one breath

`make stop` (flags + unload) is the fleet-wide kill. `make rollback` is the
bad-deploy undo. The OpenRouter per-key spend limit (rollout plan, shared
foundations) remains the money backstop underneath both.
