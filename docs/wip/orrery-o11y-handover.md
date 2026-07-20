# Handover — orrery observability on the self-hosted stack

**For:** the orrery agent. **Goal:** move orrery's observability off Grafana Cloud
onto the self-hosted stack (VictoriaMetrics/VictoriaLogs/VictoriaTraces + Grafana
+ GlitchTip on the homelab mini, tailnet-only), following the same **emit-open-formats /
ship-pluggably** architecture the podcast app uses
(`podcast_scraper-infra` ADR-119; guide `docs/guides/OBSERVABILITY_ARCHITECTURE.md`).

Orrery **goes public first**, so this is the priority. Keep it **minimal** — the
VPS is small; a handful of focused dashboards, not dozens.

## Prod o11y settings — the complete set

Backend = the **homelab** Mac mini (permanent; tailnet name `homelab`, resolves
tailnet-wide). Orrery has its **own** GlitchTip project (id `2`); moss + the podcast
app share project `1`. Set these in orrery's prod env:

```env
# Logs → VictoriaLogs (orrery grafana-agent / collector)
GRAFANA_CLOUD_LOKI_URL=http://homelab:9428/insert/loki/api/v1/push
#   + labels: app=orrery, env=${APP_ENV}, surface=web|pipeline

# Errors → NONE for orrery. No GlitchTip (decided) — see note below.

# Traces → VictoriaTraces (when instrumented)
OTEL_TRACES_EXPORTER=otlp
OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=http://homelab:10428/insert/opentelemetry/v1/traces
OTEL_SERVICE_NAME=orrery-web
OTEL_RESOURCE_ATTRIBUTES=deployment.environment=${APP_ENV}

# Metrics → VictoriaMetrics (when nginx exporter added)
REMOTE_WRITE_URL=http://homelab:8428/api/v1/write   # if orrery runs its own collector
#   (or let the VPS Alloy scrape orrery's nginx-exporter — one collector is leaner)

# Dashboards push (orrery Grafana folder)
GRAFANA=http://homelab:3000
GRAFANA_TOKEN=<orrery service-account token>        # own SA + `orrery` folder
```

`GRAFANA_TOKEN` is a secret — orrery's secret store, never git.

### Errors: no GlitchTip for orrery (decided)
Orrery is a **static site**, so its Sentry would run **in the browser** — but
`homelab:8090` is **tailnet-only**, so public visitors' browsers can't reach it.
Rather than expose a public GlitchTip ingest just for orrery, the decision is
**no GlitchTip for orrery**. Its o11y is **logs + metrics + traces**, all shipped
server/collector-side over the tailnet — none of which have this problem. The
pre-created GlitchTip project `2` is therefore **unused** (podcast + moss keep
project `1`); delete it or leave it idle. Revisit only if orrery later gains a
server-side layer, or you decide public client-error capture is worth an edge route.

## Signal taxonomy (same as podcast — swap the vendor, not the app)

| Signal | Orrery emits | Backend | Ship |
| --- | --- | --- | --- |
| Metrics | *(none yet)* — nginx has no exporter | VictoriaMetrics | nginx-prometheus-exporter sidecar (future) |
| Logs | nginx access/error + pipeline-runner stdout | VictoriaLogs | orrery's grafana-agent (repoint) → or fold into the VPS Alloy |
| Traces | OTLP (when instrumented) | VictoriaTraces | OTEL SDK (same env-var pattern as podcast) |
| Errors | *(none — no GlitchTip; static site's browser can't reach the tailnet backend)* | — | — |

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

### 4. Metrics (future) — nginx exporter
Add an `nginx-prometheus-exporter` sidecar to `orrery-web` (scrapes nginx
`/stub_status`), scrape it via the collector → VictoriaMetrics. Then an
**Orrery Web — RED** dashboard (req rate / status / latency). Defer until nginx
`stub_status` is enabled.

### 5. Traces (future) — OTEL
Same env-var pattern as podcast: `opentelemetry-instrument` (or the Node OTEL SDK)
→ `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=http://homelab:10428/insert/opentelemetry/v1/traces`,
`OTEL_SERVICE_NAME=orrery-web`, `deployment.environment=${APP_ENV}`. See
`podcast-otel-traces-handover.md`.

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
