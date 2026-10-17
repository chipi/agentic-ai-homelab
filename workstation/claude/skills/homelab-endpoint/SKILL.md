---
name: homelab-endpoint
description: Resolve a homelab service name to its real endpoint URL and how to call it — DGX model servers, the mini's observability and LLM gateway services, prod VPS services. Points at the operations handbook, which holds the one maintained table. Use when an agent or client needs to point at a homelab service, when writing config that consumes one, or when asked "what's the URL for X". Read-only.
---

# homelab-endpoint

The endpoints live in one place, the operations handbook
(`agentic-ai-homelab/docs/recipes/agent-access.md`). This skill used to keep its own
table; it went stale (ports and GPU modes changed on the DGX), so it now points there.

| Need | Where |
|---|---|
| Which host runs what, how to get on it | handbook section 0 |
| Credentials for a service (load from file, never print) | handbook section 0, "Credentials" |
| A mini service (Grafana, Victoria*, Umami, GlitchTip, Langfuse, LiteLLM) | handbook sections 1–9: each heading has the loopback port and tailnet URL |
| DGX model servers (whisper, pyannote, prod vLLM, translate, moss) and their API keys | handbook section 13 |
| Tailnet names for the web services | `docs/recipes/observability-endpoints.md` |
| The `${VAR}` substitution convention for config that consumes a service | `docs/recipes/consuming-homelab-services.md` |

## Resolve

1. Read the handbook row for the service; give the base URL, the model name if any, and the
   auth header (`Authorization: Bearer …`, with the key's source, never its value).
2. A DGX vLLM answers only in the right GPU mode: check with the `gpu-mode` skill
   (`--mode-only`) before assuming the port is live.
3. If the handbook and the live host disagree, the host wins: fix the handbook row.
