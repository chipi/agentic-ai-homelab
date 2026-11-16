# RFC-0009 — Service levels: SLIs and SLOs for every service, shown on the Hub

**Status:** Accepted, built (2026-11-16): every service, the proposed target levels, a view on the Hub
only for now (the Levels tab), burn-rate alerts thought about afterwards. How it is built, and what
changed from this text (a status job instead of recording rules): [the plan](../wip/slo-plan.md).
**Relates to:** the Hub ([`infra/homelab-home/`](https://github.com/chipi/agentic-ai-homelab/tree/main/infra/homelab-home):
`hub-status.js`, `hub-project.js`), the mini's site probe (`infra/observability/hosts/homelab/config.alloy`,
job `site-probe`), the Grafana alert rules (`infra/observability/backend/grafana/provisioning/alerting/rules.yaml`),
the [agent access handbook](../recipes/agent-access.md).

## Motivation

The homelab runs services for real users (Close Listening, Orrery, the websites) and services the
operator's own work depends on (LiteLLM, observability, backups, flotilla, the DGX's models). Each
is watched: the Hub's traffic lights, 123 alert rules, the site probe. None has a stated level:
nothing says how often Orrery may be down in a month before that is a problem, so a red light is
always urgent and a green month proves nothing.

Service levels are the step before agreements with anyone (SLAs): first say what each service
should deliver, measure it the same way every time, and see a month of it.

- **SLI** (indicator): a ratio of good events to all events, from data already collected. For
  example, the share of one-minute probes of `www.orrerylearn.com` that succeeded.
- **SLO** (objective): the share an SLI must reach over a window, here 28 days rolling. For
  example 99.5 %.
- **Error budget:** what the SLO leaves, e.g. 0.5 % of 28 days is 3 h 22 min of failed probes. The
  view shows how much of it is spent.

**Non-goals:** SLAs; alerts on SLOs (a later step, below); new collectors or probes beyond small
gaps named in the catalogue; per-user or per-request tracing.

## Proposal

### 1. Three kinds of SLI, all from what is collected today

| Kind | Good event | Source |
| --- | --- | --- |
| **Availability** | a probe minute that succeeded, counted only while the mini itself reaches the internet (as the Hub already does, `mini_vm_egress_ok`) | `probe_success{job="site-probe"}` per host; `up{job=...}` for internal services |
| **Latency** | a request answered within its threshold | `http_request_duration_seconds_bucket` where the app exports it; otherwise the probe's `probe_duration_seconds` |
| **Freshness / success** (jobs) | a scheduled job that finished on time | the `*_last_success_timestamp` gauges the jobs already push (backups, delivery, flotilla routines, the Hub, prod ops health) |

A probe that cannot run (the mini offline) is neither good nor bad: those minutes leave the
window, so a home internet outage is not charged to Orrery.

### 2. The catalogue and proposed targets (28 days rolling)

**Public sites and apps** (users depend on them):

| Service | SLI | SLO |
| --- | --- | --- |
| Orrery `www.orrerylearn.com` | availability (probe, page check) | 99.5 % |
| | latency: probe under 2 s | 99 % |
| Orrery lab API, MCP (`lab-api.`, `mcp.orrerylearn.com`) | availability (`/health`) | 99 % |
| Close Listening player and API (`closelistening.app`) | availability (`/api/app/auth/status`) | 99.5 % |
| | latency: API requests under 1 s (`http_request_duration_seconds`) | 99 % |
| | prod ops health green or orange (`prod_ops_health_aggregate` ≥ 0.5) | 99 % of checks |
| Close Listening MCP, obs MCP | availability | 99 % |
| Close Listening nightly pipeline | the run finished by 07:00 local | 6 of 7 nights (≈ 86 %) |
| `www.humancopilot.eu`, `www.devwhateverops.com`, `evals.humancopilot.eu` | availability | 99.5 % |
| `www.markodragoljevic.com`, `airandspacehistory.com` (hosted by Format, Adobe) | availability | 99 % (measured, not ours to fix until they are self-hosted) |

