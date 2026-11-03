# X3 assistant, version 1: implementation plan

**For:** [RFC-0008](../rfc/RFC-0008-x3-local-assistant.md). **Written:** 2026-11-03.
**Order agreed with the operator:** one model first, then the use cases, then benchmarks.

Each phase ends with a check that proves it, and nothing moves to the next phase until that check
passes. Steps marked **(go)** change shared state or install something, so each needs the
operator's go when it comes up. A go for one step does not cover the next.

## Phase 0 — decisions and checks before building

| # | Item | How it is settled |
|---|---|---|
| 0.1 | Where LibreChat runs: mini (always-on service host) or X3 | operator decides; this plan assumes **the mini** |
| 0.2 | Is the X3 on and reachable 24/7? | read-only: `systemctl status sleep.target suspend.target`, logind `IdleAction`, `HandleLidSwitch`, uptime history; reach `x3` from the mini over the tailnet |
| 0.3 | Fallback if the X3 is down | operator decides: none (the assistant is just down) or an OpenRouter model, marked as not local in the UI |
| 0.4 | Memory cap for the assistant unit | start at `MemoryHigh=28G` / `MemoryMax=32G` (one 18 GB model, 32k context); revisit with the measured peak of dev work |

## Phase 1 — the X3 as a deployment surface

1. `infra/x3/`: an `AGENTS.md` (scoped rules: the deploy checkout, user units only, the eval
   harness's Ollama left alone) and a README; a row in the root `AGENTS.md` table.
2. A deploy checkout on `main`, separate from the dev tree: `git clone` to
   `~/deploy/agentic-ai-homelab`. Units link from there, never from `/work/agentic-ai-homelab`.
3. Recipe `docs/recipes/x3-deploy.md`: deploy (`git pull --ff-only` + `systemctl --user restart`),
   status, logs (`journalctl --user -u …`), undo.
4. The handbook gets an X3 section (how to reach it, what runs there). `host-run` learns an `x3`
   target if the mini's agents need to run things there.
5. Fix the X3 collector README: it says the X3 runs no Docker, and it does.

**Check:** the recipe works on a no-op unit: a deploy is a pull plus a restart, and undoing it
leaves nothing behind.

## Phase 2 — the assistant model on the X3

1. `infra/x3/ollama-assistant.service` (systemd user unit), running the Ollama binary already
   installed at `~/.local/opt/ollama-0.40.13`. Its settings:
   - listens on the X3's tailnet address only, port `11435` (the eval harness keeps
     `127.0.0.1:11434`);
   - `OLLAMA_MODELS=~/.ollama/models`, the same directory, so nothing is downloaded;
   - `OLLAMA_CONTEXT_LENGTH=32768`, `OLLAMA_KEEP_ALIVE=-1` for the main model,
     `OLLAMA_MAX_LOADED_MODELS=2`;
   - the memory caps from 0.4.
   **(go)**: a new always-on service on the workstation.
2. Load `qwen3:30b-a3b-instruct-2507-q4_K_M`. It is already on disk, so nothing is pulled.
3. Observability:
   - the X3 Alloy collector reads the unit's journal as `job="ollama"`, `instance="x3"`,
     `service="assistant"`, so the hub's Ollama pages pick it up;
   - a probe on the endpoint from the mini, plus an alert;
   - an X3 lamp and sub-tab under Hosts on the hub.

**Check:**
- from the mini: `curl http://x3:11435/api/chat` answers, and `ollama ps` shows the model on the
  GPU;
- the probe is green on the hub, and the Ollama page shows `x3` requests;
- the eval harness's instance is untouched (same PID, same port).

## Phase 3 — one gateway

1. LiteLLM (mini): aliases `assistant` → the X3's Qwen3-30B, and `assistant-heavy` →
   `gpt-oss:120b` (loads on demand). **(go)**: a config change and restart on the mini's LiteLLM.
2. Mint a capped virtual key for the chat UI (`mint-credential`). **(go)**
3. Langfuse traces arrive; the hub's Spend shows the caller.

**Check:**
- a call through the gateway with the new key returns 200; a model outside the key's list returns
  403;
- the trace shows in Langfuse, and the caller card on the hub.

## Phase 4 — chat UI, from the phone too

1. `infra/librechat/` back in the repo, written fresh: a compose file with a **pinned** image
   version, `librechat.yaml` with LiteLLM as the only endpoint (no provider keys), registration
   closed after the operator's account, data volumes on the mini.
   **(go)**: pull images and start the stack on the mini's production engine.
2. Tailscale Serve under a tailnet HTTPS name (e.g. `chat.tail6d0ed4.ts.net`), like the hub.
   **(go)**
3. On the phone, done by the operator: open the name, install it as a home-screen app, sign in,
   chat.

**Check:** a chat from the phone gets an answer from the X3 model, and its trace appears in
Langfuse.

## Phase 5 — first tools (read-only)

1. **Grafana's MCP server** with a viewer token: alerts, dashboards, and Prometheus-style queries
   against VictoriaMetrics, in one server. **(go)**: an install.
2. **The Close Listening MCP servers** that already exist: corpus search and production health.
3. **The handbook and runbooks**, as files the agent can read.
4. A LibreChat agent, "homelab", with those tools and a prompt that says it is read-only.

**Check:** the questions from the RFC's use cases, asked from the phone, give answers that match
the hub:
- "is anything red right now";
- "what happened overnight";
- "how do I restart the OpenRouter collector".

## Phase 6 — clean-up

- Retire the leftover LibreChat on the DGX (untracked, floating image, provider keys in its
  `.env`). **(go)**: a DGX change.
- Check whether those provider keys are still live; rotate them if they are. **(go)**

## After version 1

1. **Use cases:** GlitchTip, Umami and Home Assistant tools (reads first; Home Assistant actions
   only with a confirmation design); retrieval over the docs (needs an embedding model, so a
   **(go)**); voice through our faster-whisper.
2. **Benchmarks:** Qwen3-30B against Qwen3.6-35B and gpt-oss-120b on the X3: first token at 4k
   and 20k context, output speed, and assistant-style quality from a small labelled set in the
   eval harness.
