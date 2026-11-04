# github-status — GitHub outages and maintenance, correlated with what we use

GitHub runs our code, CI, deploys, the fleets' issues and prod's images (ghcr.io), so a GitHub
incident looks like our failure: pushes refused, checks never starting, a deploy that cannot pull.
`poll.py` reads <https://www.githubstatus.com/api/v2/summary.json> every 5 minutes on the mini and
records two things:
- **Outages:** every unresolved incident;
- **Planned maintenance:** in progress, or starting within 7 days (`GITHUB_UPCOMING_DAYS`), so it
  shows up ahead of time.

It is the counterpart of [`infra/hetzner-status`](../hetzner-status/README.md) (the same log, banner
and alert model) and of `infra/cloudflare-edge`'s status part (githubstatus.com is the same
Statuspage product as cloudflarestatus.com). Stdlib only, read-only.

## Correlation (`ours.json`)

| relevance | when | alert | hub bar |
|---|---|---|---|
| `direct` | the incident or maintenance lists a component we use: Git Operations, API Requests, Actions, Pull Requests, Issues, Webhooks, Packages, Pages | yes (new or updated) | incident red; maintenance in progress amber, upcoming muted |
| `other` | everything else (Copilot, Codespaces, …) | no | muted, labelled "not on what we use" |

A component of ours that GitHub marks degraded without an incident shows amber on its own.

## What lands where

- **VictoriaLogs**, stream `app=github-status, service=github-status, environment=operations,
  instance=homelab`: one line per new or updated incident or maintenance. Fields: `kind`
  (`incident`|`maintenance`), `relevance`, `name`, `impact`, `status`, `components`, `link`,
  `start`, `end`, `last_update` (GitHub's latest update text), `backfill` (`true` = already there
  when watching started; never alerts).
- **VictoriaMetrics**, re-pushed every poll while true (read with `last_over_time(…[15m])`):
  - `github_status_indicator{indicator,description}`;
  - `github_status_component{name,status}` (ours, not operational);
  - `github_status_active{kind,relevance,phase,name,impact,status,components,start,end,link}`;
  - `github_status_poll_ok` and `github_status_last_success_timestamp`.
- **Alerts** (`rules.yaml`, group `github-status`, `meta="true"`: email to the operator, not the
  triage fleet): `github-status-ours` (a new or updated `direct` incident or maintenance),
  `github-status-poller-stale` (no successful read for 30 minutes).
- **Hub page**: a GitHub bar in the Notices block (a red one also at the top), counted in
  "Notices: … GitHub".

## Install / update (run in place, like hetzner-status)

```sh
sudo cp com.homelab.github-status.plist /Library/LaunchDaemons/
sudo chown root:wheel /Library/LaunchDaemons/com.homelab.github-status.plist
sudo chmod 644 /Library/LaunchDaemons/com.homelab.github-status.plist
sudo launchctl bootstrap system /Library/LaunchDaemons/com.homelab.github-status.plist
```

It is one long-lived loop: after a `git pull`, restart it with
`sudo launchctl kickstart -k system/com.homelab.github-status`. Log: `/tmp/github-status.log`.
Run once by hand: `python3 poll.py --once`. Tests: `python3 test_poll.py`.

## Limits

- **Only what GitHub admits.** On 2026-11-04, after two incidents that day (Git Operations from
  09:49Z, Actions and Pages from 16:05Z), the page showed "All Systems Operational" while the
  operator still saw runners misbehaving (not measured here). The page is GitHub's word, not a
  measurement; our own signal is CI itself (the `ci-ops-poller`'s `ci_run` events).
- **No per-repo or per-runner view:** the status page is global.
