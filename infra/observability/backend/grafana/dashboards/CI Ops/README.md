# CI Ops — Grafana folder

CI/CD and ops-runner health from GitHub Actions. GitHub runners are ephemeral
and ship no telemetry on their own; the prod workflows that **already join the
tailnet** push discrete `ops_event/v1` records to **VictoriaLogs** (`:9428`), so
runner-side deploy/backup health sits on one Grafana pane next to app telemetry.

Source of the pipeline lives in `podcast_scraper` / `chipi/infra`
(ADR-119, vendor-neutral event emission); this folder is the homelab-side view,
provisioned as code.

## Boards

| Board | uid | Goal | Datasource | Key panels |
|---|---|---|---|---|
| **CI / Ops — GitHub Actions** | `podcast-ci-ops-overview` | Deploy + backup outcomes from prod workflows | VictoriaLogs (victoriametrics-logs-datasource) | Deploys / Deploy failures / Backups / Avg deploy duration (stat); Ops event volume by type + Deploys by status over time (timeseries); Event breakdown (type × surface × status) table; recent ops events tail. Var: `$env` (Env). |
| **CI / Ops — DORA metrics** | `podcast-ci-ops-dora` | The four DORA metrics + CI health, from Tier-1 deploys + Tier-2 CI runs | VictoriaLogs (victoriametrics-logs-datasource) | Deploy frequency, change failures, CI failures, flaky runs (`attempt>1`) (stat); avg CI queue/duration + avg deploy duration + drift/drill failures (stat); deploys-by-status + CI-runs-by-status (timeseries); CI-by-workflow×status + drift/drill-outcomes (table); recent failures tail. No `$env` filter — spans prod deploys + CI. |
| **CI runners — the X3 fleet** | `ci-runners` | The 16 GitHub Actions runners on the X3 (RFC-0011): online/busy, queue, job slots, the 12-core / 48 GB slice, disk budgets, alerts, sync log | VictoriaMetrics (`gh_*`, `x3_ci_*`, `docker_engine_bytes`), VictoriaLogs (`service="ci-runner-sync"`, shipped by the X3's Alloy) | Runners online/busy, jobs queued, longest queue wait, slots held/total, jobs waiting for a slot, oldest slot wait, collector age (stat); runners offline/idle/busy (state timeline); busy share per repo, queue wait by repo, jobs and minutes 24h; CPU vs quota, CPU wait share vs 0.1, throttled share, memory vs high/max, memory pressure, OOM and limit events; cache and engine per runner vs budget, images, disk free, X3 dev engine, dev-engine-prune age; CI alert lists; sync log tail and restarts/FAIL/freed/offline. Vars: `$repo`, `$runner`. Links: the Hub's CI tab, CI / Ops overview. |

## The `ops_event/v1` schema (what the panels query)

One JSON object per event, `POST http://homelab:9428/insert/jsonline`
(tailnet-only, no token — the network is the auth):

- **Stream fields** (low cardinality): `app`, `env`, `event_type`.
- Searchable fields: `status`, `surface`, `duration_ms`, `sha`, `dry_run`,
  `triggered_by`, `_msg`. Numbers are stored as strings; LogsQL still does
  numeric ranges (`duration_ms:>60000`) and `stats avg(duration_ms)`.

### Tier-1 event types (push, from tailnet-joined workflows)

| workflow | `event_type` | notable fields |
|---|---|---|
| deploy-prod | `deploy` | status, surface=operator, duration_ms, sha, triggered_by |
| deploy-player | `deploy` | status, surface=player, triggered_by |
| backup-corpus-prod | `backup` | status, surface=corpus, dry_run, triggered_by |
| backup-player-appdata-prod | `backup` | status, surface=player-appdata, dry_run, triggered_by |

Tier-2 (`ci_run` / `drift` / `drill`, pulled from the GitHub Actions API by the
homelab DORA poller) feed the same schema and land here too — see
[`../../../../ci-ops-poller/README.md`](../../../../ci-ops-poller/README.md).

## Notes

- **Datasource:** VictoriaLogs (`victorialogs`), LogsQL, for the two `ops_event` boards; the `ci-runners` board adds VictoriaMetrics.
- **Provisioning:** auto-loads into the **CI Ops** Grafana folder within 30s
  (`../provisioning/dashboards/dashboards.yml`, `foldersFromFilesStructure`).
  Persists in git; `allowUiUpdates: true` allows UI tweaks — export back to JSON
  to keep them.
- **Emit contract (upstream):**
  `podcast_scraper:infra/observability/github-actions/README.md`;
  emitter `podcast_scraper:scripts/ops/emit_ops_event.sh`.

See parent [`../README.md`](../README.md) for the datasource/provisioning model.
