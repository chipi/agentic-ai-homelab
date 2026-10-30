# Production Infra — Grafana folder

Boards about the prod-podcast VPS that homelab owns: the outside-in view and the provider.

## Boards

| Board | uid | Goal | Datasource |
|---|---|---|---|
| **Prod uptime** | `prod-uptime` | Outside-in availability of the prod endpoints (probes from the mini every minute) and Cloudflare's own counts for every visitor | VictoriaMetrics |
| **Hetzner status bulletins** | `hetzner-status` | status.hetzner.com bulletins correlated with prod's datacenters | VictoriaMetrics, VictoriaLogs |

## Moved to chipi/infra (2026-10)

The prod box's own boards, **Host Overview** (`prod-infra-host-overview`), **Containers**
(`prod-infra-containers`) and **Edge Security** (`prod-infra-edge-security`), moved to
chipi/infra `config/grafana/dashboards/o11y/` with their uids unchanged, and are uploaded by its
`grafana_sync` into the `o11y` folder (the homelab app move; D-0014). Links by uid keep working.

## Provisioning

These JSONs load into the **Production Infra** Grafana folder within 30 s (`../provisioning/dashboards/dashboards.yml`).
`allowUiUpdates: true` lets the UI change a board, but export it back to JSON to keep the change.

See [`../README.md`](../README.md) for the datasource setup.
