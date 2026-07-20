# Observability backend migration runbook — DGX → homelab

The o11y backend (VictoriaMetrics/Logs/Traces + Grafana + GlitchTip + Langfuse)
runs on the DGX as a **stopgap**. It moves to the always-on Mac mini (`homelab`).
The DGX keeps only its **collector**.

**The design that makes this cheap:** every sender→backend reference comes from an
**env var**, so the cutover is a per-host `.env` flip — **no config or code edits**.
`homelab` is a Tailscale device name (free tier: no custom DNS) → it resolves
tailnet-wide as `homelab` / `homelab.<tailnet>.ts.net` once the mini owns the name
(it does). All the values below currently point at the DGX (`dgx-llm-1`).

## Preconditions (before flipping anything)

1. Backend stack is **up + healthy on homelab** — stand it up from
   `infra/observability/backend/` with the backend's own `.env`:
   set `VM_LISTEN` / `VLOGS_LISTEN` / `VTRACES_LISTEN` / `GRAFANA_LISTEN` to
   **homelab's tailnet IP** (these are the backend's *own bind* addresses, not
   sender refs). Same for the `infra/glitchtip/` and `infra/langfuse/` stacks.
2. Data: either migrate the named volumes (`vm-data`, `vlogs-data`, `vt-data`,
   `grafana-data`, GlitchTip/Langfuse Postgres) from the DGX, or start fresh
   (short retention makes a clean start cheap).
3. `ping homelab` resolves from every sender host (DGX, prod-podcast VPS,
   workstation).

## The flip-set — per host, per `.env`

Each row: flip the value from the DGX form to the homelab form, then restart the
listed process. Nothing else changes.

All paths verified 2026-07-20: DGX self-collector `.env` (on-host), moss compose
(on-host), prod-podcast collector `.env` (its README), app `.env` (`deploy.sh` sets
`REPO_DIR=/srv/podcast-scraper`, stages `.env` there). Access to the VPS is
`ssh -i ~/.ssh/podcast_prod_operator deploy@prod-podcast`.

### Host: DGX — self-collector (`~/agentic-ai-homelab/infra/observability/.env`)
| Key | → homelab | Restart |
|---|---|---|
| `REMOTE_WRITE_URL` | `http://homelab:8428/api/v1/write` | `docker compose up -d` (in `infra/observability/`) |
| `LOGS_WRITE_URL` | `http://homelab:9428/insert/loki/api/v1/push` | ↑ same |

### Host: prod-podcast VPS — collector (`/opt/vps-observability/.env`)
| Key | → homelab | Restart |
|---|---|---|
| `REMOTE_WRITE_URL` | `http://homelab:8428/api/v1/write` | restart the Alloy collector |
| `LOGS_WRITE_URL` | `http://homelab:9428/insert/loki/api/v1/push` | ↑ same |

### Host: prod-podcast VPS — podcast app (`/srv/podcast-scraper/.env`, deploy-staged)
| Key | → homelab | Restart |
|---|---|---|
| `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT` | `http://homelab:10428/insert/opentelemetry/v1/traces` | redeploy app stack |
| `PODCAST_SENTRY_DSN_API` | host part → `homelab:8090` | ↑ same |
| `PODCAST_SENTRY_DSN_PIPELINE` | host part → `homelab:8090` | ↑ same |

### Host: DGX — moss server (`/opt/moss-server/docker-compose.yml`, converge-managed)
| Key | → homelab | Restart |
|---|---|---|
| `GLITCHTIP_DSN` | host part → `homelab:8090` | redeploy moss (converge) |

### Host: backend (homelab) — Grafana alert channel (`infra/observability/backend/.env`)
| Key | → homelab | Restart |
|---|---|---|
| `ALERT_GLITCHTIP_WEBHOOK_URL` | `http://homelab:8090/api/.../webhook` | `docker compose up -d grafana` |

### Host: workstation — operator tooling (podcast repo local `.env`)
| Key | → homelab | Used by |
|---|---|---|
| `GRAFANA_URL` | `http://homelab:3000` | `scripts/ops/push-grafana-dashboards.sh` |
| `PODCAST_OBS_*` (if self-hosted) | homelab endpoints | `podcast_obs` control-plane CLI |

## What does NOT change (moves *with* the backend)

- **Grafana provisioned datasources** — they use the internal compose bridge
  (`http://victoriametrics:8428`, `http://victorialogs:9428`, …), so they travel
  with the backend containers untouched.
- **Provisioned dashboards**, **alert rules**, **contact-point/policy structure**
  (`grafana/provisioning/`).
- **`config.alloy`** files — already env-driven (`sys.env("REMOTE_WRITE_URL")` /
  `sys.env("LOGS_WRITE_URL")`); no literal backend IP in them.

## Verify after the flip (per signal)

```sh
# metrics — prod-podcast + dgx targets present on the NEW backend
curl -sG "http://homelab:8428/api/v1/query" --data-urlencode "query=up" | grep -o '"instance":"[^"]*"' | sort -u
# logs — recent lines landing
curl -sG "http://homelab:9428/select/logsql/query" --data-urlencode 'query=_time:5m | stats by (instance) count()'
# traces — services reporting
curl -s "http://homelab:10428/select/jaeger/api/services"
# errors — trigger a test error, confirm the issue lands in GlitchTip on homelab
# alert — Grafana → test-fire a rule → confirm a GlitchTip issue opens
```

## Rollback

Flip each `.env` value back to `dgx-llm-1` and restart the same processes.
No schema/volume changes are implied by the flip, so rollback is symmetric and
< 5 min. (Data written to homelab during the window stays on homelab.)
