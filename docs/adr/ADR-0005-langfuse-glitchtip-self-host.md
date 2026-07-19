# ADR-0005 — Self-host LLM tracing (Langfuse) + error tracking (GlitchTip)

**Status:** Accepted (build pending per-stack bring-up approval)
**Date:** 2026-07-20
**ctx src:** this session; extends the self-hosted observability backend
(VictoriaMetrics/VictoriaLogs/Grafana) stood up 2026-07-19 — see
`infra/observability/backend/`. Operator drivers: cost/limits, data-local,
own-the-stack (same as the metrics/logs self-host).

## ctx

The self-hosted metrics + logs stack covers host/GPU/container health and log
browsing. Two concerns it does **not** cover:

1. **LLM/agent tracing** — how the harnesses (Claude Code, opencode, Pi) talk to
   models: prompts, completions, token usage, cost, latency, session/trace
   trees. This is the "monitor how harnesses talk to models" goal (fleet
   Phase 4). Metrics/logs lack the semantics (span tree, prompt/completion,
   per-call token+cost, session grouping).
2. **Application error/crash tracking** — exceptions + performance in app code
   (podcast scraper, etc.). Different from LLM traces.

Both wanted, same drivers as leaving Grafana Cloud.

## Decision

1. Self-host **Langfuse v3** for LLM/agent tracing → `infra/langfuse/`.
2. Self-host **GlitchTip** (NOT full Sentry) for error tracking →
   `infra/glitchtip/`. Sentry-SDK/DSN compatible, a fraction of the weight.
3. Both follow the established pattern: containerized in `infra/`, **Tailscale-
   only** exposure (per-port ACL grant), `.env` gitignored, images pinned,
   Mac-mini-portable.
4. **Langfuse capture path = deferred open decision** — LiteLLM proxy choke
   point vs OTEL/native per-harness. Stand Langfuse up first, wire second.
   Lean: LiteLLM proxy (uniform, provider-agnostic, full prompt/completion
   capture; cost = reconfigure each harness base URL once). Routing live harness
   traffic through a new proxy is its **own** change + approval.

## The stacks (weight is the headline)

| Stack | Containers | Components |
|---|---|---|
| **Langfuse v3** | ~6 | postgres, clickhouse, redis, minio (S3), langfuse-web, langfuse-worker |
| **GlitchTip** | ~4 | web, worker (celery), postgres, redis |
| ~~Full Sentry~~ | ~40 | Kafka, Snuba, Relay, ClickHouse, symbolicator, many workers — **rejected** |

Only the **web UIs** publish host ports; datastores stay on the internal compose
bridge. Fine on the DGX (RAM plenty). On the Mac mini later, Langfuse is the
heaviest component — watch RAM (ClickHouse + Postgres + MinIO).

## Alternatives considered

- **Full Sentry self-hosted** (`getsentry/self-hosted`): ~40 containers, 16GB+
  RAM, painful upgrades. Rejected — overkill; GlitchTip gives the same SDK/DSN
  developer experience at ~4 containers.
- **Langfuse Cloud / Sentry SaaS**: rejected — same cost/data-local/own-stack
  drivers that moved us off Grafana Cloud.
- **Langfuse v2** (lighter, Postgres-only): rejected — deprecated upstream in
  favor of v3; don't build on a sunset architecture.
- **OTEL-only into existing Grafana/VM** (no dedicated LLM tool): rejected —
  metrics/logs can't represent trace trees / prompt-completion / per-call cost.
- **Phoenix (Arize) / Helicone / OpenLLMetry** as Langfuse alternatives:
  considered; Langfuse chosen for roadmap fit, self-host maturity, built-in cost
  tracking + prompt management.

## Consequences / trade-offs

- Two new **stateful** stacks: operational burden (upgrades, backups). A second
  ClickHouse now runs (Langfuse) alongside VictoriaMetrics — acceptable,
  different purpose.
- **Auth to manage:** unlike VM/VictoriaLogs (no auth, tailnet-boundary),
  Langfuse + GlitchTip have their own login/secrets → gitignored `.env`,
  strong admin creds, `NEXTAUTH_SECRET`/`SECRET_KEY` etc.
- **Portability is heavier than VM:** Postgres/ClickHouse/MinIO volumes must
  migrate (or accept a fresh start — traces/errors are append-only, so
  fresh-start loses history).
- **Port + ACL planning:** the tailnet ACL is a per-port allowlist. Grafana
  already holds `:3000`, so Langfuse web needs a *different* published port
  (e.g. `3001`/`4000`) and GlitchTip another (avoid taken `8080`/`9000`) — each
  needs its own ACL grant. Datastores need no grant (bridge-internal).
- New deps → pinned + recorded here (satisfies the deps/big-bets rules).
- Capture-path deferral means Langfuse ingests nothing until wired — acceptable.

## Non-goals

- Not replacing metrics/logs — complementary.
- Not full Sentry feature parity.
- Not routing live harness/app traffic through a new proxy in this ADR — that's
  a separate change with its own approval.
- Not building custom LLM-trace tooling.

## Rollout (when approved, per-stack)

1. **Langfuse** — `infra/langfuse/` compose + `.env.example`; pin images;
   internal datastores + web on a chosen tailnet port; ACL grant; bring up on
   DGX (per-instance approval); create org/project; note the ingest keys.
2. **GlitchTip** — `infra/glitchtip/` compose + `.env.example`; ACL grant for
   its web port; bring up; create org/project → DSN.
3. **Capture wiring (Langfuse)** — separate decision (LiteLLM vs OTEL) + change.
4. **Handover docs** — `docs/wip/` for each, matching the observability handovers.

Related: the observability self-host + tailnet-ACL patterns in
`infra/observability/backend/README.md` and the VPS handovers under `docs/wip/`.
