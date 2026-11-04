# provider-status — outages and planned maintenance of the providers we depend on

GitHub and OpenRouter outages look like our own failures. On GitHub's side: pushes refused, checks
that never start, a deploy that cannot pull prod's images from ghcr.io. On OpenRouter's side: the
fleets' and the pipeline's LLM calls failing, the assistant's failover gone. `poll.py` reads each
provider's status page every 5 minutes on the mini and records two kinds of item:
- **Outages:** incidents not yet resolved;
- **Planned maintenance:** in progress, or announced and not started, so it shows up ahead of time.

It is the family of [`infra/hetzner-status`](../hetzner-status/README.md) (the same log, banner and
alert model) and of `infra/cloudflare-edge`'s status part. Those two keep their own collectors.
Stdlib only, read-only.

## Providers (`providers.json`)

| Provider | Reader | What counts as ours (`direct`) |
|---|---|---|
| GitHub | `statuspage`: `githubstatus.com/api/v2/summary.json` (components, unresolved incidents, scheduled maintenance with start and end) | an item listing Git Operations, API Requests, Actions, Pull Requests, Issues, Webhooks, Packages or Pages (not Copilot, Codespaces) |
| OpenRouter | `rss`: `status.openrouter.ai/history.rss` (its JSON API answers 403; each item has a category and its updates, newest first, with a state word) | every item, unless its title is about the website, sign-in or video, or its text says "Inference is not affected" (the feed names no components) |

- **What counts as active:**
  - an incident whose newest state is not Resolved / Completed / Postmortem;
  - maintenance in progress;
  - maintenance announced but not started. On GitHub that means starting within 7 days
    (`PROVIDER_UPCOMING_DAYS`). On OpenRouter it means the newest state is "Scheduled": its feed gives
    no start time as a field, so the hub shows it as "announced".
- **To add a provider:** add an entry with one of the two reader types. Many status pages are either
  Statuspage (`/api/v2/summary.json`) or publish a `history.rss`.

## What lands where

- **VictoriaLogs**, stream `app=provider-status, service=provider-status, environment=operations,
  instance=homelab`: one line per new or updated item. Fields:
  - `provider`, `kind` (`incident`|`maintenance`), `relevance`;
  - `name`, `status`, `impact`, `components`, `link`, `start`, `end`;
  - `last_update` (the provider's newest update text);
  - `backfill`: `true` means it was already there when watching that provider started, and never
    alerts.
- **VictoriaMetrics**, re-pushed every poll while true (read with `last_over_time(…[15m])`), each with
  a `provider` label:
  - `provider_status_active{kind,relevance,phase,name,impact,status,components,start,end,link}`;
  - `provider_status_component{name,status}` (statuspage: a component of ours not operational);
  - `provider_status_indicator{indicator,description}` (statuspage);
  - `provider_status_poll_ok` and `provider_status_last_success_timestamp`.
- **Alerts** (`rules.yaml`, group `provider-status`, `meta="true"`: email to the operator, not the
  triage fleet):
  - `provider-status-ours`: a new or updated `direct` incident or maintenance;
  - `provider-status-poller-stale`: a provider not read for 30 minutes.
- **Hub page:** one bar per item in the Notices block, named by provider ("GitHub · incident on what
  we use", "OpenRouter · maintenance"). A red bar also shows at the top. The Notices line counts them
  per provider.

## Install / update (run in place, like hetzner-status)

```sh
sudo cp com.homelab.provider-status.plist /Library/LaunchDaemons/
sudo chown root:wheel /Library/LaunchDaemons/com.homelab.provider-status.plist
sudo chmod 644 /Library/LaunchDaemons/com.homelab.provider-status.plist
sudo launchctl bootstrap system /Library/LaunchDaemons/com.homelab.provider-status.plist
```

It is one long-lived loop: after a `git pull`, restart it with
`sudo launchctl kickstart -k system/com.homelab.provider-status`. Log: `/tmp/provider-status.log`.
Run once by hand: `python3 poll.py --once`. Tests: `python3 test_poll.py`.

## Limits

- **Only what a provider admits.** On 2026-11-04, after two GitHub incidents that day (Git Operations
  from 09:49Z, Actions and Pages from 16:05Z), GitHub's page showed "All Systems Operational" while the
  operator still saw runners misbehaving (not measured here). A status page is the provider's word,
  not a measurement. Our own signals are CI itself (the `ci-ops-poller`'s `ci_run` events) and
  LiteLLM's errors in GlitchTip.
- **OpenRouter's relevance is a text rule**, since its feed names no components: an API problem
  whose title happens to mention "dashboard" would be marked `other`.
- **The view is global:** neither page shows a per-repo, per-runner or per-model status.
