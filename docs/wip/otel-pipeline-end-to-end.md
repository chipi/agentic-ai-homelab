# Telemetry pipeline end to end — map, gaps, plan

→ becomes `docs/recipes/observability-correlation.md` (how to walk one request through every
tool) plus an ADR for the naming contract, once the segments below are done.

Started 2026-10-14. Covers every emitter in podcast_scraper, agentic-ai-homelab and orrery,
the collectors, the three Victoria backends, Grafana, GlitchTip and Langfuse. Every finding
below was measured on the live stack or read in code (file:line in the session notes); nothing
is inferred unless it says so.

## 1. The pipeline today

| Signal | Emitters | Path | Backend |
|---|---|---|---|
| Traces | podcast-api, podcast-pipeline, operator-public-api, player-api, player-mcp (Python OTel SDK, http/protobuf, 100% sampled); delivery ×3 (manual spans) | **direct OTLP** from the app to `homelab:10428/insert/opentelemetry/v1/traces` — no collector | VictoriaTraces v0.9.4, 7-day retention (default), no CPU cap |
| Metrics | app `/metrics` (instrumentator, `mcp_*`, `delivery_*`), node/cAdvisor/DCGM/vLLM exporters, Postgres/Redis exporters | Alloy scrape → `remote_write` (mini, DGX, prod VPS); fleets and cron scripts push `/api/v1/import/prometheus` | VictoriaMetrics v1.102.1, 6-month retention, ~21.6k series |
| Logs | every container's stdout; prod journal (sshd), Caddy, fail2ban; fleetd/signal-fleet/ci-ops jsonline pushes | Alloy `loki.source.docker/journal/file` → Loki push (label contract: `infra/observability/LOG-STANDARD.md`) | VictoriaLogs v1.52.0, 30 days, 2 CPUs |
| Errors | apps, browsers, DGX servers, delivery, LiteLLM (Sentry SDKs) | Sentry protocol → GlitchTip | GlitchTip (OTel trace id only as `tags.trace_id`) |
| LLM calls | LiteLLM callback, fleets, bugfix-fleet | Langfuse SDK | Langfuse (no OTel trace id) |
| Product analytics | player, viewer, orrery | Umami | Umami |

Volumes (24h, measured): ~88k spans across 7 services; ~35k log lines carry a trace id.

## 2. What is wrong (measured)

### Correlation (the reason a request cannot be walked end to end)
1. **Log → trace link never fires for app logs.** Grafana's VictoriaLogs derived field (and the
   Alloy `trace_id` stage) require `<32hex>-<16hex>` (traceparent shape). Apps write five other
   shapes: `trace=<id>` (access log, pipeline), `[trace_id=<id> span_id=<id> …]` (OTel log
   correlation), `"trace_id":"<id>"` (JSON events, delivery). Verified on two real player-api
   traces: line has the id, VictoriaTraces has the trace (4 spans), regex match = False.
2. **Trace → logs finds nothing.** The Tempo datasource's `tracesToLogsV2` query looks for a
   `trace_id` field (30 lines/day have it) or `request.headers.*` fields (0 lines). A plain
   phrase search for the id finds the lines. Verified: current query 0, phrase 1.
3. **player-mcp logs carry no trace id** (started without the `opentelemetry-instrument`
   launcher, so `OTEL_PYTHON_LOG_CORRELATION` does nothing).
4. **Two trace ids per request in GlitchTip**: Sentry's own `contexts.trace.trace_id` and the
   OTel id in `tags.trace_id`. signal-fleet looks up the Sentry one in VictoriaTraces
   (inferred miss — to verify).
5. **No browser → API trace**: browser Sentry has no tracing integration, sends no trace
   headers.
6. **No metric → trace exemplars** anywhere.
7. **Traces live 7 days, logs 30**: a trace id in a 2-week-old log line leads nowhere.

### Naming (services and environments)
8. `deployment.environment` missing on operator-public-api, player-api (staged by the deploy
   workflow but not passed into the container) and all three delivery workers.
9. Pipeline is `podcast-pipeline` in prod and `pipeline` in dev.
10. `delivery-worker` is one service.name for three different containers.
11. Label keys and values differ per signal: traces `service.name`/`deployment.environment`;
    logs `app`/`surface`/`env` (LOG-STANDARD); fleet metrics/logs `service`/`environment`
    with value `operations`; bugfix-fleet TS pushes have no labels at all.
