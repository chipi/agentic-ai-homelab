# Alerting — provisioned rules, contact points, policies

Grafana alerting rules, notification channels, and routing are defined as code in this directory and loaded into the Grafana instance on the Mac mini on startup. All queries target VictoriaMetrics (infrastructure metrics) or VictoriaLogs (security logs / application events). Changes commit to the repo; `docker compose up -d grafana` reloads provisioning.

## Rules

Rules are grouped by domain. Thresholds are tuned against real baselines observed on 2026-07-20; headroom rationale is noted per rule.

| Rule | Fires when (threshold + for) | Datasource | Intent |
|---|---|---|---|
| **Scrape target down** `infra-target-down` | `up == 0` for 5m | VictoriaMetrics | Critical scrape target lost. Excludes on-demand GPU services (vllm, vllm-autoresearch, ollama — they swap with gpu-mode-swap). |
| **Host disk low** `infra-disk-low` | Free space < 10% for 10m | VictoriaMetrics | Warning: filesystem usage elevated. Current baselines 33–58% free; 10% is pure headroom. |
| **Host disk critical** `infra-disk-crit` | Free space < 5% for 5m | VictoriaMetrics | Critical: imminent fill risk. Opens a GlitchTip issue. |
| **FastAPI 5xx errors elevated** `app-http-5xx` | Rate > 0.01 req/s for 5m | VictoriaMetrics | Application error spike. Covers api, pyannote, moss (all instrumented). Baseline is 0/h; 0.01 req/s ≈ 3+ errors in 5m. |
| **SSH auth failures / probes spiking** `sec-ssh-authfail` | Count > 15 in 5m | VictoriaLogs | Security: SSH probe/auth-failure burst. Prod-podcast is tailnet-only; normal ~0/5m; >15 signals a loop or unexpected exposure. |
| **fail2ban issued a ban** `sec-fail2ban-ban` | Count > 0 (immediately) | VictoriaLogs | Security: confirmed hostile event. Any ban is worth surfacing; fires with no delay. Opens a GlitchTip issue. |
| **Orrery launch data stale** `orrery-launch-data-stale` | No refresh in 7h (for 15m) | VictoriaLogs | Orrery VPS cron (orrerylearn.com) refreshes launch manifest every 6h. Zero successful refreshes in a 7h window means the cron run was missed or the fetch is failing. |
| **Prod ops health check stale** `prod-ops-health-stale` | Last run > 27h ago, or series absent 48h (for 15m) | VictoriaMetrics | Each production app's daily `prod_ops_health.sh` pushes `prod_ops_health_*` gauges; the home page greys to STALE at >26h, this pages at >27h so a dead pusher is reported, not just visible. Generic over `app` labels. |

## Contact points

Each channel is **pluggable** — its secret is sourced from the backend `.env` (gitignored); leaving it empty silences that channel (alert still fires and is visible in the UI).

- **`default`** (email)  
  Recipient configured in `.env` as `ALERT_EMAIL_TO`. SMTP transport is wired via `GF_SMTP_*` env vars.

- **`slack`** (incoming webhook)  
  Webhook URL configured in `.env` as `ALERT_SLACK_WEBHOOK_URL`. Formatted as `[alertname] [severity]`.

- **`glitchtip`** (webhook → issue ingestion)  
  GlitchTip webhook URL configured in `.env` as `ALERT_GLITCHTIP_WEBHOOK_URL`. Receives critical-severity alerts only; each one opens a GlitchTip issue for investigation.

## Notification policies

Routing model: **route by severity, not by channel**. The tree stays stable as channels are added/removed; only the receiver reference changes.

- **Default receiver:** `default` (email + eventually Slack once the webhook is set)
- **Grouping:** by `alertname` and `job`
- **Group wait:** 30s (batch alerts arriving together)
- **Group interval:** 5m (re-group after 5m of silence)
- **Repeat interval:** 4h (re-send unresolved alerts every 4h)

**Critical-severity route:** receiver = `glitchtip`, `continue: true`  
Critical alerts (disk critical, fail2ban ban, scrape target down) route to GlitchTip **and** continue to the default receiver — so confirmed issues both open a ticket and ping the day-to-day channel.

**Transition path:** Once the Slack webhook is set, flip the default receiver from email to `slack` (or add a child route) — no rule changes needed.

## Editing

1. Edit the relevant YAML in this directory (`rules.yaml`, `contactpoints.yaml`, or `policies.yaml`).
2. Commit and push.
3. Reload provisioning: `docker compose up -d grafana` in the backend stack directory.

The strict Grafana provisioning loader validates schema on startup; invalid YAML blocks the container. Check container logs (`docker logs grafana`) if provisioning fails.

Link back to dashboards and observability setup: [../../dashboards/README.md](../../dashboards/README.md) · [../../README.md](../../README.md)
