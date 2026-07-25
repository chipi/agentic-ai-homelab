# ci-ops-poller — CI/DORA poller (Tier-2) → VictoriaLogs

A launchd loop **on the mini** that pulls the **GitHub Actions API** and emits
`ops_event/v1` records to VictoriaLogs (`:9428`), covering the CI/CD signals that
**don't** join the tailnet and so can't push from inside the runner. Together
with the Tier-1 push events (deploy/backup, emitted from `podcast_scraper`), this
gives CI health + DORA metrics on one Grafana pane (folder **CI Ops**).

Design lineage: homelab handover (`podcast_scraper#1319`), ADR-119 (vendor-
neutral event emission). Tier-1 contract lives in
`podcast_scraper:infra/observability/github-actions/README.md`.

## What it does, each poll (~15 min)

1. Reads a persisted cursor (`state.json`) and queries
   `GET /repos/<repo>/actions/runs?created=>{since}` (paginated). The repo has
   thousands of runs — it **never full-scans**; the cursor + a 2h overlap window
   bound every query.
2. For each **completed** run, classifies by workflow file:
   - `infra-drift.yml` → **`drift`**
   - `drill-*.yml` → **`drill`**
   - other `.github/workflows/*` → **`ci_run`**
   - the four Tier-1 workflows (deploy-prod/player, backup-corpus/player) → **skipped**
     (they're already emitted via push — skipping avoids double-counting).
3. Emits `ops_event/v1` to `POST :9428/insert/jsonline` with
   `duration_ms` (`updated_at − run_started_at`), `queue_ms`
   (`run_started_at − created_at`), plus `workflow, branch, event, sha, run_id,
   attempt, status`.
4. **Dedups on `run_id:run_attempt`** (VictoriaLogs is append-only). A re-run
   bumps `run_attempt` → a new event = the flaky signal.

Stream fields (low cardinality): `app, env, event_type`. `env` defaults to `ci`
(Tier-1 deploys use `prod`).

## The DORA metrics that fall out (LogsQL over VictoriaLogs)

- **Deploy frequency** — `event_type:deploy status:success` over time (Tier-1).
- **Change-failure-rate** — `deploy status:failure` ÷ total deploys.
- **Lead time / MTTR** — from `deploy` `duration_ms` + failure→next-success gaps.
- **CI health** — `ci_run` pass-rate, flaky-rate (`attempt:>1`), `queue_ms`.

Two dashboards render this data, provisioned in the **CI Ops** Grafana folder:
- `CI Ops/ci-ops-overview.json` (`podcast-ci-ops-overview`) — deploy/backup +
  event overview.
- `CI Ops/dora-metrics.json` (`podcast-ci-ops-dora`) — the four DORA metrics +
  CI health (deploy frequency, change-failure, CI pass/flaky, queue/duration).

## Install (on the mini)

```sh
# 1. mint the fine-grained PAT (see .env.example) and drop it in .env
cp .env.example .env && $EDITOR .env        # set GITHUB_TOKEN
# 2. stage the script + config where the plist expects them
mkdir -p ~/ci-ops-poller
cp poll.py .env ~/ci-ops-poller/
# 3. smoke-test one cycle (prints scanned/emitted, writes to VictoriaLogs)
python3 ~/ci-ops-poller/poll.py --once
# 4. install the launchd loop
cp com.homelab.ci-ops-poller.plist ~/Library/LaunchAgents/
launchctl load -w ~/Library/LaunchAgents/com.homelab.ci-ops-poller.plist
tail -f /tmp/ci-ops-poller.log
```

Uses `/usr/bin/python3` (stdlib only — no pip deps). `.env` + `state.json` are
gitignored.

## Verify

```sh
# events landing (last 1h, by type):
curl -sG "http://homelab:9428/select/logsql/query" \
  --data-urlencode 'query=schema:ops_event/v1 event_type:(ci_run OR drift OR drill) _time:1h | stats by (event_type) count()'
```

## Relation to `fleetd`

Deliberately standalone, matching the mini's other launchd loops
([`../mini-metrics/`](../mini-metrics/README.md),
[`../dgx-scrape/`](../dgx-scrape/README.md)) — it does not touch the `fleetd`
package. If you later prefer to run it under `fleetd`, it already honors that
cycle contract: `poll.py --once` is idempotent (the cursor owns dedup) and exits
0, so it drops in as a `cycle_cmd` with no code change.

## Related

- Dashboards folder: [`../observability/backend/grafana/dashboards/CI Ops/`](../observability/backend/grafana/dashboards/CI%20Ops/README.md)
- Systems index: [`infra/README.md`](../README.md)
- Upstream emit contract: `podcast_scraper:infra/observability/github-actions/README.md`