12. Metric series without a `job` (≈700), `player_mcp` instance = container IP, laptop dev
    pushes with instance = checkout folder name.

### Backends
13. VictoriaMetrics is 52 minor versions behind (v1.102.1 → v1.154.0); search limit reached
    4,903 times (no timeouts).
14. VictoriaTraces v0.9.4 → v0.12.0 available; no retention set (7d default).
15. Pipeline one-shot runs' in-process metrics are never collected in prod.

## 3. Plan — segments (each: change → verify on live data → commit + push)

| # | Segment | Repos | Done when |
|---|---|---|---|
| S1 | **Naming contract** — one service.name per deployable, one environment vocabulary, same values in traces/logs/metrics; fix every emitter that breaks it (8–12) | podcast_scraper, homelab | every span, log stream and metric series of a service resolves to the same `service` + `environment` pair (checked by query) |
| S2 | **Trace ⇄ log correlation** — one Alloy stage + one Grafana derived field that read all five id shapes; tracesToLogs by phrase; trace ids in player-mcp logs (1–3) | homelab, podcast_scraper | from 3 real traces per service: log line shows "View trace" and the trace opens; trace "Logs for this span" returns its lines |
| S3 | **Errors and LLM calls join the walk** — GlitchTip events carry the OTel trace id where the fleet reads it; Langfuse traces carry it where possible (4) | podcast_scraper, homelab | a real GlitchTip error → its trace → its logs, by id, no guessing |
| S4 | **VictoriaTraces tuned** — upgrade, retention aligned with logs (30d, disk checked), CPU cap like the others, Tempo datasource features (service graph / span metrics only if VictoriaTraces supports them) (7, 14) | homelab | traces older than 7d resolve; Traces Drilldown + trace search timed before/after |
| S5 | **VictoriaMetrics tuned** — upgrade, concurrency/limits, cardinality hygiene, exemplars if supported end to end (6, 12, 13) | homelab, podcast_scraper | all 30 dashboards re-checked; query timings before/after; no job-less series |
| S6 | **End-to-end walkthroughs** — (a) player request → player-api → podcast-api; (b) pipeline run (`run_id`) → episode → enrichment → delivery email/push; (c) error → GlitchTip → trace → logs; (d) LLM call → Langfuse. Each gap found becomes a fix in S1–S5 | all | each walk done on live data with screenshots, every hop by id |
| S7 | **Docs** — fix drift (podcast OBSERVABILITY_RUNBOOK derived-field claim, LOG-STANDARD regex, dependency map, endpoints recipe, ADR-119 status), record the naming contract | both | strict docs builds green |

Not in scope unless asked: browser tracing (5) — it adds a Sentry/OTel integration to two
front-ends and sends trace headers cross-origin; listed so it isn't a silent gap.

## 4. Correlation ids (inventory to complete in S6)

| Id | Created by | Should appear in |
|---|---|---|
| trace id (W3C, 32 hex) | OTel SDK per request/run | spans, every log line of the request, GlitchTip `tags.trace_id`, events JSON |
| span id | OTel SDK | spans, OTel-format log lines, events JSON |
| `run_id` | pipeline CLI | pipeline logs `[run=…]`, `episode.process`/`enrichment.enricher` span attributes, events JSON, metrics? |
| `episode_id`, `feed_id` | pipeline | span attributes, events JSON |
| delivery `outbox` id / tenant | podcast-api outbox → delivery | delivery logs, `delivery.drain` span? (to check) |
| Sentry event id | GlitchTip | error ↔ trace link via `tags.trace_id` |
| Langfuse trace id | LiteLLM / fleets | (no join to OTel today) |

## 5. Status

- [x] Map (live + code), 2026-10-14
- [~] **S1 naming contract** — decided in [ADR-0010](../adr/ADR-0010-telemetry-naming-contract.md):
  OTel vocabulary (`namespace` / `service` / `environment`) declared once by each
  deployable; `environment=operations` stays for the fleets and self-monitoring (operator,
  2026-10-14). Phase A (add `service` + `environment` to every log source) done: mini live
  (800ae69); DGX deployed 18:15 UTC (config file only; ~74 duplicate lines from idle containers re-read on restart, left in place); prod base + drop-ins, orrery,
  ops events and dev naming are local commits for the next deploy; ci-ops-poller live
  from 17:55 UTC (its loop needed a restart to load 6dcf540), inbox live each cycle;
  orrery's drop-in pushed (8203ff4bb6b) and installed on prod: `service=orrery-web` verified. Phases B/C (identity from compose labels, consumers switch, old labels
  dropped) go with the deploy after. Traces: delivery workers named per worker (live),
  player/operator `deployment.environment` and metric `service` labels in podcast local
  commits.
