# X3 assistant, version 1: implementation plan

**For:** [RFC-0008](../rfc/RFC-0008-x3-local-assistant.md). **Written:** 2026-11-03, revised the
same day after the operator's decisions and the review.
**Order agreed with the operator:** one model first, then the use cases, then evaluation and
benchmarks against them.

Each phase ends with a check that proves it, and nothing moves to the next phase until that check
passes. Steps marked **(go)** change shared state or install something, so each needs the
operator's go when it comes up. A go for one step does not cover the next.

## Phase 0 — clean-up and access

| # | Step | Check |
|---|---|---|
| 0.1 | Retire the leftover LibreChat on the DGX: stop its containers, keep its data dir until confirmed unneeded. **(go)**: a DGX change | `docker ps` on the DGX shows no `librechat-*` |
| 0.2 | Check whether the OpenAI / Anthropic / Google keys named in its `.env` are live; rotate the live ones. **(go)** | each key tested once and listed as live or dead; live ones rotated |
| 0.3 | The X3's GPU memory to the full 128 GB, with a restart (the operator) | `mem_info_gtt_total` and Ollama's `library=ROCm total=` show the new size |
| 0.4 | Tailscale ACLs: the mini's services (`tag:homelab-svc`) may reach `omarchy` (100.92.54.65) on the assistant port, nothing else. **(go)**: an ACL change | from the mini, the port answers; another X3 port does not |
| 0.5 | The briefing's goal, time, delivery and shape (RFC table), with the operator | written into the RFC |

## Phase 1 — feasibility test on the X3 (about an hour) **(go)**

A throwaway second Ollama on port 11435 (same binary, same model directory), with
`qwen3:30b-a3b-instruct-2507-q4_K_M` loaded, run in a transient systemd user scope with a memory cap.
It measures:

1. whether the scope's `memory.current` counts the model (about 18 GB), i.e. whether a cap works;
2. time to the first word and output speed at 4k and 20k-token prompts, and with a 32k context;
3. what happens to each instance when the eval harness's Ollama loads a large model, and the other
   way round;
4. the X3's swap and free memory during all of it.

The test is stopped and removed afterwards. Its numbers decide the unit's settings and the rule for
sharing the GPU with the eval harness, and they are written into the RFC.

## Phase 2 — chat UI: LibreChat and Open WebUI side by side

On the mini's dev Docker engine (ADR-0009: `devengine start`, the `dev` context, a memory cap per
container, torn down after).

1. Both UIs, pinned image versions, LiteLLM as the only endpoint, using the failover model
   (`qwen/qwen3-30b-a3b-instruct-2507` on OpenRouter) through a capped dev key. **(go)**: image
   pulls, and a key.
2. Grafana's MCP server with a viewer token, wired into both. **(go)**: an install and a token.
3. The same tasks in both, from the desktop and the phone: H2 (explain a real alert), H4 (is prod
   healthy), X1 (a general chat with a pasted document).
4. Judged on: tool calls that work, showing which model answered, use on the phone, upkeep
   (config, upgrades, backups).

**Check:** a recorded decision (a `D-NNNN` entry superseding D-0007, or an ADR) naming the UI.

## Phase 3 — the X3 as a deployment surface, and the assistant

1. `infra/x3/`: an `AGENTS.md` (the deploy checkout, user units only, the rule for the eval
   harness, who upgrades Ollama) and a README; a row in the root `AGENTS.md` table.
2. A deploy checkout on `main`, separate from the dev tree: `~/deploy/agentic-ai-homelab`.
3. `infra/x3/ollama-assistant.service` (systemd user unit), with the settings Phase 1 measured:
   port 11435 on the tailnet address, the shared model directory, 32k context, one model kept
   loaded, the cap if Phase 1 showed it works. **(go)**: a new always-on service on the workstation.
