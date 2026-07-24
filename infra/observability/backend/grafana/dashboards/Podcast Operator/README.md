# Podcast Operator — Grafana folder

Observability for the **podcast operator API** (`instance=prod-podcast, job=api`) and associated surfaces (viewer, pipeline) running on the prod-podcast VPS.

## Boards

| Board (uid) | Goal | Datasource | Key panels / vars |
|---|---|---|---|
| **Overview** (`podcast-operator-overview`) | Status snapshot + volume trends over 24h | VictoriaMetrics (prometheus) + VictoriaLogs | **Templating:** `$surface` (All/Player/Operator/Pipeline) · **Stats row:** app event count, API req/s, API 5xx rate, LLM cost (24h pipeline) · **Timeseries:** app event volume over time, API latency p50/p95 (s) · **Log tail:** live app events, filtered by surface |

## Notes

**Signals:**

- **Metrics:** API surfaces instrumented via OTel; `http_requests_total` and `http_request_duration_seconds_bucket` emit to VictoriaMetrics under service label `podcast-api`.
- **Logs:** App/pipeline logs → VictoriaLogs with fields `instance=prod-podcast`, `job={api,podcast-pipeline,podcast-search,podcast-listen,podcast-jobs}`, `event_type` (e.g. `llm_cost`), and message body. Filtered via LogsQL with field matchers and stats pipelines.

**Provisioning:** Dashboards auto-reload within 30s (see `../provisioning/dashboards/dashboards.yml`). `allowUiUpdates: true` allows UI tweaks; export back to `.json` to persist.

**Sparsity:** LLM cost panel (`event_type:llm_cost`) emits only when pipeline runs — expect zero or sparse data if pipeline is idle. Event volume filtered by `$surface` regex (`podcast-.*` etc.) will show no data if that surface produces no logs in the lookback window.
