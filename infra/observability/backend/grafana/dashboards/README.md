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

Only modern (React-panel) dashboards are vendored. The old DCGM (12239) and
cAdvisor (893) dashboards were **dropped** — they use Angular panels
(`graph`/`singlestat`), which Grafana 11 disables by default, so they render
broken. Replaced by the authored ones below.

## Authored (modern React panels)

| File | Datasource | Covers |
|---|---|---|
| `gpu-dcgm.json` | VictoriaMetrics | GPU (DCGM): utilization, temp, power, SM clock, mem-copy util, XID errors. Var `$gpu`. |
| `containers-cadvisor.json` | VictoriaMetrics | Containers (cAdvisor): CPU/mem/net per Docker cgroup. Names show as short Docker IDs (cAdvisor isn't resolving Docker metadata here — `name` label absent). |
| `logs-overview.json` | VictoriaLogs (`victoriametrics-logs-datasource`) | Generic log browser: total/error counts, volume by container, errors-over-time, live log stream. Vars: `$container` (multi, from `field_values`), `$search`. |

Authored dashboards are hand-built (or replace an Angular original). Query
shapes were validated against the live datasources and each was import-tested
into Grafana before commit. For logs: `stats`/`statsRange` want a `| stats …`
pipe in the LogsQL `expr`; `instant` returns raw lines for a `logs` panel.

All three were processed on vendor-in: the `${DS_PROMETHEUS}` datasource input
was replaced with our provisioned datasource uid `victoriametrics`, and the
`__inputs`/`__requires` import prompts stripped so file-provisioning loads them
without interaction.

To add more: download JSON from grafana.com, replace any `${DS_*}` datasource
placeholder with `victoriametrics`, drop it here.
