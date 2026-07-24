# Provisioned dashboards

Dashboards-as-code: every `*.json` here loads into Grafana automatically (no
manual import), lives in git, and survives host moves. `allowUiUpdates: true`
lets you tweak in the UI — but **export back to a file here to persist**, or the
next provisioning reload overwrites your change.

## Folder structure = Grafana folders

Provisioning uses `foldersFromFilesStructure: true` (see
[`../provisioning/dashboards/dashboards.yml`](../provisioning/dashboards/dashboards.yml)),
so **each subdirectory below is a Grafana folder**. Drop a board JSON into the
right subdir and it appears in that folder within ~30s
(`updateIntervalSeconds: 30`).

| Folder | Covers | Per-folder doc |
|---|---|---|
| **Homelab/** | Mac mini + DGX core infra (host, GPU, containers, logs, DGX services, bug-fix fleet, orrery refresh) | [Homelab/README.md](Homelab/README.md) |
| **Production Infra/** | prod-podcast VPS — host / containers / edge security | [Production Infra/README.md](Production%20Infra/README.md) |
| **Podcast Operator/** | Operator API + viewer observability | [Podcast Operator/README.md](Podcast%20Operator/README.md) |
| **Podcast Player/** | Consumer player (log-based); source of truth is `podcast_scraper-infra`, synced here | [Podcast Player/README.md](Podcast%20Player/README.md) |

Each per-folder README states that folder's **goal** and a per-board table (what
each answers, datasource, key panels). Alerts are documented separately in
[`../provisioning/alerting/README.md`](../provisioning/alerting/README.md).

## Vendored vs authored boards

**Vendored (metrics):**

| File (folder) | Source (grafana.com) | Covers |
|---|---|---|
| `Homelab/node-exporter-full.json` | 1860 rev45 | Host: CPU, mem, disk, net, fs, load |

Only modern (React-panel) dashboards are vendored. The old DCGM (12239) and
cAdvisor (893) dashboards were **dropped** — they use Angular panels
(`graph`/`singlestat`), disabled by default in Grafana 11, so they render broken.
Replaced by authored equivalents.

**Authored (modern React panels)** — hand-built or replacing an Angular original.
Query shapes were validated against the live datasources and import-tested into
Grafana before commit. For logs: `stats`/`statsRange` want a `| stats …` pipe in
the LogsQL `expr`; `instant` returns raw lines for a `logs` panel. The
per-folder READMEs list every authored board.

## Datasources

Boards reference the provisioned datasource uids: **`victoriametrics`**
(Prometheus-compatible, metrics), **VictoriaLogs**
(`victoriametrics-logs-datasource`), **VictoriaTraces**. On vendor-in, replace
any `${DS_*}` datasource input with `victoriametrics` and strip the
`__inputs`/`__requires` import prompts so file-provisioning loads without
interaction.

## Adding a board

1. Build/export the JSON (or download from grafana.com).
2. Replace any `${DS_*}` datasource placeholder with the provisioned uid
   (`victoriametrics`), strip `__inputs`/`__requires`.
3. Drop it in the **subdir for its Grafana folder** (create a new subdir for a
   new folder), commit. It loads within ~30s. Update that folder's README.
