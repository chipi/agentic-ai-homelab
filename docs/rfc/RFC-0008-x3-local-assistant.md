# RFC-0008 — A local assistant on the X3, and the X3 as a deployment surface

**Status:** Proposed (2026-11-03)
**Relates to:** D-0005 and D-0007 (LibreChat picked, then removed from scope),
[`infra/observability/hosts/x3/`](https://github.com/chipi/agentic-ai-homelab/tree/main/infra/observability/hosts/x3)
(the X3's collector), the [agent access handbook](../recipes/agent-access.md), ADR-0009 (Docker on
the mini), the eval harness's triage results (`eval-harness/research/internal/TRIAGE_RESULTS_LIVE.md`).

## Motivation

The operator wants a smaller LLM running on owned hardware as a day-to-day assistant:

- for the homelab: questions about the stack, the runbooks, alerts, logs and metrics;
- as a personal assistant: drafting, notes, summaries, quick questions;
- as a helper on projects;

on their own infrastructure, private by default, reachable from the phone.

Two hosts could run it: the DGX Spark and the X3 (GMKtec EVO-X3). Until now the X3 has been a
workstation with a research collector on it, not a place services are deployed to. Running an
always-on assistant there makes it a third deployment surface next to the Mac mini and the DGX,
and that needs the same treatment the other two have: from the repo, through deploy, to running
and watching it.

## Facts this rests on (measured 2026-11-03)

| | DGX Spark (NVIDIA GB10) | X3 (AMD Ryzen AI Max+ 395, Radeon 8060S) |
|---|---|---|
| Unified memory | 121 GB, **16 GB available** in prod mode (`free -g`) | 124 GB, **70 GB available** (`free -g`) |
| In use | prod-vllm 26 GB, translate 30 GB, pyannote 3 GB, moss 2 GB, whisper 1.4 GB (`nvidia-smi`) | the desktop, the operator's dev agents, the eval harness's Ollama |
| Always serving? | No: `gpu-mode-swap` changes what runs (prod / ollama / code / research) | Yes, while the machine is on |
| Engine | vLLM: fast prefill, prefix cache, batching | Ollama 0.40.13 (llama.cpp), run by the eval harness as a long-job on `127.0.0.1:11434` |
| Speed | Qwen3-30B-A3B on vLLM, 30 days: first token 230 ms median / 1.8 s p95 on 4.3k-token prompts, 53 tokens/s per stream | Ollama, all models, 30 days: output 47 tokens/s, prompt 549 tokens/s (medians from its timing log lines) |
| Models on disk | Ollama: 27 families (qwen3, qwen3.5, qwen3.6, gpt-oss, gemma4, nemotron-3.5, …) | Ollama, 484 GB: 15 tags from llama3.1:8b to nemotron-3.5-super:120b |
| Docker | yes | yes (`websites-preview` runs); the X3 collector's README says it runs none, which is out of date |

Quality evidence: the eval harness's triage experiment (65 owner-labelled decisions). The DGX
vLLM Qwen3-30B-A3B leads on combined cost (0.400). The harness says plainly that the order is not
a ranking at this size: 50 arms are not separated from the leader. Hosted models (Sonnet, Haiku,
GPT, Gemini) sit in the same band. There is no assistant-style eval (Q&A over docs, tool use) yet.

## Use cases, in order

| # | Use case | Needs | Local fit |
|---|---|---|---|
| 1 | **Homelab assistant**: "what is the endpoint for X", "how do I restart Y", "what does this alert mean" | the handbook and runbooks as context; tool calls | Good: private, and the answers are in our own docs |
| 2 | **Reading o11y through tools**: "what happened overnight", "is anything red", "visitors on orrery this week" | read-only tools over VictoriaMetrics / VictoriaLogs / Grafana / GlitchTip / Umami | Good for summaries; the skills already hold the queries |
| 3 | **Personal assistant**: drafting, notes, summaries, quick questions, from the phone | a chat UI, history, fast replies | Good |
| 4 | **Home automation**: "is the garage open", later "turn off the lights" | Home Assistant tools | Reads are fine; writes need a confirmation design |
| 5 | **Project helper**: questions about code and designs | top-tier reasoning, long context | Weak: a helper, not a replacement for Claude / opencode / coder-next |

Version 1 covers 1–3, read-only.

## Proposal

### 1. The X3 becomes a deployment surface

What the mini and the DGX already have, the X3 gets too:

| Concern | Mini | DGX | X3 (proposed) |
|---|---|---|---|
| Where it lives in the repo | `infra/mini-*`, `infra/observability/backend/` | `infra/dgx/`, `infra/vllm/` | **`infra/x3/`** with its own `AGENTS.md` and README |
| Deploy checkout | `~/agentic-ai-homelab` | `/home/ops/agentic-ai-homelab` (user `ops`) | **a separate checkout on `main`** (e.g. `~/deploy/agentic-ai-homelab`), never the dev tree at `/work/agentic-ai-homelab`, so uncommitted edits never go live |
| How services run | launchd + Docker (prod engine) | Docker compose in place | **systemd user units** linked from the deploy checkout (the pattern `alloy-research` already uses); Docker only where a service ships as containers |
| Deploy | `git pull` + kickstart / compose | `git pull` + compose | `git pull` + `systemctl --user restart <unit>` |
| Observability | Alloy, VictoriaMetrics | Alloy, DCGM, cAdvisor | Alloy already runs (`alloy-research`): add the assistant's Ollama log and a probe |
| Health | probes, alerts | probes, alerts, `gpu-mode` | a blackbox probe on the assistant endpoint, an alert, a lamp on the hub (Hosts → X3) |
| Access recipe | handbook | handbook | handbook section + `host-run x3` |
| Undo | per stack | per stack | `systemctl --user disable --now <unit>`, remove the link |

Two rules come with it:
- **Separate from the eval harness.** The assistant gets its own Ollama instance (own port, e.g.
  `11435`, own `OLLAMA_KEEP_ALIVE`) reading the same model directory. Sharing the harness's
  instance would add load to its timed runs, and an eval could evict the assistant's model.
- **The workstation comes first.** Memory caps on the unit (`MemoryHigh` / `MemoryMax`), one
  resident model, and the heavy model loaded on demand only.

### 2. Models

| Role | Model | Memory | Why |
|---|---|---|---|
| **Assistant (v1)** | `qwen3:30b-a3b-instruct-2507-q4_K_M` | 18 GB | Leads the triage eval; 3B active parameters, so fast; tool calling; 262k native context (run at 32k) |
| Candidate, same shape | Qwen3.6-35B-A3B | ~21 GB | Newer; on the DGX's disk; no score in the harness yet |
| "Think harder", on demand | `gpt-oss:120b` | 65 GB | Strong tool use, adjustable reasoning, 5.1B active; loads only when asked, unloads after a few minutes |
| Small, resident (routing, classification) | `nemotron-3.5-bolt:e4b` or `gemma4:12b` | 8 GB | Cheap enough to keep loaded |
| Retrieval over the docs (v2) | an embedding model | ~1 GB | Not installed; pulling one needs the operator's go |

The benchmarks (speed at 4k / 20k context, assistant-style quality) come after the use cases work,
per the operator.

### 3. One gateway

The mini's LiteLLM gets aliases, `assistant` and `assistant-heavy`, routed to the X3 over the
tailnet, each client with its own capped virtual key. Every client (chat UI, opencode, pi, scripts)
uses the same endpoint; Langfuse traces it; the hub's Spend tab shows it as an Ollama source.

### 4. Chat UI: revisit LibreChat (D-0007)

**What LibreChat is:** an open-source, self-hosted chat application. It is a harness for chat the
way Claude Code or opencode is a harness for coding: it has no model of its own. It holds
conversations, routes to models, calls tools, and runs agents. Per its documentation:
- **Custom OpenAI-compatible endpoints:** it points at LiteLLM, so it can use every local and
  OpenRouter model through one gateway.
- **MCP servers**, configured in `librechat.yaml` or added at runtime, usable in chat or by
  **agents**. An agent is a saved prompt, model and toolset.
- **Chat with files (RAG API):** needs extra services, a RAG API and a vector database.
- **Authentication:** email, LDAP, SAML or OAuth / OIDC; registration can be closed after the
  first user.
- **Conversation search:** through Meilisearch.

**Not verified yet:** voice input through an OpenAI-compatible speech-to-text endpoint, which
would be our own faster-whisper on the DGX.

**Why D-0007 dropped it, and what changed.** In June LibreChat fronted one coder model, and Chatbox
(a phone app, no server) did the same job with nothing to maintain. Now there is a gateway with
every model behind it, MCP tools worth calling (the stack's own data), whisper for voice, and an
assistant use case. Chatbox can't call our tools. Whether that earns the maintenance is this RFC's
main question.

**The LibreChat running on the DGX today** is a leftover from June. Its files are untracked; the
image is a floating `librechat-dev-api:latest` (v0.8.6). It points only at coder-next (:9000, down
in prod mode). Its `.env` names OpenAI, Anthropic and Google API keys (names checked, values not
read). Whichever way this RFC goes, that instance should be retired or replaced, and the keys
checked and rotated if still live. That is a separate, approved step.

**Placement:** the mini is the always-on service host (Grafana, LiteLLM, Langfuse, GlitchTip and
Umami already run there). LibreChat itself is small: an API server, MongoDB and Meilisearch. The
model stays on the X3.

### 5. Mobile

The phone is on the tailnet (Tailscale app). LibreChat is served with Tailscale Serve under a
tailnet HTTPS name, the way the hub is (`hub.tail6d0ed4.ts.net`), and installed as a home-screen
web app. Nothing is exposed to the internet. Chatbox, pointed at the LiteLLM `assistant` alias,
remains the zero-maintenance fallback (no tools).

### 6. Integrations (MCP tools), read-only in v1

| Integration | What it answers | How |
|---|---|---|
| **Hub / VictoriaMetrics / VictoriaLogs** | "is anything red", "what happened overnight", "spend this week" | a read-only query tool; the hub's own queries as named tools |
| **Grafana** | alerts firing, dashboard panels | Grafana's MCP server with a viewer token |
| **GlitchTip** | "new errors since the deploy" | its Sentry-compatible API, read-only token (the `deploy-verify` logic) |
| **Umami** | "visitors on orrery this week" | its API, read-only |
| **Close Listening** | search the podcast corpus; prod health | the project's existing MCP servers (corpus search, o11y) |
| **Handbook and runbooks** | "how do I …" | the repo docs as files (v1), retrieval (v2) |
| **Home Assistant** | "is the garage open"; later actions | Home Assistant's MCP server integration; read-only first, actions only with a confirmation design |
| **GitHub** | "open PRs", "what failed in CI" | read-only token |

**Prompt injection:** tool results (logs, issues, web pages) can carry instructions. Read-only
tools bound the damage. Write tools (Home Assistant actions, GitHub writes) wait for a design
where the user confirms each action.

## Non-goals

- Replacing Claude Code / opencode for project work.
- Changing what the DGX serves, or using its production model for the assistant.
- Fine-tuning, or training anything.
- Exposing anything outside the tailnet.
- Benchmarks before the use cases run (they come after, per the operator).

## Open questions

1. **LibreChat or not** (D-0007 revisited): hands-on time with tools wired in decides it.
   Fallback: Chatbox plus the gateway, no tools.
2. **Where LibreChat runs:** the mini (always-on service host) or the X3 (next to the model).
3. **Is the X3 always on and reachable?** Sleep settings are unchecked. If it sleeps, the
   assistant needs a fallback route in LiteLLM (e.g. to an OpenRouter model, flagged in the UI as
   not local).
4. **Memory headroom on the X3** under the operator's peak dev load: what cap to set for the
   assistant unit.
5. **The leftover DGX LibreChat:** retire it, and check its provider keys.
6. **Voice:** STT through our faster-whisper, needs testing.

## Alternatives considered

- **Host it on the DGX.** Best engine (vLLM) and prefill, but 16 GB is free in prod mode and the
  GPU modes swap; it would compete with production or vanish. Rejected for the always-on
  assistant; the DGX stays the heavy-batch and production host.
- **Use the production Qwen on the DGX through LiteLLM.** No new memory, but it shares a
  production KV cache that already peaked at 99%. Rejected.
- **Open WebUI instead of LibreChat.** Also has tools and RAG, single container. Rejected in
  D-0007 on the same terms as LibreChat. Worth a second look if LibreChat's three containers
  prove too heavy.
- **Chatbox only (D-0007).** Zero maintenance, but no tools, so use cases 2, 4 and 5 are out.
  Kept as the fallback.
- **vLLM on ROCm on the X3.** Better prefill and batching than Ollama, but the AMD path for this
  APU is less proven than llama.cpp. Revisit at the benchmark stage.

## Discussion

- 2026-11-03 — Written from the session that measured both hosts. The operator asked to treat
  the X3 as a full deployment surface, to start with one model, focus on use cases, then return
  to benchmarks; LibreChat to be considered as the UI, including from the phone.
