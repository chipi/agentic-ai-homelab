# Handover — orrery observability on the self-hosted stack

**For:** the orrery agent. **Goal:** move orrery's observability off Grafana Cloud
onto the self-hosted stack (VictoriaMetrics/VictoriaLogs/VictoriaTraces + Grafana
+ GlitchTip on the homelab mini, tailnet-only), following the same **emit-open-formats /
ship-pluggably** architecture the podcast app uses
(`podcast_scraper-infra` ADR-119; guide `docs/guides/OBSERVABILITY_ARCHITECTURE.md`).

Orrery **goes public first**, so this is the priority. Keep it **minimal** — the
VPS is small; a handful of focused dashboards, not dozens.

## Prod o11y settings — orrery is LOGS-ONLY

Orrery is a **static site** — so its observability is **logs only**. No metrics, no
errors, no traces integration (decided): a static nginx site has no server to emit
traces or server-side errors, and client-side (browser) errors can't reach the
tailnet-only backend anyway. Backend = the **homelab** Mac mini (permanent; tailnet
name `homelab`). Set this in orrery's prod env:

```env
# Logs → VictoriaLogs (orrery grafana-agent / collector) — the ONLY o11y integration
GRAFANA_CLOUD_LOKI_URL=http://homelab:9428/insert/loki/api/v1/push
#   + labels: app=orrery, env=${APP_ENV}, surface=web|pipeline

# Dashboards push (orrery Grafana folder) — log-based dashboards only
GRAFANA=http://homelab:3000
GRAFANA_TOKEN=<orrery service-account token>        # own SA + `orrery` folder
```

`GRAFANA_TOKEN` is a secret — orrery's secret store, never git.

### Not integrated for orrery (by decision)
- **Metrics** — none. (nginx has no exporter; a static site isn't worth one.)
- **Traces** — none. (No server → no spans.)
- **Errors** — none. No GlitchTip: a static site's Sentry runs in the browser, and
  `homelab:8090` is tailnet-only, so public visitors can't reach it; exposing a
  public ingest isn't worth it. The pre-created GlitchTip project `2` is therefore
  **unused** (podcast + moss keep project `1`) — delete it or leave it idle.

## Signal taxonomy — logs only

| Signal | Orrery | Backend | Ship |
| --- | --- | --- | --- |
| Logs | nginx access/error + pipeline-runner stdout | VictoriaLogs | orrery's grafana-agent (or fold into the VPS Alloy) |
| Metrics / Traces / Errors | *(not integrated — static site; see above)* | — | — |

## What orrery has today (from recon)

- `ops/observability/grafana-agent.yaml` — docker_sd tails `orrery-web` (nginx) +
  `orrery-pipeline-runner-*` stdout → **Grafana Cloud Loki**. Silent-by-default
  (no creds → no-op). No metrics scraping (comment: "until the future VPS RFC").
- **Dashboards already built** on the `orrery-fixes` branch:
  `ops/observability/dashboards/{orrery-web-access,orrery-pipelines}.json` +
  `import.sh` (POSTs to `/api/dashboards/db`). They query Loki — datasource uid
  `grafanacloud-logs`.
- Sentry client-side only (`src/lib/observability/sentry.ts`).
- Placeholder `orrery-edge.json` in the podcast infra repo (retire it).

## Steps (minimal, ordered)

### 1. Logs → VictoriaLogs (the immediate win, no app change)
Repoint orrery's grafana-agent Loki endpoint from Cloud to VictoriaLogs:
- `GRAFANA_CLOUD_LOKI_URL` → `http://homelab:9428/insert/loki/api/v1/push`
  (tailnet; ACL 9428 granted). No auth needed on the tailnet.
- Add labels `app=orrery`, `env=${APP_ENV}` (dev/prod), and a **`surface`** label
  (`web` vs `pipeline`) so the two orrery surfaces are differentiable — mirror the
  podcast player/operator/pipeline split.
- **Revoke** the old Cloud `glc_` token after cutover (it was exposed in the
  container env; treat as compromised).

*(Alternative: drop orrery's own agent and let the VPS Alloy
`hosts/prod-podcast/` discover `orrery-*` containers via docker_sd. One collector
is leaner on a small box — recommended if both apps share the VPS.)*

### 2. Dashboards → self-hosted Grafana
Take the `orrery-fixes` dashboards, swap the datasource uid `grafanacloud-logs`
→ **`victorialogs`**, give each a stable `uid`, and push them. Use a token from a
Grafana **service account** into an **`orrery`** folder (mirror the podcast
`podcast-deploy` SA + `VPS — Podcast` folder; ADR-117 per-tenant folder split).
Minimal set: **Orrery Web** (access/RED from nginx logs) + **Orrery Pipelines**
(runs/errors). Retire the placeholder `orrery-edge.json`.

### 3. Errors → SKIPPED (no GlitchTip for orrery)
Decided: orrery's client-side browser errors can't reach tailnet-only GlitchTip,
and a public ingest isn't worth it for a static site. Project `2` is unused. See
§"Errors: no GlitchTip for orrery" above.

### 4. Metrics / Traces / Errors — not integrated
Out of scope for orrery (static site): no metrics, no traces, no GlitchTip. See
§"Not integrated for orrery" above. Logs (steps 1–2) are the whole o11y surface.

## Verify (tailnet)

```sh
curl -m5 -o /dev/null -w "%{http_code}\n" http://homelab:9428/health   # VL
curl -sG "http://homelab:9428/select/logsql/query" \
  --data-urlencode "query=app:orrery AND _time:15m | stats by (surface) count()"
```
Then Grafana → the `orrery` folder → the two dashboards populate; filter by `env`.

## Keep-lean guardrails (small server)

- 2 orrery dashboards to start (Web, Pipelines); deep-dives via Explore.
- One collector if possible (VPS Alloy) rather than a second agent.
- No high-cardinality labels; short retention (align with the VM/VL backend).
