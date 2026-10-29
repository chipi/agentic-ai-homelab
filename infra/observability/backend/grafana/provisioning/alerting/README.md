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
| **docker-prune stale** `docker-prune-stale` | Last run > 8d ago, or series absent 10d (for 15m) | VictoriaMetrics | Dead-man for the weekly colima disk-reclaim job (`infra/docker-maintenance`). The job was once written-but-never-installed and the disk grew 60G unnoticed — absence of its `homelab_maintenance_last_run_timestamp` push IS the incident. |

## Contact points

Each channel is **pluggable** — its secret is sourced from the backend `.env` (gitignored); leaving it empty silences that channel (alert still fires and is visible in the UI).

- **`default`** (email)  
  Recipient configured in `.env` as `ALERT_EMAIL_TO`. SMTP transport is wired via `GF_SMTP_*` env vars.

- **`slack`** (incoming webhook)  
  Webhook URL configured in `.env` as `ALERT_SLACK_WEBHOOK_URL`. Formatted as `[alertname] [severity]`.

- **`glitchtip`** (webhook → issue ingestion)  
  GlitchTip webhook URL configured in `.env` as `ALERT_GLITCHTIP_WEBHOOK_URL`. Receives critical-severity alerts only; each one opens a GlitchTip issue for investigation.

## Notification policies

Routing model: **route by severity, not by channel**. The tree stays stable as channels are added/removed; only the receiver reference changes. What `policies.yaml` does today:

- **Root receiver:** `default`, email to `$ALERT_EMAIL_TO`. Grouped by `alertname` and `job`; group wait 30s, group interval 5m, **repeat every 24h**.
- **Plumbing states** (`DatasourceNoData`, `DatasourceError`, `Watchdog`): muted. They are wiring problems, not incidents; still visible in Grafana and on the hub banner.
- **`meta: "true"`** (fleetd, the VM, Grafana's own health): matched first, email only, never to the triage fleet.
- **No GlitchTip route.** The old `severity=critical → glitchtip` route was removed on 2026-08-05: a matched child route stops the fall-back to the root receiver, so every critical was swallowed, and GlitchTip is a triage-fleet source, so bridging alerts into it would ingest each event twice. The `slack` and `glitchtip` contact points still exist with placeholder values; no route uses them.

**Who acts on a firing alert.** The triage fleet (signal-fleet) reads every firing Grafana alert, not a list. When you add a rule:

| You want | You do |
|---|---|
| the fleet triages it | nothing: it is in by default. Give it a stable `alertname`, `service` and `instance` labels, a symptom `summary`, and a probe hint |
| only the operator sees it (substrate) | label `meta: "true"` |
| a new box's issues land in its own repo | add one line to `INSTANCE_REPO_MAP` in `signal-fleet/mvp/filing.py` (today `prod-podcast` → podcast_scraper, everything else → this repo) |
| never | let NoData or an absent series impersonate an incident: for pushed metrics use `noDataState: OK` plus a paired dead-man rule; for scraped metrics fix the scrape |

`kind=` is a hint for the triager, never a gate; a new `kind` needs no fleet change.

## Editing

1. Edit the relevant YAML in this directory (`rules.yaml`, `contactpoints.yaml`, or `policies.yaml`).
2. Commit and push.
3. Reload provisioning: `docker compose up -d grafana` in the backend stack directory.
   Gotcha: if the container config didn't change, `up -d` does NOT restart it and the new
   rules are NOT loaded — use the restart-free reload instead:
   `curl -X POST -u "$ADMIN:$PASS" http://localhost:3000/api/admin/provisioning/alerting/reload`

**Rule-authoring gotcha — error-counter series don't exist until the first error.** A rule
querying a label slice that only appears after the first bad event ever (`status="bounced"`,
`outcome="error"`, …) gets NoData on a *healthy* system, and Grafana's default `noDataState`
turns that good news into a permanent `DatasourceNoData` plumbing alert. Set
`noDataState: OK` on such rules. Rules of record: `fleetd-cycle-failing` (2026-08-02, 6 days
false-firing) and `delivery-high-bounce`/`delivery-dead-letter` (2026-08-14→30, 16 days).
The reverse also matters: for dead-man rules watching a series that SHOULD always exist
(`prod-ops-health-stale`, `delivery-scheduler-silent`), absence is the incident —
`noDataState: Alerting` is correct there. Decide which case a new rule is; don't inherit the default.

The strict Grafana provisioning loader validates schema on startup; invalid YAML blocks the container. Check container logs (`docker logs grafana`) if provisioning fails.

Link back to dashboards and observability setup: [../../dashboards/README.md](../../dashboards/README.md) · [../../README.md](../../README.md)