- [~] **S2 trace ⇄ log** — one regex for all five id shapes in Grafana + Alloy: Grafana and
  the mini and the DGX live; prod (all four Alloy files: checked on the box, 0 matches)
  only with the next podcast deploy; trace → logs via a correlation
  (`backend/grafana/correlations/`); player-mcp gets OTel log correlation with the next
  deploy. Verified in the browser.
- [~] **S3 errors / LLM calls** — GlitchTip: the triage fleet now follows `tags.trace_id`
  (06c07e0; replay on 13 real issues: trace found 0 → 4, the rest labelled "not found" /
  "no trace_id", not errors). Langfuse: prod DGX calls reach Langfuse only after the
  next deploy (#2342 routes them through the gateway); none carry a run id or trace id.
  Operator chose "metadata to the gateway" — **not built yet**. Errors outside a span
  have no trace id (`run_id` tag: open).
- [x] **S4 VictoriaTraces** — v0.12.0, 30-day retention, 5 GiB cap, 72 h field lookbehind
  (live 2026-10-14; `3d` crash-looped it for ~2 min, fixed in bd4dc79). Search verified
  in Explore.
- [x] **S5 VictoriaMetrics** — v1.154.0 live; scrape targets, 30-day-old data and every
  host's freshness unchanged after the upgrade. No exemplars in VictoriaMetrics: metric →
  trace is panel links (live). Trace → metrics live.
- [x] **S6 end-to-end walkthroughs** (2026-10-14, on live data): (a) player-mcp -> player-api
  trace -> logs; (b) pipeline run -> 3 traces by `run_id` tag, 106 log lines (the new regex
  extracts all 3 trace ids from them; prod gets it with the next deploy); (c) GlitchTip error ->
  trace via `tags.trace_id`; (d) LLM call -> Langfuse by `session_id` (gateway, verified with a
  probe); (e) digest scheduler -> outbox -> delivery by `correlation_id` in all three hops'
  logs; delivery -> player-api is now one trace (traceparent, live) and the delivery event
  names the episodes (slug -> episode_id via the corpus catalog).
- [ ] S7 docs (LOG-STANDARD and the ops handbook's trace recipe already updated)

### Found on the way

- `delivery-events` never produced a span — **fixed** (dfe68d0, live: `delivery.events.poll`).
- The public operator (`operator-api-1` / `operator-viewer-1`) shipped no logs — **fixed** in a
  podcast local commit (own source in operator.alloy; next deploy), plus a drop rule for the
  viewers' healthcheck lines (~99% of compose-viewer-1's volume).
- The obs MCP looked up pipeline traces as `pipeline`; prod is `podcast-pipeline` (33.9k prod
  spans / 7 d vs 50 dev) — **fixed** in a podcast local commit.
- **Prod apps lost ~2.3% of span batches**: `homelab:10428` is lima's ssh forwarder; 7 of 300
  probes hung 12 s (no TCP connect), the TLS node `vtraces.` 0 of 180. Apps' endpoint moved to
  the TLS node in a podcast local commit (next deploy); player-obs reads through it verified.
- player-mcp logs could never carry a trace id (uvicorn's access line runs after the span) —
  **fixed** in a podcast local commit (the api's access-log middleware, shared).
- Alloy kept read positions inside its container: recreate = full replay. **Fixed**: named
  volume on the mini and the DGX (d30f70a), migrated without replay, recreate verified.
- The ci-ops-poller is one long-lived loop: a code change needs a restart (README now says so).
- Incident 2026-10-14 17:24–17:28: adding `service` on the mini's docker-source targets
  replayed 97,450 old lines; fixed (800ae69), duplicates deleted (exact filter, originals
  unchanged at 24,273,178). Rule now in LOG-STANDARD and ADR-0010.
