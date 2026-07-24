# Podcast Player — Grafana folder

Observability for the **consumer podcast player** (public app) on the prod-podcast VPS. This folder is log-based — panels query VictoriaLogs (`instance:prod-podcast`), not Prometheus metrics. The player-api is not scraped as a metrics target.

## Boards

| Board (uid) | Goal | Datasource | Key panels / templating |
|---|---|---|---|
| `overview.json` (podcast-player-overview) | Event counts, LLM cost, volume over time, live logs | VictoriaLogs | App events ($surface) · LLM cost (24h, pipeline) · App event volume over time ($surface) · App events ($surface) — tail. Var: `$surface` (All / Player / Operator / Pipeline) |

## Notes

- **Log-based, not metrics.** Queries event_type, estimated_cost_usd, and job labels in VictoriaLogs. No Prometheus time-series.
- **Source of truth**: `podcast_scraper-infra` repo. This copy is synced so Grafana provisioning reads it locally.
- **Provisioning**: Auto-load into the Homelab folder within 30s (see `../provisioning/dashboards/dashboards.yml`).
- **Further context**: `../README.md`
