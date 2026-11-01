# Slack for operations

Set up 2026-11-01, after an analytics outage sat for ~14 hours behind an email nobody read at
night. Scope: operations only.

## The rule

**Slack carries only what needs the operator.** Grafana holds every alert and dashboard; email
holds the full record (every alert, warnings included); Slack gets the few things worth acting
on, and stays quiet enough that every notification means "act".

Principles: one channel = one purpose = one feeding system; only `#ops-critical` and
`#ops-decisions` notify; reuse what runs (Grafana alerting, the official GitHub app, the triage
fleet), custom code only where nothing off the shelf exists; stay inside the free plan's 10
integrations (Homelab Ops and GitHub use 2).

| Channel | What lands there | Fed by | Notifications | Status |
|---|---|---|---|---|
| `#ops-critical` | every `severity=critical` alert, firing and resolved | Grafana alerting | on (push) | live |
| `#ops-deploys` | every prod deploy run (started, passed, failed); deploy gates can be approved from Slack | GitHub app, workflow subscriptions | off | live |
| `#ops-triage` | issues the triage fleet files or comments on | GitHub app, issues with label `triage-fleet/filed` | off | live |
| `#ops-decisions` | agents' "needs your go" | agents (not built) | on | channel exists, phase 3 |
| `#ops-daily` | reserved for a morning summary; nothing posts | — | off | parked |

`#ops-critical` volume: about 40 messages in the 30 days before the switch, mostly prod OOM kills
and the mini's disk, both being fixed.

The morning summary is deliberately not built. Grafana cannot send digests, so it would be a new
custom job, and the operator's rule is to minimise custom software and reuse what runs: warnings
are already in email, and the homelab start page shows what is firing. The channel and its
webhook stay ready if an off-the-shelf way appears.

### Phases

1. **Done (2026-11-01):** critical alerts with action-named links; `#ops-deploys` and
   `#ops-triage` via the GitHub app.
2. **Asking ops questions in Slack: parked, and it will be our own agent, not Claude Tag**
   (operator, 2026-11-01). Claude Tag (Anthropic's Claude in Slack) was ruled out: it needs a
   Claude Team or Enterprise plan, runs in Anthropic's cloud sandbox with default-deny egress (so
   it cannot reach the tailnet: Grafana, VictoriaMetrics, the mini), and its use of a custom remote
   MCP connector is not documented. The operator prefers agents hosted on the DGX for this, when
   that capability exists there; it would answer in the ops channels from the homelab's own
   observability. Not designed yet.
3. **Small builds, design first:** the triage fleet replies in a critical's thread ("known issue
   #…" or "new"); `#ops-decisions` with one "needs your go" format for every agent session.

Monthly: count messages per channel. `#ops-critical` should average under one a day; an alert that
pushes without needing action is fixed or demoted.

## How it is wired

Everything runs in Grafana's own alerting on the Mac mini:

- **Rules** (`infra/observability/backend/grafana/provisioning/alerting/rules.yaml`) are evaluated
  every minute against VictoriaMetrics and VictoriaLogs.
- **Routing** (`policies.yaml`): `severity=critical` goes to contact point `critical`, before any
  other route. Warnings fall to the root receiver, email.
- **Contact point `critical`** (`contactpoints.yaml`) holds two integrations: email
  (`ALERT_EMAIL_TO`) and Slack (`ALERT_SLACK_WEBHOOK_URL`). One contact point, because a matched
  route stops the fall-back to the root receiver: a Slack-only route would have dropped the email.
