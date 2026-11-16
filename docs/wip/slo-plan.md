# Service levels: the build plan, and how they show on the Hub

The plan for [RFC-0009](../rfc/RFC-0009-service-slos.md), accepted and built 2026-11-16 (the Hub's Levels
tab). The operator's decisions: every service, the RFC's target levels, a view on the Hub only (no
alerts yet), and §6 below.

## 1. What the data says today

Checked on the mini, 2026-11-16, read only:

- VictoriaMetrics keeps 6 months (`--retentionPeriod=6`), so a 28-day window is always there.
- **Availability over the last 28 days** (probe minutes that succeeded, counted only while the mini
  itself reached the internet, as the Hub's Sites tab already does):
  - 16 of the 19 probed endpoints are between 99.78 % and 99.98 %.
  - **Three are under their 99.5 % target:** `analytics.closelistening.app` 97.03 %,
    `airandspacehistory.com` 97.17 %, `analytics.humancopilot.eu` 98.43 %. The first view will open
    with them red. That is the point of it, not a bug to hide.
- **Probe latency:** the 95th percentile over 28 days is under 0.81 s on every endpoint (the
  proposed threshold is 2 s).
- Close Listening's API exports `http_request_duration_seconds` (2,383 series); `up` exists for the
  internal services (delivery, LiteLLM's database, vLLM, Ollama, the Victoria stack and more).

## 2. A change to the RFC: no recording rules

The RFC proposed VictoriaMetrics recording rules, but **nothing in the stack evaluates rules**: the
backend runs Grafana, VictoriaMetrics, VictoriaLogs and VictoriaTraces, no vmalert. Adding vmalert is a
new service. Instead, the Hub's existing **status job** (`status-job.js`, every 5 minutes on the mini)
computes the SLIs:

- it reads the catalogue, runs each SLI's query over 28 days (and over 7 days and 1 day for the
  trend), and writes `www/slo.json`;
- it pushes the results back to VictoriaMetrics as gauges (`hub_slo_ratio{service,sli,window}`,
  `hub_slo_objective{service,sli}`, `hub_slo_budget_left{service,sli}`), so Grafana graphs them
  from the same numbers;
- the page reads `slo.json`; no number is computed in two places.

One job, no new service, and the same failure handling the Hub already has: a stale `slo.json`
renders grey, never green.

## 3. The catalogue

`infra/homelab-home/slo-catalogue.json` (JSON, because the status job is Node with no YAML library).
One entry per SLI:

```json
{ "service": "Orrery", "group": "Public sites and apps", "sli": "availability",
  "good_ratio": "<PromQL giving the share of good minutes>", "objective": 0.995,
  "link": "#projects/orrery" }
```

Three query shapes cover the RFC's whole catalogue:

| Kind | The ratio |
| --- | --- |
| availability (probe) | the Sites tab's own expression for that host, averaged over the window |
| availability (internal) | `avg_over_time(up{job="..."}[window])` |
| latency | from the histogram: requests under the threshold over all requests; for probed sites, the share of probe minutes under 2 s |
| freshness (jobs) | the share of 5-minute steps in which `time() - <last_success_timestamp>` was under the job's bound |

Each objective comes from the RFC's table. The error budget is `1 - objective` of 28 days; budget
left is how much of it the window has not used.

**Gaps found while planning:** the Close Listening nightly pipeline has no "finished by 07:00"
metric. Its SLI reads the pipeline's own `podcast_pipeline_last_success_age_seconds` (the full
incremental run, as the 36 h alert does) within 26 h, and the catalogue says so (operator,
2026-11-16). The DGX models and LiteLLM have `up` only (the RFC's first open question).

## 4. How it shows on the Hub

**A new tab, Levels**, between Sites and Hosts. Mobile first: it works at 360 px with no sideways
scroll, and on a phone each row stacks. In the sketch, the three rows' numbers are today's (§1); the
counts in the header and the sparklines are made up for the layout.

```text
Service levels · 28 days rolling                         updated 10:05 · 31 SLIs
3 below target · 2 at risk · 26 meeting

PUBLIC SITES AND APPS
● analytics.closelistening.app   availability  97.03 %  target 99.50 %  budget  -494 %   ▁▂▁▃▁▁▂  breached
● airandspacehistory.com         availability  97.17 %  target 99.00 %  budget  -183 %   ▂▁▂▂▁▃▂  breached
● Orrery www                     availability  99.93 %  target 99.50 %  budget   86 %    ▇▇▇▇▇▇▆  meeting
  ...
TELEMETRY INTAKE
  ...
PLATFORM
  ...
```

- **Rows sort by budget left,** so what is closest to breaking is first, inside each group.
- **States:** meeting (budget left 25 % or more), at risk (under 25 %), breached (under 0), stale (the
  job's numbers are older than 15 minutes: grey, never green).
- **Each row** shows the SLI now, its target, the budget left as a share and as time ("3 h 10 min
  left of 3 h 22 min"), a 28-day sparkline of daily values, and links to its Grafana panel or Project
  page.
- **On a phone:** service and state on the first line, the numbers on the second, the sparkline under
  them.
- **Overview gains one card,** "Service levels": `<meeting> of <all> meeting`, red when one is
  breached, linking to the tab.
- **Projects pages** (Close Listening, Orrery, Evals, Websites) gain a "Service levels" band with that
  app's rows.
- **Not on the Hub:** alerts, budget burn rates, and the morning brief (the RFC's later step).

## 5. The build, in order

1. **The catalogue,** with every RFC entry and its query, and each query run once by hand against
   VictoriaMetrics: no SLI enters with a query that returns nothing.
2. **`hub-slo.js`,** a pure module like `hub-status.js`: the catalogue and query results in; ratios,
   budgets, states and sparklines out. `test_slo.js` with fixtures: meeting, at risk, breached, a
   query with no data (stale, not 100 %), the egress gate.
3. **The status job** runs it and writes `slo.json`, pushes the gauges, records its last success.
4. **The page:** the Levels tab, the Overview card, the Projects bands. `test_page.js` grows; a
   screenshot check at 360 px and at desktop width.
5. **Deploy** the usual way (the mini's checkout, `gen.sh`), then **verify** that `slo.json` is fresh,
   the three breached rows show red, and a number on the page matches the same query in Grafana.
6. **Docs:** the Hub README and the RFC's status.

About a day of work. Nothing changes in the observability stack itself.

## 6. Decisions for the operator

**Decided 2026-11-16:** 1-3 yes (the status job and JSON, a "Levels" tab, the three breached
endpoints red from day one). 4: start with `up` for the DGX models and LiteLLM and evolve from
there; the nightly pipeline's SLI from its last-run timestamp, as it is today.

1. The status job instead of recording rules (§2), and JSON in `infra/homelab-home/` instead of the
   RFC's `infra/observability/slo/catalogue.yaml`.
2. The tab's name and place: "Levels", between Sites and Hosts.
3. The three endpoints already breached: show them red from day one (recommended), or note them as
   known while each gets looked at.
4. The RFC's open questions: `up` alone for the DGX models and LiteLLM; the nightly pipeline's SLI.

## Not covered

- Why the three endpoints are under target: not looked at yet. Two are Umami trackers
  (`analytics.*`), one the Adobe Portfolio site; each needs its own check before anything is changed.
- Alerts and burn rates: the RFC's later step, by the operator's decision.
- SLAs.
