# Slack for operations

Set up 2026-11-01, after an analytics outage sat for ~14 hours behind an email nobody read at
night. Scope: operations only.

## The rule

**Slack carries only what needs the operator.** Grafana holds every alert and dashboard; email
holds the full record (every alert, warnings included); Slack gets the few things worth acting
on, and stays quiet enough that every notification means "act".

| Channel | What lands there | Notifications | Volume |
|---|---|---|---|
| `#ops-critical` | every `severity=critical` alert, firing and resolved | on (push) | about 40 in the 30 days before the switch, mostly prod OOM kills and the mini's disk, both being fixed |
| `#ops-daily` | reserved for a morning summary; **nothing posts here yet** | off | 0 |

The morning summary is deliberately not built. Grafana cannot send digests, so it would be a new
custom job, and the operator's rule is to minimise custom software and reuse what runs: warnings
are already in email, and the homelab start page shows what is firing. The channel and its
webhook stay ready if an off-the-shelf way appears.

Later, if wanted: `#ops-decisions`, where agents post "needs your go". Not set up.

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

## Checks

- Both webhooks: one test post each from the mini, 2026-11-01, Slack answered `200 ok`.
- A test alert through the `critical` contact point (Grafana's receiver test API; in the UI:
  Alerting, Contact points, `critical`, Test): 2026-11-01, Grafana returned `ok` for both
  integrations and the operator received it in `#ops-critical` and by email.

## Rotating a webhook

In the Homelab Ops app, Incoming Webhooks: remove the old URL, add a new one for the same
channel, put it in the `.env`, recreate Grafana, send a test.