**Telemetry the apps send to** (an outage loses data silently):

| Service | SLI | SLO |
| --- | --- | --- |
| Umami trackers (5 `analytics.*` hosts) | availability (`/api/send`) | 99.5 % |
| GlitchTip intake (3 `telemetry.*` hosts) | availability (envelope endpoint) | 99.5 % |

**Platform** (the operator's own work depends on it):

| Service | SLI | SLO |
| --- | --- | --- |
| LiteLLM gateway (mini) | availability (`up`) | 99 % |
| Observability stack (VictoriaMetrics, VictoriaLogs, Grafana) | availability (`up`) | 99 % |
| Delivery (outbox) | availability (`up{job="delivery"}`); freshness under 15 min | 99 % each |
| Off-box backup (mini) | a successful backup within 26 h | 99 % of hours |
| Close Listening Postgres backup and restore check | backup within 26 h; restore check within 8 days | 99 % of hours |
| flotilla | each enabled routine fresh (`flotilla_routine_last_success_timestamp_seconds` within its `freshness`) | 99 % per routine |
| The Hub's own jobs (status, briefing) | fresh (status 15 min, briefing daily by 07:15) | 99 % / 27 of 28 days |
| DGX models (prod vLLM, translation vLLM) | availability while the GPU mode is `prod` | 99 % |

Targets are where a homelab can be honest: 99.5 % allows 3 h 22 min of failure in 28 days, 99 %
allows 6 h 43 min. Most of today's services are above them; the point of the first month is to see
where they are not.

### 3. Recording rules in VictoriaMetrics

One recording rule per SLI, `sli:<service>:<kind>:ratio_28d` (and a 1 h and 7 d version for the
view's trend), next to the alert rules in the backend's provisioning. The Hub and Grafana read the
same series; no number is computed in two places. The catalogue lives in one file
(`infra/observability/slo/catalogue.yaml`: service, SLI, query of good and of total, objective)
from which the rules are generated, so adding a service is one entry.

### 4. A view on the Hub

A **Service levels** tab on the Hub, one row per service: the SLI now, against its SLO, the error
budget left (time and %), and a 28-day sparkline. Rows sort by budget left, so what is closest to
breaking is first. Each row links to its Grafana panel. The Projects tab's cards for Close
Listening and Orrery gain the matching SLO row. Mobile first (360 px, no sideways scroll).

### 5. Later: when a budget burns

Not built now (the operator's decision): burn-rate alerts (fast: 2 % of the budget in 1 h; slow: 5 %
in 6 h) that would replace the per-service "is down" alerts, and the budget left feeding the
morning brief and flotilla's ops fleet. To be thought through once a month of the view exists.

## Open questions

1. **Gaps:** the DGX models and LiteLLM have no outside-in probe, only `up`; is `up` enough, or a
   probe that makes a one-token request?
2. **Latency on the sites:** the probe measures from the mini, one place; Cloudflare's own timings
   per request would be truer (the free plan gives aggregate request counts, not latency per host).
3. **Bots:** Orrery's traffic is mostly a browser farm this week (2026-11-16): an SLI counted on
   requests would be about them; availability by probe is not.

## Alternatives considered

- **Grafana's SLO plugin / Sloth / Pyrra:** generate the same recording rules from a catalogue. A
  dependency for what a small generator does; reconsider if the catalogue grows past ~40 SLIs.
- **Uptime percentages only** (the Hub's 24 h probe averages): no window, no budget, and blind to
  latency and jobs.

## Discussion

- 2026-11-16 — drafted from the operator's ask; the catalogue is what the site probe, the alert
  rules and the Hub's sources measure today.
- 2026-11-16 — accepted with the plan's four decisions; built as the Hub's Levels tab (47 SLIs).
  Close Listening API latency leaves out health checks and background polls (what users wait for);
  the nightly pipeline row reads the pipeline's own `podcast_pipeline_last_success_age_seconds`.
