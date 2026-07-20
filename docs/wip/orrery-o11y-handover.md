# Handover — orrery observability on the self-hosted stack

**For:** the orrery agent. **Goal:** move orrery's observability off Grafana Cloud
onto the self-hosted stack (VictoriaMetrics/VictoriaLogs/VictoriaTraces + Grafana
+ GlitchTip on the DGX, tailnet-only), following the same **emit-open-formats /
ship-pluggably** architecture the podcast app uses
(`podcast_scraper-infra` ADR-119; guide `docs/guides/OBSERVABILITY_ARCHITECTURE.md`).

Orrery **goes public first**, so this is the priority. Keep it **minimal** — the
VPS is small; a handful of focused dashboards, not dozens.

## Signal taxonomy (same as podcast — swap the vendor, not the app)

| Signal | Orrery emits | Backend | Ship |
| --- | --- | --- | --- |
| Metrics | *(none yet)* — nginx has no exporter | VictoriaMetrics | nginx-prometheus-exporter sidecar (future) |
| Logs | nginx access/error + pipeline-runner stdout | VictoriaLogs | orrery's grafana-agent (repoint) → or fold into the VPS Alloy |
| Traces | OTLP (when instrumented) | VictoriaTraces | OTEL SDK (same env-var pattern as podcast) |
| Errors | Sentry protocol (client-side today) | GlitchTip | Sentry SDK / browser DSN |

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
- `GRAFANA_CLOUD_LOKI_URL` → `http://100.69.49.126:9428/insert/loki/api/v1/push`
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

### 3. Errors → GlitchTip
Point orrery's Sentry DSN at the GlitchTip project (create an `orrery` project
server-side; the podcast one is `podcast`). `environment=${APP_ENV}`. See
`glitchtip-vps-error-tracking-handover.md` for the `before_send` redaction pattern
(GlitchTip stores what you send — scrub secrets/PII).

### 4. Metrics (future) — nginx exporter
Add an `nginx-prometheus-exporter` sidecar to `orrery-web` (scrapes nginx
`/stub_status`), scrape it via the collector → VictoriaMetrics. Then an
**Orrery Web — RED** dashboard (req rate / status / latency). Defer until nginx
`stub_status` is enabled.

### 5. Traces (future) — OTEL
Same env-var pattern as podcast: `opentelemetry-instrument` (or the Node OTEL SDK)
→ `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=http://100.69.49.126:10428/insert/opentelemetry/v1/traces`,
`OTEL_SERVICE_NAME=orrery-web`, `deployment.environment=${APP_ENV}`. See
`podcast-otel-traces-handover.md`.

## Verify (tailnet)

```sh
curl -m5 -o /dev/null -w "%{http_code}\n" http://100.69.49.126:9428/health   # VL
curl -sG "http://100.69.49.126:9428/select/logsql/query" \
  --data-urlencode "query=app:orrery AND _time:15m | stats by (surface) count()"
```
Then Grafana → the `orrery` folder → the two dashboards populate; filter by `env`.

## Keep-lean guardrails (small server)

- 2 orrery dashboards to start (Web, Pipelines); deep-dives via Explore.
- One collector if possible (VPS Alloy) rather than a second agent.
- No high-cardinality labels; short retention (align with the VM/VL backend).
