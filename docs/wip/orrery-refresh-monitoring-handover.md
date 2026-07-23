# Handover — Orrery launch-data refresh monitoring (2026-07-23)

Short note for whoever picks up the mini-side work. Two things to do (§Todo).

## What we did

- **Orrery prod (`orrerylearn.com` VPS)** now self-refreshes its launch manifest
  every 6h via an on-VPS cron (Orrery RFC-035) — fetches from the upstream APIs
  into the `/data` overlay nginx serves live. The **GitHub refresh workflows were
  deleted**; GitHub is out of the prod data path.
- The Orrery `grafana-agent` now **tails `/srv/orrery/data-refresh.log`** and
  ships it to VictoriaLogs as **`job=orrery-data-refresh`** (labels
  `app=orrery`, `surface=pipeline`). Deployed + verified flowing:
  `job:orrery-data-refresh "ok" "bytes"` returns >0.
- **This repo, commit `81cc662` (already on `origin/main`):**
  - `infra/observability/backend/grafana/provisioning/alerting/rules.yaml` — new
    `orrery` group, rule `orrery-launch-data-stale`: warns if no successful
    refresh (`… | stats count()` on `"ok" "bytes"`) in a 7h window.
  - `infra/observability/backend/grafana/dashboards/orrery-launch-data.json` —
    success/fail counts (24h) + live refresh log.

## Todo

1. **Activate on the mini.** The mini's checkout (`~/agentic-ai-homelab`) is behind
   `origin/main` **and has local uncommitted state** (`.sops.yaml` modified,
   `secrets.sops.env` untracked). Grafana here is shared multi-tenant, so pull +
   restart carefully:
   ```sh
   cd ~/agentic-ai-homelab
   git stash push -u .sops.yaml infra/observability/secrets.sops.env
   git pull --ff-only origin main
   git stash pop
   /usr/local/bin/docker restart grafana   # loads the alert rule; dashboards auto-reload (file provider, 30s)
   ```
   Verify: the `orrery-launch-data-stale` rule appears in Grafana Alerting and the
   "Orrery — launch data refresh" dashboard renders. The rule query already
   validates live against VictoriaLogs.

2. **Fix the `app=orrery` log-stream mislabel.** ~9k lines/12h in VictoriaLogs are
   tagged **`{app=orrery, env=prod}` with no `container`/`tenant`/`job`**, but the
   content is a **uvicorn API's `/healthz` `/metrics` `/api/health`** — NOT Orrery
   (Orrery has no Python service; its VPS agent always adds `container` via
   `docker_sd`). So a **mini-side Alloy/agent config is mislabelling some other
   service's logs as `app=orrery`**, polluting the orrery stream. Find the source
   (a label-less scrape pushing `external_labels: app: orrery`) and give those
   logs their correct `app`/`tenant`. Not in the Orrery repo (grep-confirmed).
   Repro:
   ```sh
   curl -s http://homelab:9428/select/logsql/query \
     --data-urlencode 'query=app:orrery -container:* | fields _time,_msg' \
     --data-urlencode 'start=1h' | head
   ```
