# homelab-home — tailnet start page

A single-page overview of the homelab machines, served on the mini at
`https://hub.tail6d0ed4.ts.net` (tailnet-only, HTTPS via Tailscale node). Two symmetric columns —
**Mac mini** and **DGX** — each showing: host stat row, CPU/GPU charts,
service health traffic-lights, a Docker line, and a services table. Every
chart/badge deep-links to the matching Grafana dashboard or service.

## Pieces
- `gen.sh` — regenerates `www/index.html`. Reads service creds from the stack
  `.env` files (`observability/backend`, `glitchtip`, `langfuse`, `umami`) at
  generation time; **contains no secrets itself**. Run it to refresh the static
  shell (the live numbers are fetched client-side).
- `docker-compose.yml` — `nginx:alpine` serving `www/`, bound to the **tailnet
  IP** (`100.87.33.61:8888`), joined to `backend_default` so it can proxy VM.
- `default.conf` — nginx, no auth of its own (tailnet-only since 2026-10-24) + a `/vm/`
  reverse-proxy to `victoriametrics:8428` (same-origin, so the page's JS queries
  VM without CORS).

- `hub-status.js` — the hub's status semantics in one place (RFC-0008): what is green, amber or
  red for sites, boxes, Close Listening health, alerts, Needs you, delivery, credit, spend and
  capacity. It returns data; `gen.sh` inlines it and the page draws from it. Tests:
  `test_status.js` (the module), `test_page.js` / `test_uptime.js` (the page on top of it).