- **Message:** `[CRITICAL]` or `[RESOLVED]`, the alert name, host and instance; the rule's summary
  (what broke, the first thing to check); the links, each named after its action:

  | Link | Opens | You |
  |---|---|---|
  | the title | this alert's page: query, graph, instance, earlier firings | judge new or repeat |
  | Mute this alert… | the silence form, pre-filled for this alert only | pick a duration, Save |
  | All firing alerts | Active notifications (`/alerting/groups`): everything firing now | see if it is part of something bigger |

  A resolved message is the title (still a link to the alert) and "Cleared at". The title is a
  Slack link (`<url|text>`) because that overrides the title link Grafana sets itself
  (`/alerting/list`, grafana/alerting#96). Grafana is tailnet-only, so the links work where
  Tailscale runs. Verified 2026-11-01 with a real temporary critical rule: title, mute form
  (1 affected instance) and the firing list all correct.
- **Silencing a known critical:** the Silence link opens Grafana's silence form with that alert's
  labels filled in. Choose the duration there (default 2h; the form takes none from the URL) and
  save. Notifications stop until it expires; the alert still evaluates and shows as firing. Use it
  for something already being worked on, so `#ops-critical` keeps meaning "act".

What counts as critical was reviewed on 2026-11-01 against 30 days of firings: 20 rules.
`infra-target-down` (59 firings, mostly flapping exporters) and `sec-fail2ban-ban` (routine
bans) were demoted to warning. "Home internet down" stays critical and reaches `#ops-critical`.

## The Slack side

A custom app, **Homelab Ops**, created at <https://api.slack.com/apps> "From scratch", with only
**Incoming Webhooks** turned on (no other scopes, no events). One webhook per channel. It works on
the free plan: the app is one of the plan's 10 integrations; history older than 90 days is
hidden, which is fine because Grafana and email keep the record.

The webhook URLs are secrets (anyone holding one can post to the channel). They live only in the
mini's `~/agentic-ai-homelab/infra/observability/backend/.env`, entered by the operator:

```text
ALERT_SLACK_WEBHOOK_URL=…        # #ops-critical
OPS_DAILY_SLACK_WEBHOOK_URL=…    # #ops-daily
```

Grafana reads `ALERT_SLACK_WEBHOOK_URL` at container start (`docker-compose.yml` passes it
through), so after changing it: `docker compose up -d grafana` in `infra/observability/backend`.

### The GitHub app (`#ops-deploys`, `#ops-triage`)

The official GitHub app for Slack. Three connections, all needed: the app added to the workspace;
`/github signin` (links the Slack user to GitHub `chipi`); and on GitHub, Settings,
Applications, Slack, repository access to `infra`, `orrery`, `eval-harness`, `podcast_scraper` and
`agentic-ai-homelab`. In a private channel, `/invite @GitHub` first. Slack runs one slash command
per message: paste each line separately.

`#ops-deploys` (the prod deploy workflows of each repo; Close Listening deploys from `infra`):

```text
/github subscribe chipi/infra workflows:{name:"Deploy ALL prod surfaces at ONE sha","Deploy player — PUBLIC surface","Deploy operator — PUBLIC surface","Deploy operator — CONTROL plane (tailnet · privileged)","Deploy config (by surface)","Deploy litellm — PROD gateway (tailnet · ADR-142)","Deploy vps-observability endpoints (prod Alloy → TLS)"}
/github subscribe chipi/orrery workflows:{name:"Deploy to prod VPS (orrery)"}
/github subscribe chipi/eval-harness workflows:{name:"Deploy evals to prod VPS"}
/github unsubscribe chipi/<repo> issues pulls commits releases deployments     (each of the three)
```

`#ops-triage` (the repos holding the fleet's `triage-fleet/filed` issues):

```text
/github subscribe chipi/podcast_scraper issues comments +label:"triage-fleet/filed"
/github subscribe chipi/agentic-ai-homelab issues comments +label:"triage-fleet/filed"
/github subscribe chipi/orrery issues comments +label:"triage-fleet/filed"
/github subscribe chipi/eval-harness issues comments +label:"triage-fleet/filed"
/github unsubscribe chipi/<repo> pulls commits releases deployments            (each of the four)
```

**The name filter splits on commas and has no escape.** A workflow whose name contains a comma
can never match: two infra workflows were renamed for this on 2026-11-01 (chipi/infra 7fc747d,
`(tailnet, privileged)` to `(tailnet · privileged)`, `(tailnet, ADR-142)` to `(tailnet · ADR-142)`).
Keep deploy workflow names comma-free, and copy names exactly (em-dash, middle dot, arrow).
`/github subscribe list features` shows what is active.

## Checks

- Both webhooks: one test post each from the mini, 2026-11-01, Slack answered `200 ok`.
- A test alert through the `critical` contact point (Grafana's receiver test API; in the UI:
  Alerting, Contact points, `critical`, Test): 2026-11-01, Grafana returned `ok` for both
  integrations and the operator received it in `#ops-critical` and by email.
- `#ops-deploys`: an Orrery prod deploy posted there, 2026-11-01 (operator).
- `#ops-triage`: `/github subscribe list features` showed the four repos with
  `issues, comments, +label:'triage-fleet/filed'`; no fleet issue had posted yet when written.

## Rotating a webhook

In the Homelab Ops app, Incoming Webhooks: remove the old URL, add a new one for the same
channel, put it in the `.env`, recreate Grafana, send a test.