4. Recipe `docs/recipes/x3-deploy.md` (deploy, status, logs, undo) and an X3 section in the handbook.
5. Observability: the unit logs to a file the X3 collector already reads (`*ollama*.log`), with
   `service="assistant"`; a probe from the mini and an alert; an X3 lamp under Hosts on the hub.
6. Fix the X3 collector README (it says the X3 runs no Docker).

**Check:**
- from the mini, the assistant answers on 100.92.54.65:11435 and `ollama ps` shows the model on the
  GPU;
- the probe is green on the hub, and the Ollama pages show the assistant's requests;
- the eval harness's instance is untouched (same PID, same port).

## Phase 4 — one gateway, with the failover

1. LiteLLM (mini): the alias `assistant` → the X3 (by IP), with a fallback to
   `qwen/qwen3-30b-a3b-instruct-2507` on OpenRouter on its own capped key, a ~30 s timeout and
   few retries on this alias only. A `translate` alias for TranslateGemma (X3 use case). **(go)**:
   a config change and restart of a gateway the fleets and podcast also use, so at a quiet time,
   with the previous config kept for undo.
2. A capped virtual key for the chat UI (`mint-credential`). **(go)**

**Check:**
- with the new key, `assistant` returns 200 and a model outside the key's list returns 403;
- stopped, slow and hung X3: each still returns 200 from the failover within ~35 s, and the trace
  and spend show the failover; restarted, the next call is local;
- `translate` returns a translation while the DGX is in prod mode.

## Phase 5 — the chosen UI in place, from the phone

1. The UI from Phase 2 on the mini's production engine: pinned versions, memory caps, data
   volumes in `infra/backup`, its own secrets in mode-600 files with handbook rows. **(go)**
2. A tailnet HTTPS name, following the hub's pattern or `tailscale serve`. **(go)**: a new tailnet
   node or serve config.
3. Tracing for private chat (X1): a separate Langfuse project, or none, as decided. **(go)**
4. The operator installs it on the phone.

**Check:** a chat from the phone answers from the X3 model, and the UI shows which model answered.

## Phase 6 — the tools for the version 1 use cases (read-only)

| Tool | Use cases | (go) |
|---|---|---|
| Grafana MCP server (viewer token) | H2, H4, H5, H7 | install, token |
| GlitchTip (read-only token) | H4, H7, H1 | token |
| GitHub (read-only token, the fleet's labels) | H6, H1 | token |
| Close Listening o11y MCP | H4, H1 | auth from the UI |
| Home Assistant (read-only token, MCP integration) | X4 | token, HA config |
| `translate` alias | X3 | done in phase 4 |

Agents in the UI, each with a short prompt and only the tools it needs: "homelab" (H2, H4, H5, H6,
H7), "home" (X4), plain chat (X1), "translate" (X3).

**Check:** a small labelled set per use case (5–10 questions each, the answers taken from the hub
and the source systems), asked from the phone, answers matching. The same set is the start of the
later evaluation.

## Phase 7 — the morning briefing (H1)

1. A briefing script on the mini, on a schedule (launchd): fixed queries, the same ones the hub
   uses (alerts, deploys, GlitchTip, prod health, fleet queue, spend and credit, capacity, home),
   into a structured summary; the model then writes and orders it. Numbers come from the script.
2. Delivery as decided in 0.5 (phone push with a link; a hub page; a conversation in the UI).
3. Its own log and a heartbeat: a missing briefing raises an alert.

**Check:** a week of briefings, each on time, every number matching the hub at that hour, and the
operator says what to change.

## After version 1

1. The later use cases from the RFC, one at a time (e.g. "why did spend spike", the podcast
   corpus, voice notes, home actions with confirmation).
2. Use cases inside our tools: Grafana's LLM plugin, Langfuse evaluators, Home Assistant Assist
   (RFC I1–I3).
3. Evaluation and benchmarks against the version 1 use cases: Qwen3-30B against Qwen3.6-35B and
   gpt-oss-120b, quality on the labelled sets, first token and speed on the X3.
