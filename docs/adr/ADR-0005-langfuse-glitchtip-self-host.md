# ADR-0005 — Self-hosted observability platform: metrics/logs, LLM tracing, error tracking

**Status:** Accepted. Metrics + logs **implemented** 2026-07-19; Langfuse +
GlitchTip **build pending** per-stack bring-up approval.
**Date:** 2026-07-20 (metrics/logs recorded retrospectively)
**ctx src:** this session + the 2026-07-19 observability build
(`infra/observability/`). Operator drivers: cost/limits, data-local,
own-the-stack.

## ctx

One initiative — self-host the observability platform — spanning three signal
types the homelab needs:

1. **Metrics + logs** — host/GPU/container health + log browsing. *Built
   2026-07-19; recorded here retrospectively.*
2. **LLM/agent traces** — how the harnesses (Claude Code, opencode, Pi) talk to
   models: prompts, completions, token/cost, latency, session trees. Metrics/
   logs can't represent this (no span tree / prompt-completion / per-call cost).
3. **Application errors/crashes** — exceptions + performance in app code
   (podcast scraper, etc.).

Shared posture for all three: containerized under `infra/`, **Tailscale-only**
exposure (per-port ACL grant), `.env` gitignored, images pinned, Mac-mini-
portable. Grafana is the pane of glass for metrics/logs; Langfuse and GlitchTip
bring their own UIs.

## Decision

### 0. Metrics + logs — VictoriaMetrics + VictoriaLogs + Grafana (retrospective)

Implemented 2026-07-19, replacing **Grafana Cloud**:

- **VictoriaMetrics** (TSDB, `:8428`) + **VictoriaLogs** (logs, `:9428`) +
  **Grafana OSS** (`:3000`) — `infra/observability/backend/`, one host (DGX now,
  Mac mini later).
- **Alloy collectors** on each host (`infra/observability/`) scrape host/GPU
  (DCGM)/containers (cAdvisor)/vLLM/Ollama and push metrics (`remote_write`) +
  Docker logs (Loki push protocol) over Tailscale. Env-driven sink
  (`REMOTE_WRITE_URL`/`LOGS_WRITE_URL`).
- **Dashboards-as-code**, provisioned from git; **modern React panels only**
  (dropped the Angular DCGM/cAdvisor dashboards — Grafana 11 disables Angular).
- **VPS/app dashboards federated:** the podcast repo pushes its dashboards to the
  shared Grafana via a service-account token into a dedicated folder (API push).

### 1. LLM/agent tracing — Langfuse v3 → `infra/langfuse/`

### 2. Error tracking — GlitchTip (NOT full Sentry) → `infra/glitchtip/`

Sentry-SDK/DSN compatible at a fraction of the weight.

### 3. Both new stacks follow the patterns above (tailnet-only, ACL, pinned, portable).

### 4. Langfuse capture path = deferred open decision

LiteLLM proxy choke point vs OTEL/native per-harness. Stand Langfuse up first,
wire second. Lean: LiteLLM proxy (uniform, provider-agnostic, full prompt/
completion capture; cost = reconfigure each harness base URL once). Routing live
harness traffic through a new proxy is its **own** change + approval.

## The stacks (weight is the headline)

| Stack | Containers | Components | State |
|---|---|---|---|
| **Metrics/logs backend** | 3 | VictoriaMetrics, VictoriaLogs, Grafana | **live** |
| **Collector** (per host) | 4 | Alloy, dcgm-exporter, cAdvisor, ollama-metrics | **live** |
| **Langfuse v3** | ~6 | postgres, clickhouse, redis, minio (S3), web, worker | pending |
| **GlitchTip** | ~4 | web, worker (celery), postgres, redis | pending |
| ~~Full Sentry~~ | ~40 | Kafka, Snuba, Relay, ClickHouse, symbolicator, workers | **rejected** |

Only web UIs / ingest publish host ports; datastores stay on the internal
compose bridge. Fine on the DGX. On the Mac mini later, Langfuse is the heaviest
component — watch RAM (ClickHouse + Postgres + MinIO).

## Alternatives considered

- **Grafana Cloud / Langfuse Cloud / Sentry SaaS**: rejected — cost/limits,
  data leaves infra, don't own the stack. (Grafana Cloud was the incumbent we
  migrated off.)
- **Prometheus** (vs VictoriaMetrics): VM chosen — single-node, ~7× less RAM,
  purpose-built remote-write sink, PromQL-compatible.
- **Loki** (vs VictoriaLogs): VictoriaLogs chosen — same VM family, lighter,
  LogsQL. Security identical (tailnet + ACL, no store auth).
- **Full Sentry self-hosted**: ~40 containers, 16GB+ RAM, painful upgrades.
  Rejected — GlitchTip gives the same SDK/DSN experience at ~4 containers.
- **Langfuse v2** (Postgres-only, lighter): rejected — deprecated upstream for
  v3; don't build on a sunset architecture.
- **OTEL-only into Grafana/VM** (no dedicated LLM tool): rejected — no trace-
  tree / prompt-completion / per-call cost semantics.
- **Phoenix (Arize) / Helicone / OpenLLMetry**: Langfuse chosen for roadmap
  fit, self-host maturity, built-in cost tracking + prompt management.

## Consequences / trade-offs

- **Realized (metrics/logs):** off Grafana Cloud; tailnet ACL is per-port, so
  each service needs a grant (done: `3000`/`8428`/`9428`); no store-level auth
  (tailnet is the boundary); DGX collector cut over from Cloud → VM.
- **New (Langfuse/GlitchTip):** two stateful stacks → operational burden
  (upgrades, backups). A second ClickHouse runs (Langfuse) alongside VM —
  acceptable, different purpose.
- **Auth to manage:** unlike VM/VictoriaLogs, Langfuse + GlitchTip have their own
  login/secrets → gitignored `.env`, strong admin creds, `NEXTAUTH_SECRET` /
  `SECRET_KEY` etc.
- **Portability heavier than VM:** Postgres/ClickHouse/MinIO volumes must migrate
  (or accept a fresh start — traces/errors are append-only, so fresh-start loses
  history).
- **Port + ACL planning:** Grafana holds `:3000`, so Langfuse web needs a
  different port (e.g. `3001`/`4000`) and GlitchTip another (avoid taken
  `8080`/`9000`) — each needs its own ACL grant. Datastores need none.
- New deps → pinned + recorded here (satisfies the deps/big-bets rules).
- Capture-path deferral means Langfuse ingests nothing until wired — acceptable.

## Non-goals

- The three signal types are complementary — none replaces another.
- Not full Sentry feature parity.
- Not routing live harness/app traffic through a new proxy in this ADR — that's a
  separate change with its own approval.
- Not building custom LLM-trace tooling.

## Rollout

- **Metrics + logs:** done (2026-07-19). See `infra/observability/backend/README.md`
  and the VPS handovers under `docs/wip/`.
- **Langfuse** — `infra/langfuse/` compose + `.env.example`; pin images; web on a
  chosen tailnet port + ACL grant; bring up on DGX (per-instance approval);
  create org/project; note ingest keys. Then capture wiring (separate decision).
- **GlitchTip** — `infra/glitchtip/` compose + `.env.example`; ACL grant for its
  web port; bring up; create org/project → DSN.
- **Handover docs** in `docs/wip/` for each, matching the observability handovers.