- `hub-slo.js` + `slo-catalogue.json` — the service levels (RFC-0009, plan `docs/wip/slo-plan.md`): the
  catalogue has one entry per SLI (`service`, `group`, `sli`, `good_ratio`, `objective`, `link`, optional
  `app` for the Projects band and `note`). `good_ratio` is a PromQL ratio of good to all with a `[window]`
  placeholder the job fills with `28d`, `7d` and `1d` (`[window:1m]` for a subquery). The module turns a ratio
  into the error budget (`1 - objective` of 28 days), a state (meeting: 25 % of the budget or more left; at risk:
  under 25 %; breached: under 0; stale: no data, or numbers older than 15 minutes), the rows sorted by budget left
  inside each group and 28 daily values for the sparkline, and draws the **Levels** tab (between Sites and Hosts),
  the Overview card ("<meeting> of <all> meeting", red when one is breached) and a "Service levels" band on each
  Projects page (rows with that `app`). A query with no data is stale, never 100 %. Probe SLIs carry the Sites
  tab's egress gate (`mini_vm_egress_ok`: minutes while the mini itself was offline leave the window); the test
  refuses a probe query without it. To add an SLI: add an entry and run it once in VictoriaMetrics (vmui or
  `curl --data-urlencode query=...`, with `[window]` replaced by `28d`); an entry whose query returns nothing
  does not belong in the catalogue. Tests: `test_slo.js` (the module and the catalogue file), `test_page.js`
  (the page's part).
- `hub-project.js` — the Projects tab (`#projects/<app>/<period>/<compare>/<audience>`), one page
  per app: Close Listening, Orrery, Evals, Websites. Bands:
  - usage (Umami, through Grafana's `umami-pg`);
  - delivery (the app's own request metrics in VictoriaMetrics; Close Listening splits app
    requests from its background calls);
  - edge and uptime (Cloudflare's 1 h request counts per host, the mini's probes);
  - jobs (Close Listening: nightly run time from the run container's lifetime in cadvisor,
    episodes and enricher failures from VictoriaLogs through the read-only `/vl/select/` proxy).

  Each card is the period so far (Today, 7 days, 30 days) against the previous period, the same
  day last week or the average of earlier periods, over the same stretch of time. Each chart draws
  the comparison dashed under the current line. A comparison window that starts before its number
  has data is left out ("no comparison"):
  - older than the source keeps (VictoriaLogs: 30 days);
  - before the Umami event was first seen;
  - before the gauge's first sample.

  "Beta users" leaves out the operator's own Umami sessions (`operatorIds`, the Player's
  `distinct_id`). Apps are entries in `APPS` plus a link in the tab's `#pj_apps` nav. Tests:
  `test_project.js`.
- `status-job.js` — runs the same module on the mini every 5 minutes (launchd
  `com.homelab.hub-status`), writes `www/status.json` (served at `/status.json`), logs each
  snapshot to VictoriaLogs (`job:hub-status`), and records `hub_status_last_success_timestamp`
  (alert `hub-status-stale`). It also writes `www/timeline.json` (served at `/timeline.json`,
  use case H7, incident write-ups): the last 48 h of alert changes, deploys, backups, drills,
  drift, failed CI runs, new GlitchTip issues and container starts, grouped by kind (`byKind`),
  each kind oldest first, each event one finished `line` (`<local time> — <what> — <ref>`, the
  ref finding it in its source) that the assistant copies; "last night" (19:00 to 07:00) is computed and its events flagged `lastNight`; a source
  that fails is named in `missing`. The assistant does not read this file: it reads one kind at a time,
  `www/timeline/<kind>.json` and `last-night.json` (only the lines), as `getTimeline` (`openapi.json`).
  And `www/analytics.json` (served at `/analytics.json`): per Umami site (dev sites left out),
  visitors and pageviews today, yesterday, the last 7 days and the 7 before (local days), and the
  7 days' top pages, referrers, countries and click events, read through Umami's API with the admin
  login in `~/umami/.env` (one login per run, token in memory only). The assistant reads it as
  `getSiteAnalytics`. A run takes ~5 s with 7 sites (2026-11-04).
  And `www/fleet.json` (served at `/fleet.json`, use case H6): what the triage fleet wants from the
  operator. `needsYou` is the fleet's own count (escalations of the last 7 days + bug proposals, as
  `signal-fleet/mvp/inbox.py` counts them), each escalation with its filed issue, plus every escalated
  issue still open. The fleet part comes only from the inbox the fleet publishes every cycle,
  `~/signal-fleet/export/inbox.json` (schema `fleet_inbox/v1`; `HUB_FLEET_INBOX` overrides the path),
  never from the fleet's ledgers or queue: a document older than an hour is shown with `stale: true`,
  another schema version is refused. The open escalated issues come from
  GitHub with `~/assistant-github-readonly.env` (Issues read on the five repos the fleet files into, listed
  in `hub-sources.js` `FLEET_REPOS`); a repo GitHub refuses is named in `unreadable`. The assistant reads
  it one list at a time, `www/fleet/needs-you.json` and `open-escalated.json` (count and finished lines),
  as `getFleetQueue(list)`; `fleet.json` is for scoring.
  And `www/slo.json` (served at `/slo.json`): every catalogue SLI's ratio over 28 d, 7 d and 1 d, objective, budget
  left, state and 28 daily values, which the page reads (no number is computed twice). The job also pushes
  `hub_slo_ratio{service,sli,window}`, `hub_slo_objective{service,sli}` and `hub_slo_budget_left{service,sli}` so Grafana
  graphs the same numbers, and records `hub_slo_last_success_timestamp`. It runs after the heartbeat, on its own: a
  failure there is logged on the job's line (`service levels failed: ...`) and never changes the rest of the job or its
  exit code. `node status-job.js --slo-only` runs just this part (writes `slo.json`, pushes the gauges).
  `status.json` also carries `assistantSpend`: the assistant's answers by backend (X3 local, free; OpenRouter
  `assistant-cloud`, paid) per Spend-tab window, read from the mini LiteLLM's spend log through
  `docker exec litellm-postgres psql` (the container's own credentials), and pushed as
  `hub_assistant_calls` / `hub_assistant_usd{backend,window}` for the Spend tab's "Assistant: local or
  OpenRouter" cards.
- **The Automation tab** (since 2026-11-23, was Fleets; `#fleets` still opens it). One time frame throughout: counts
  and spend over the last 7 days against the 7 before, lines over 14 days, states as they are now. Flotilla first, one card per
  fleet with a row per routine from `flotilla_run`, `flotilla_routine_last_success_timestamp_seconds`,
  `flotilla_routine_freshness_seconds` and `flotilla_spend_day_usd`, each linking to the routine in flotilla's UI;
  then every fleet, triage included, as one shared row (runs, failures by cause, spend, typical run, from flotillad's "run end"
  log lines, the last failure in its own words, plus ops' off-site backup age, platform's heartbeat pass rate and
  bug-fix's routable issues, and a Cases card from flotilla_cases_open and flotilla_case_moves_total: open by status,
  waiting for your approval, all-time opened and closed); then n8n (up, version and active workflows from its metrics; one card per RFC-0014
  case with its flows' runs (n8n_workflow_*_total) and flotilla's hook calls; the
  flows in `infra/n8n/flows` and the egress allowlist, read when `gen.sh` runs; Egress 7d from the proxy's log lines). Paused or stopped routines are
  not in the metrics, so they show as grey (nothing recent), not as paused.
- **Spend tab links** (2026-11-23): the mini LiteLLM UI, the LLM Gateway dashboard, OpenRouter activity and the
  four vendor consoles. The VPS LiteLLM has no UI on the tailnet.
- **Direct spend on the Spend tab** (since 2026-11-23): calls the mini LiteLLM sends straight to DeepSeek, Qwen
  (Alibaba), Z (GLM) or Kimi (Moonshot), not through OpenRouter.
  - **Which models count:** `gen.sh` builds `DIRECTMODELS` from `infra/litellm/config.yaml`. That is every alias
    whose `api_base` is one of those vendors' APIs, or a native `deepseek/` `moonshot/` `dashscope/` `zai/` model.
    A new direct alias appears on the next `gen.sh` with no Hub change.
  - **Where the numbers come from:** the page reads those models' rows from `LiteLLM_DailyUserSpend`
    (`litellm-pg`) for the same completed UTC days.
  - **Where they show:**
    - the "Direct to vendors" totals card, with one line per vendor even at $0;
    - source `Direct` in the model table, with its own filter;
    - the vendor cards (`OpenRouter + Direct` with both amounts);
    - the callers' and projects' "direct" tokens.
  - **Not counted as local:** before this, the gateway's non-OpenRouter rows were all "local", so these paid
    calls were shown as free local tokens.
  - **What the dollars mean:** LiteLLM's estimate from the list prices set on each alias, not the vendor's bill.
    Qwen's aliases are on a prepaid token plan, priced at list for comparison.
  - **Not covered:** the vendors' balances (no reader), and direct calls through prod's gateway (none so far;
    prod pushes `litellm_model_*` by provider, which the tab does not split by vendor).
- `briefing-job.js` — the morning briefing (RFC-0008 use case H1), at 07:00 (launchd
  `com.homelab.hub-briefing`): needs-you first, then the night (alert changes from Grafana's state
  history, containers started, new GlitchTip issues), numbers, all-green. Every number comes from
  code; the model (`assistant-cloud` through the mini's LiteLLM, key `~/hub-briefing-litellm.env`)
  writes only the two-sentence opening, and the briefing goes out without it if it fails. Writes
  `www/briefing/<date>.html` and `index.html` (the last 30 kept; `https://hub.tail6d0ed4.ts.net/briefing/`),
  pushes the headline to the phone through Home Assistant (`notify.mobile_app_iphone`, token
  `~/home-automation-secrets/ha-token`), records `hub_briefing_last_success_timestamp` (alert
  `hub-briefing-missing`). `node briefing-job.js --dry-run` builds the page without pushing.
- `ci-job.js` + `hub-ci.js` — the CI tab (RFC-0011, phase A). `ci-job.js` runs every 5 minutes (launchd
  `com.homelab.hub-ci`), reads only, and writes `www/ci.json` (served at `/ci.json`: `www/` is mounted whole,
  so `default.conf` needs no change) and the `gh_*` gauges. `hub-ci.js` holds the status semantics (a job
  waiting over 5 min amber, over 30 min red; a runner offline under 15 min amber, 15 min or more red; a failed
  or timed-out job red; a repo with half of 3 or more jobs failed red; a `ci.json` older than 15 min grey) and
  draws the tab from `ci.json`; the page computes nothing else. Tests: `test_ci.js` (the module, and the
  collector over `fixtures-ci/`, saved answers of the real API for the five repos, plus the job as a process
  against a fake VictoriaMetrics); `test_page.js` runs the tab's page code (routes, fetches, refresh, filters) and
  checks the wiring in `gen.sh`.
  - **The drill-down.** Spend's period row (This month, Last 30 days, Last 7 days, Yesterday; completed UTC
    days, `#ci/<period>`, default 30 days), then cards for the chosen period: runs, jobs, minutes on the X3 and
    on GitHub, success rate, median queue wait, estimated GitHub minutes saved, each against the period of the
    same length before it, with "Today so far" the one live row. The collector holds 30 days, so a period whose
    previous one starts before the oldest record (`stats.since`) is not compared. Runs and Success rate open
    the past runs of the period (`when: period`); a per-repo table for the period; a card per runner
    (state, the run it is on, jobs and minutes in 24 h; runners are per repo because `chipi` is a personal
    account). The saved estimate is X3 minutes at $0.008 a minute (GitHub's Linux 2-core list price, `GH_RATE_USD_PER_MIN`);
    wall-clock understates billed minutes (each job rounds up to a minute) and free minutes are not subtracted.
    The success rate is succeeded of succeeded plus failed runs; cancelled runs are shown apart. Past runs are
    paged client-side, 25 a page, over the last 30 days or the chosen period, filtered by repo and result; the
    page and filters live in the hash (`#ci/runs/<page>/<repo>/<result>[/<period>[/period]]`), a run is `#ci/run/<repo>/<id>` (repo without `chipi/`).
    Each run row links to our run page and, small, to GitHub's.
  - **Files the job writes** next to `ci.json` (`www/`, tailnet-only like everything else, no new exposure):
    `ci-state.json` (30 days of runs with their jobs, a ledger of finished jobs, the logs already fetched),
    `ci-runs/<repo>/<run_id>.json` (run header, jobs, steps; written when the run is read, pruned with the 30 days;
    about 9 KB a run), `ci-logs/<repo>/<job_id>.txt` (ANSI codes stripped, the last 600 lines plus every
    `##[error]` line from before them with its line number, up to 50; lines cut at 2000 characters). Logs are fetched
    once per finished job (`GET actions/jobs/<id>/logs`, a redirect followed without the token), for the newest 200
    jobs only, at most 40 a collection; a log not yet fetched says so on the run page; files of jobs that leave the
    newest 200 are deleted. A 404 within an hour of the job ending is retried, later it is given up on.
  - **API budget.** Runs: up to 4 pages of 100 per repo while they are inside 30 days; jobs of a run once (at most
    100 first reads per repo per collection, so a first run backfills 30 days over a few runs); open runs every time.
    Logs as above. `ci.json` lists at most 1000 runs (~0.7 MB); the history is only as old as the collector's reads.
  - **Fixtures** (`fixtures-ci/`) are `gh api` GETs of 2026-11-26 trimmed to the fields used (runs: sha, first
    line of the commit message, actor; jobs: steps), plus two real job logs (`log-<repo>-<job>.txt`, GitHub-masked,
    one CI-only database password replaced by `***`).
  - **What it reads** (GET only, `api.github.com`), for `chipi/closelistening-studio`, `-common`, `-player`,
    `-integration` and `chipi/infra` (override: `HUB_CI_REPOS`, comma list):
    `actions/runners` (name, status, busy, labels; the machine is the label that is not
    `self-hosted`/`linux`/`x64`, today `x3`), `actions/runs?per_page=50`, and `actions/runs/<id>/jobs` for each
    run that is queued, running or finished in the last 24 h (queue wait = started - created, duration =
    completed - started, `where` = self-hosted if the job's labels say so). A finished run's jobs are read once
    and kept in `www/ci-state.json`, which also keeps a ledger of finished jobs for 30 days: the 30 d minutes
    count from the 30 days of runs the collector read (it backfills the newest runs on its first collections).
  - **Token: the assistant's read-only token**, `~/assistant-github-readonly.env` (`GITHUB_TOKEN=...`, the
    same file `hub-sources.js` reads for Issues; override `HUB_CI_TOKEN_FILE`). No new file. That token must
    also cover the five repos with **Actions: Read** (runs and jobs) and **Administration: Read** (the
    runners list), both needed and verified on the mini on 2026-11-26 (reported by the operator's check: with the
    permissions missing, the runners and runs endpoints both answered 403; with them, 200 on all five repos). The
    token's row in `docs/recipes/agent-access.md` lists them. A repo the
    token cannot read shows as an error on the tab, the job exits 1, and the heartbeat is not written, so
    `gh-ci-collector-stale` fires after 20 minutes. The token is never logged.
  - **Gauges** (VictoriaMetrics, labels bounded: no per-job series): `gh_runner_up`, `gh_runner_busy`
    `{repo,runner,machine}`; `gh_jobs_queued`, `gh_job_queue_seconds_max` `{repo}`; `gh_jobs_finished_24h`
    `{repo,conclusion}`; `gh_minutes_24h` `{repo,where}`; `gh_ci_collector_last_success_timestamp`.
  - **Alerts** (`infra/observability/backend/grafana/provisioning/alerting/rules.yaml`, beside
    `hub-status-stale`): `gh-runner-offline` (offline 15 min), `gh-job-queued-long` (waiting over 30 min),
    `gh-ci-collector-stale` (no full read for 20 min).
  - **Try it without a token:** `HUB_CI_FIXTURES=fixtures-ci HUB_CI_NOW=1795730580 HUB_CI_OUT=/tmp/ci/ci.json
    HUB_VM=http://127.0.0.1:1 node ci-job.js` (the push fails and is reported; the file is written).
  - **Install** on the mini: add `com.homelab.hub-ci` to the install loop below, after putting the token's
    new permissions in place; check `/tmp/hub-ci.log` and `www/ci.json`, then `./gen.sh` for the tab.
    **Rollback:** `sudo launchctl bootout system/com.homelab.hub-ci; sudo rm /Library/LaunchDaemons/com.homelab.hub-ci.plist`,
    delete the three `gh-*` rules and the CI tab from `gen.sh`; the `gh_*` series age out of VictoriaMetrics,
    `www/ci.json` and `www/ci-state.json` can be deleted.
- `hub-sources.js` — where the jobs read from (the mini's localhost services and token files).

Install the jobs (system LaunchDaemons running as the operator, from this checkout, as the
mini-metrics jobs do):
```sh
for j in hub-status hub-briefing hub-ci; do
  sudo cp com.homelab.$j.plist /Library/LaunchDaemons/ && sudo chown root:wheel /Library/LaunchDaemons/com.homelab.$j.plist
  sudo chmod 644 /Library/LaunchDaemons/com.homelab.$j.plist && sudo launchctl bootstrap system /Library/LaunchDaemons/com.homelab.$j.plist
done
# undo: sudo launchctl bootout system/com.homelab.<job>; sudo rm /Library/LaunchDaemons/com.homelab.<job>.plist
```

## Reminders (`reminders.json`)

The operator's dated to-dos: a token to renew, a key that expires. Each entry is `text`, `due`
(`YYYY-MM-DD`), `warn_days` and optionally `link` and `about`. `HubStatus.reminders` decides, from the
list and the clock: an entry shows from `warn_days` before its date, and is overdue after it.
- **The page:** a notice bar (`remindbar`). Coming entries are amber and counted in the Notices
  summary. Overdue ones are red, so they are also in the critical bar on every tab. An entry the
  module does not understand shows as a plumbing bar that names it.
- **The briefing:** in Needs you. Overdue ranks beside a site down, coming beside the fleet's queue.
  The first three items go to the phone with the 07:00 push.

To add one: edit `reminders.json`, push, then run `gen.sh` on the mini. The page embeds the list
when it is generated; the briefing reads the file at each run. `test_status.js` fails on an entry it
does not understand, so CI catches a typo.

## Not in git (mini-local, gitignored)
`www/index.html` (generated), `.env`. (`.htpasswd` and `.basic-auth-cred` are left over from the basic auth removed on 2026-10-24.)

## Deploy / refresh (run-in-place from the repo — no copy-out)
Runs from this repo checkout; `gen.sh` writes `www/index.html` next to itself
and the compose mounts it. `www/` is gitignored
(generated / secret, staged here on the mini).
```sh
# on the mini, in this dir (…/agentic-ai-homelab/infra/homelab-home)
./gen.sh                       # rebuild www/index.html
docker compose up -d           # (re)start nginx
```
Reachable at `https://hub.tail6d0ed4.ts.net` (HTTPS via Tailscale certificate node/Caddy).
The container binds loopback `:8888` internally; the public entry point is the dedicated node.

## Related

- Systems index: [`infra/README.md`](../README.md)
- Global docs: [Pillar 2 — Local AI infra](https://github.com/chipi/agentic-ai-homelab/blob/main/docs/local-ai-infra.md)
