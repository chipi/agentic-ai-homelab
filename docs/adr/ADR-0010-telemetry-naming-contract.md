# ADR-0010 — One telemetry naming contract, set once at the source

**Status:** Accepted (2026-10-14). Phase A shipped; phases B and C go with the next
podcast_scraper deploy after it.
**Date:** 2026-10-14

## Context

Logs, traces and metrics name the same service with different keys and values, so no
single filter follows a service across the three (measured 2026-10-14):

| Signal | Service key | Environment key | Values |
|---|---|---|---|
| Traces | `service.name` | `deployment.environment` | `player-api`, `podcast-pipeline` … / `prod`, `dev` |
| Metrics | `service` (some jobs), `job` | `environment` | as traces, where set |
| Logs, prod VPS | `app` + `surface` (ADR-121, podcast_scraper) | **none** | `player` + `api` |
| Logs, mini | `container` only | `env` | `prod` |
| Logs, DGX | `container` only | `env` | `production` |
| Logs, CI events | `app=podcast_scraper` | `env` | `ci` |

`app` is a product group (`app=player` covers api, mcp, app, obs and the digest
scheduler). The log labels are derived in each collector by container-name regexes in
per-app drop-ins, which is how ADR-121 keeps the two `api` containers apart.

## Decision

**One vocabulary, the OpenTelemetry resource attributes, identical in every signal:**

| Key | Meaning | Examples |
|---|---|---|
| `namespace` (OTel `service.namespace`) | product | `podcast`, `player`, `orrery`, `delivery`, `litellm`, `homelab` |
| `service` (OTel `service.name`) | one deployable | `player-api`, `podcast-pipeline`, `delivery-email` |
| `environment` (OTel `deployment.environment`) | `prod`, `dev`, `ci` for the apps; `operations` for the observers | |
| `instance` | the box | `prod-podcast`, `homelab`, `dgx-llm-1` |

`operations` stays the environment of the fleets and the stack's self-monitoring (fleetd,
signal-fleet, bugfix-fleet, host/telemetry alerts), as designed in
`signal-fleet/SIGNALS.md` (2026-07-24): their own telemetry stays out of the monitored
apps' `prod`/`dev` filters. (Their self-triage guard is `meta="true"` plus a separate
GlitchTip project, not the environment.)

**Identity is declared once, by the deployable, and copied by every collector:**

- Each compose service sets `OTEL_SERVICE_NAME` and
  `OTEL_RESOURCE_ATTRIBUTES=service.namespace=…,deployment.environment=…` (traces), and
  the same three values as container labels (`telemetry.service`,
  `telemetry.namespace`, `telemetry.environment`).
- Alloy (logs) and the scrape configs (metrics) read those container labels with **one
  generic rule** per box. No per-app container-name regexes and no `surface`.
- Containers that aren't ours (Postgres, Redis, Caddy, vLLM) get the same labels in
  their compose files.
- Processes started without compose name themselves in code (`init_otel`'s default:
  the CLI is `podcast-pipeline`, the server `podcast-api`).

**Log labels are set after the log source, never on its targets.** `loki.source.docker`
and `loki.source.file` key their read positions by target labels. A new target label
makes every container a new target, which re-reads its whole log. On the mini on
2026-10-14 that wrote 97,450 duplicate lines, deleted the same day. The rule goes in a
`loki.relabel` after the source.

## Migration

**Phase A: add, break nothing. Shipped 2026-10-14 (podcast/orrery parts ride the next deploy).**
Every log source gains `service` + `environment` next to the old labels:

- mini: `infra/observability/hosts/homelab/config.alloy` (live);
- DGX: `infra/observability/config.alloy` (with the DGX converge, plus `HOMELAB_ENV=prod`);
- prod VPS: podcast_scraper `base.alloy` `loki.relabel "naming"`, orrery `orrery.alloy`;
- event pushers: podcast `emit_ops_event.sh`, `ci-ops-poller`, the signal-fleet inbox;
- dev pushes: `init_otel` names each process.

**Phase B: identity at the source. With the deploy after A.**

1. Compose files in podcast_scraper, orrery and homelab get the three `telemetry.*`
   labels and `service.namespace` in `OTEL_RESOURCE_ATTRIBUTES`.
2. One generic Alloy rule per box maps the labels to `service` / `namespace` /
   `environment` (after the source). The per-app drop-ins keep only their keep-filters.
3. Metrics: the same labels on scrape targets; pushed metrics (fleets, delivery) add
   `namespace`.
4. Consumers switch to the new keys:
   - 13 dashboard and alert files (73 uses of `app`, `surface` and `env`, counted
     2026-10-14);
   - signal-fleet `correlate.py`;
   - the podcast_obs MCP (`obs_surface` is built on `surface`);
   - the o11y-review skill;
   - the smoke/deploy workflows.
   - During the 30-day overlap a query that needs older history ORs the old labels.

**Phase C: drop the old labels.** After every box runs phase B and 30 days have passed
(log retention), remove `app`, `surface` and `env` from the collectors and the OR
fallbacks from queries. LOG-STANDARD then documents only the new contract, and
ADR-121's naming section is marked superseded in podcast_scraper.

## Consequences

**Positive**

- One filter (`service:player-api`, `environment:prod`) works in logs, traces and
  metrics; the trace→logs, logs→trace and trace→metrics links key off the same
  values.
- Adding a service needs no collector change: its compose file declares it.
- The product grouping survives as its own key instead of a name prefix.

**Negative**

- Phase A leaves two vocabularies side by side until phase C.
- Phase B touches four repos and two deploy windows (prod VPS, DGX).
- Queries over history older than the switch need the old labels for up to 30 days.

**Neutral**

- Stream count is unchanged: `service` maps one-to-one onto the existing
  `app`+`surface` or `container` streams.

## Alternatives considered

- **Add `service`/`environment` and keep `app`/`surface` for good (phase A only).**
  Nothing breaks, but two vocabularies stay forever, and every new query picks one.
- **Rename `app`/`surface`/`env` to `service`/`environment` and drop `app`.** One
  vocabulary, but the product grouping becomes a name-prefix match that already fails
  (`operator-public-api` is the podcast product). Rejected for losing the grouping.
- **Ship app logs over OTLP with the SDK resource.** Labels by construction, but it adds
  an OTel logs pipeline to every app and still needs collector rules for the containers
  that aren't ours. Container labels get the same result for every container.

## References

- [Telemetry pipeline end to end](../wip/otel-pipeline-end-to-end.md): the map, gaps and
  segments this belongs to.
- `infra/observability/LOG-STANDARD.md`: the log label contract (updated for phase A).
- podcast_scraper `docs/adr/ADR-121-one-node-alloy-per-box-app-rule-dropins.md`: the
  `app`/`surface` naming this supersedes in phase C.
- `signal-fleet/SIGNALS.md` 2026-07-24: why the fleets use `environment=operations`.
