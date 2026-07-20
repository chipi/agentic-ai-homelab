# RFC-0001 — LiteLLM proxy as the Langfuse capture layer

**Status:** Proposed
**Date:** 2026-07-20
**Relates to:** ADR-0005 §4 (Langfuse capture path deferred). Langfuse is live at
`infra/langfuse/` (project `agents`, `http://100.69.49.126:4000`) but ingests
nothing until wired.

## Motivation

Capture how the harnesses (Claude Code, opencode, Pi) and apps talk to models —
prompts, completions, tokens, cost, latency, trace trees — **uniformly**,
provider-agnostic, with a **dev/prod** split (Mac coding agents + podcast app =
`dev`; VPS = `prod`). Need to decide *how* traffic is captured and fed to
Langfuse.

## Proposal

Put a **LiteLLM proxy** in the request path as the single choke point. Clients
point their base URL at LiteLLM; it routes to the real providers (Anthropic,
OpenRouter, OpenAI, local vLLM) and logs every call to Langfuse via its native
callback. One config → uniform capture + cost tracking, for any harness/provider.

### Topology (the load-bearing choice): proxy-local, Langfuse-central

Run LiteLLM **on each client host** (Mac for dev, VPS for prod), each logging to
the **central** Langfuse on the DGX. Why:

- **No new single-point-of-failure on the critical path.** The Mac coding agents
  currently hit cloud providers directly. A *central* proxy on the DGX would make
  every model call `Mac → DGX → provider` — if the DGX is down, your primary
  coding work stops. A *local* proxy keeps the request path on `localhost →
  provider`; only the async Langfuse logging crosses the tailnet, and it's
  best-effort — if Langfuse/DGX is down, LiteLLM still serves.
- **dev/prod falls out naturally:** the Mac proxy tags `dev`, the VPS proxy tags
  `prod`. Central Langfuse aggregates both.

### Per-harness wiring

- **Claude Code:** `ANTHROPIC_BASE_URL` → LiteLLM (Anthropic-format endpoint).
  **Main risk** — see Open Questions #2.
- **opencode:** already OpenRouter; point its provider base URL at LiteLLM
  (OpenAI-compatible), keep the OpenRouter roster as LiteLLM model routes.
- **Pi:** set its model base URL at LiteLLM.
- **Podcast app:** its LLM client base URL → local LiteLLM (dev on Mac, prod on VPS).

### Langfuse integration

LiteLLM's native callback: `success_callback: ["langfuse"]` +
`LANGFUSE_PUBLIC_KEY`/`SECRET_KEY`/`HOST` (→ `http://100.69.49.126:4000`, project
`agents`). Logs prompt/completion/tokens/cost/latency; supports metadata/tags
(set `environment`). Cost from LiteLLM's pricing map.

### Deployment shape

`infra/litellm/` — small compose (proxy + `config.yaml`). Runs on Mac (dev) and
VPS (prod). Provider keys in config/env (secrets, gitignored). Proxy listens on
localhost — no tailnet ACL for the proxy itself (only Langfuse ingest `4000`,
already needed).

## Open questions

1. **Topology** — proxy-local (recommended) vs central-on-DGX. Confirm.
2. **Claude Code through LiteLLM** — does LiteLLM's Anthropic passthrough preserve
   prompt caching, beta headers, tool use, and extended thinking without
   degrading Claude Code? **SPIKE required before committing.** If it degrades the
   coding experience, Claude Code stays direct (uncaptured, or usage-only via its
   own OTEL) and we only route opencode/Pi/apps.
3. **Local vLLM** — route the DGX vLLM calls through LiteLLM too (unified traces)
   or leave direct?
4. **Key management** — LiteLLM holds real provider keys on Mac + VPS; how stored
   (env, `config.yaml`, secret store)?
5. **dev/prod granularity** — one project `agents` with `environment` tags, or
   separate Langfuse projects per env/harness?
6. **Mac runtime** — LiteLLM as a launchd background service vs docker; latency +
   lifecycle on the laptop.

## Alternatives considered

- **OTEL / native per-harness** (no proxy): point each harness's OTLP/SDK at
  Langfuse. No request-path hop, but thinner data (Claude Code OTEL = usage
  metrics/logs, not full prompt/completion) and per-harness setup. Good **fallback**
  for any harness that breaks through LiteLLM (see #2).
- **Central LiteLLM on the DGX:** one config, but path-critical DGX dependency for
  the Mac's coding agents. Rejected as default on availability grounds.
- **Provider-native logging / OpenRouter dashboards:** partial, per-provider, not
  unified, not self-hosted.
- **Hand-instrument the Langfuse SDK** in the podcast app only: misses the
  harnesses entirely.

## Discussion

- **2026-07-20 (initial):** Langfuse stood up; capture deferred in ADR-0005.
  Proposing proxy-local topology to avoid making the DGX a single-point-of-failure
  on the Mac's coding critical path. The one thing that could sink the whole
  "capture Claude Code via proxy" idea is #2 — so a spike on Claude-Code-through-
  LiteLLM should come before any `infra/litellm/` build.
