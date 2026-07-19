# Provisioned dashboards

Every `*.json` here auto-loads into the Grafana **Homelab** folder (see
`../provisioning/dashboards/dashboards.yml`) within 30s — no manual import.
Dashboards-as-code: they live in git, so they survive the move to the Mac mini.
`allowUiUpdates: true` lets you tweak in the UI, but export back to a file here
to persist.

## Vendored (metrics)

| File | Source (grafana.com) | Covers |
|---|---|---|
| `node-exporter-full.json` | 1860 rev45 | Host: CPU, mem, disk, net, fs, load |
| `nvidia-dcgm.json` | 12239 rev2 | GPU: util, VRAM, power, temp (DCGM) |
| `docker-cadvisor.json` | 893 rev5 | Containers: per-container CPU/mem/net |

## Authored (logs)

| File | Datasource | Covers |
|---|---|---|
| `logs-overview.json` | VictoriaLogs (`victoriametrics-logs-datasource`) | Generic log browser: total/error counts, volume by container, errors-over-time, live log stream. Vars: `$container` (multi, from `field_values`), `$search` (free-text LogsQL). |

The logs dashboard is hand-authored (no grafana.com equivalent) — query shapes
(`statsRange`/`stats`/`instant`) were validated against the live datasource. To
add log panels: `stats`/`statsRange` want a `| stats …` pipe in the LogsQL
`expr`; `instant` returns raw lines for a `logs` panel.

All three were processed on vendor-in: the `${DS_PROMETHEUS}` datasource input
was replaced with our provisioned datasource uid `victoriametrics`, and the
`__inputs`/`__requires` import prompts stripped so file-provisioning loads them
without interaction.

To add more: download JSON from grafana.com, replace any `${DS_*}` datasource
placeholder with `victoriametrics`, drop it here.
