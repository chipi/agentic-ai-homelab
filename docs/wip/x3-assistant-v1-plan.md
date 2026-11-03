# X3 assistant: implementation plan

**For:** [RFC-0008](../rfc/RFC-0008-x3-local-assistant.md). **Written:** 2026-11-03, revised twice
the same day after the operator's decisions and two reviews.
**Order agreed with the operator:** step 1, the assistant (one model, the version 1 use cases in
three waves); step 2, the same model inside Grafana, Langfuse and Home Assistant; step 3, the use
cases rebuilt around those tools; then evaluation and benchmarks against the use cases.

Each phase ends with a check that proves it, and nothing moves on until that check passes. Steps
marked **(go)** change shared state or install something, so each needs the operator's go when it
comes up. A go for one step does not cover the next.

# Step 1 — the assistant

## Phase 0 — clean-up and decisions

| # | Step | Check |
|---|---|---|
| 0.1 | ~~Retire the leftover LibreChat on the DGX~~ — **done 2026-11-03**: no API requests in 7 days, no connections; its database held 0 users, 0 keys, 0 conversations; `compose down` removed the containers and network; the folder `/home/ops/agentic-ai-homelab/infra/librechat` deleted (operator: "like it was never there"); its hub row, `.gitignore` block and `infra-drift` allowance removed. Left: its anonymous MongoDB volume and three images (~2.7 GB), unused, pending the operator's go | `docker ps -a` on the DGX shows no `librechat-*`; the folder is gone; the ops checkout is clean |
| 0.2 | ~~Check its provider keys~~ — **done 2026-11-03**: none stored. `OPENAI_API_KEY`, `ANTHROPIC_API_KEY` and `GOOGLE_KEY` were unset or `user_provided`, and the database's `keys` collection was empty, so nothing to rotate | — |
| 0.3 | ~~The briefing's push channel~~: Home Assistant's companion app, on the operator's phone (confirmed 2026-11-03). The briefing job calls HA's notify service for that device with a token kept on the mini | — |
| 0.4 | Off the critical path: the X3's GPU memory to 128 GB (the operator, with a restart): both the GTT size and `ttm.pages_limit` | `mem_info_gtt_total`, `/sys/module/ttm/parameters/pages_limit` and Ollama's `library=ROCm total=` all show the new size |

## Phase 1 — feasibility test on the X3 (about an hour) **(go)**

A throwaway second Ollama on `127.0.0.1:11435` (same binary, same model directory), with
`qwen3:30b-a3b-instruct-2507-q4_K_M` loaded, in a transient systemd user scope with a memory cap.
It measures:

1. whether the scope's `memory.current` counts the model (about 18 GB), i.e. whether a cap works;
2. time to the first word and output speed at 4k and 20k-token prompts, with a 32k context;
3. what happens to each instance when the eval harness's Ollama loads a large model, and the other
   way round;
4. swap and free memory throughout.

Stopped and removed afterwards. The numbers decide the unit's settings and the rule for sharing the
GPU with the harness, and go into the RFC.

## Phase 2 — the hub's status module, and the briefing on the failover model (in parallel with 1)

No dependency on the X3, the UI or MCP, so the briefing works in week 1.

1. `hub-status.js` (plain JS, returns data): first the areas version 1 needs, moved out of `gen.sh`
   one at a time, each with a test on its data:
   - prod health (site and podcast lamps);
   - "Needs you";
   - spend and credit;
   - host capacity.
   The page draws from the module and looks the same as before.
2. A Node job on the mini (launchd, every 5 minutes) runs the module against localhost, writes
   `status.json` (served by the hub at `/status.json`) and logs each snapshot with its timestamp to
   VictoriaLogs. **(go)**: a new launchd job.
3. The briefing job (launchd, 07:00 local, the window since 19:00, Mondays since Friday 19:00):
   the status history for the window, plus alerts, deploys and GlitchTip, in the order and shape of
   the RFC's briefing table; the model writes it, through LiteLLM on the failover model
   (`qwen/qwen3-30b-a3b-instruct-2507` on OpenRouter) with its own capped key; if the model call
   fails, a plain template version from the same data. Delivered to a "Briefing" page on the hub
   (the last 30 kept), and as a push with the headline and a link once the channel is settled.
   **(go)**: a launchd job and a key.
4. A heartbeat: no briefing by 07:15 raises an alert.

**Check:**
- the hub looks and behaves as before, and its tests pass;
- `status.json` matches the page at the same minute;
- a week of briefings: each on time, every number matching the logged status snapshot for that hour
  (checked with VictoriaMetrics' `time=`), and the operator says what to change.

## Phase 3 — chat UI: LibreChat and Open WebUI side by side

On the mini's dev engine (operator; RFC section 4), for a bounded window of about 3 days.

1. `devengine start` (it refuses if the mini is short of memory). Both UIs in the `dev` context,
   pinned image versions, memory caps per container (LibreChat's three containers and Open WebUI
   within the engine's 6 GiB), published on two fixed loopback ports on the mini (a recorded
   exception to the random-port rule), LiteLLM as the only endpoint, on the failover model through
   a capped dev key. **(go)**: the engine, image pulls and a key.
2. Phone access: `tailscale serve` on the mini publishes the two ports over HTTPS on 8443
   (LibreChat) and 8444 (Open WebUI) **(go)**, and a temporary ACL rule in chipi/infra,
   `autogroup:admin` → `tag:homelab-host:8443,8444` **(go: the PR's merge)**. Check first where the
   mini's `tailscale` command lives and what it already serves (not found at the usual paths).
3. The status tool (one GET on `status.json`) and Grafana's MCP server (viewer token) wired into
   both. **(go)**: an install and a token.
4. The same tasks in both, desktop and phone: X1 (a general chat with a pasted document), H4 (is
   prod healthy), H2 (explain a real alert).
5. Judged on: tool calls that work, use on the phone (including the microphone), upkeep (config,
   upgrades, backups).
6. Teardown: serve off, the ACL rule reverted, containers removed, `devengine stop`.

**Check:** a recorded decision (a `D-NNNN` entry superseding D-0007, or an ADR) naming the UI; the
teardown done (no serve config, no ACL rule, the dev engine stopped).

## Phase 4 — the X3 as a deployment surface, and the assistant

1. `infra/x3/`: an `AGENTS.md` (the deploy checkout, user units only, the rule for the eval
   harness from phase 1, who upgrades Ollama) and a README; a row in the root `AGENTS.md` table.
2. The deploy checkout on `main`: `~/deploy/agentic-ai-homelab`; re-link `alloy-research` to it
   (it runs from the dev tree today).
3. `infra/x3/ollama-assistant.service` (systemd user unit), with the settings phase 1 measured:
   port 11435 on the tailnet address, ordered after `tailscaled`, the shared model directory, 32k
   context, the one model kept loaded, the cap if phase 1 showed it works. **(go)**: a new
   always-on service on the workstation.
4. Network: a ufw rule for 11435 on `tailscale0` **(go)**, and a Tailscale ACL PR in chipi/infra:
   source `tag:homelab-host`, destination a `hosts` entry for `omarchy` (100.92.54.65), port 11435
   only **(go: the PR's merge)**. The handbook's pointer to the policy file is corrected (it names
   podcast_scraper).
5. Recipe `docs/recipes/x3-deploy.md` (deploy, status, logs, undo), an X3 section in the handbook,
   and the X3 collector README fixed (it says the X3 runs no Docker).
6. Observability: the unit logs to its own file; a second block in the X3 collector reads it with
   `service="assistant"`; a probe from the mini, an alert, an X3 lamp under Hosts on the hub.

**Check:**
- from the mini, the assistant answers on 100.92.54.65:11435, and another X3 port does not;
- `ollama ps` shows the model on the GPU; the probe is green on the hub; the Ollama pages show the
  assistant's requests;
- the eval harness's instance is untouched (same PID, same port).

## Phase 5 — one gateway, with the failover

1. LiteLLM (mini): the alias `assistant` → the X3 by IP, a ~30 s timeout and no retries on the
   local deployment, a fallback to `qwen/qwen3-30b-a3b-instruct-2507` on OpenRouter (the key from
   phase 2), on this alias only. **(go)**: a config change and restart of the gateway the fleets
   and podcast also use, at a quiet time, with the previous config kept for undo.
2. A capped virtual key for the chat UI (`mint-credential`). **(go)**
3. The briefing switches from the failover model to `assistant`.
4. The hub's Spend tab gets "assistant: N local / $X failover".

**Check:**
- with the new key, `assistant` returns 200 and a model outside the key's list returns 403;
- stopped, slow and hung X3: each still returns 200 from the failover within ~35 s, and Langfuse and
  the hub show the failover; after LiteLLM's cooldown the next call is local again.

## Phase 6 — the chosen UI in place, from the phone

1. The UI on the mini's production engine: pinned versions, memory caps, data volumes in
   `infra/backup`, its secrets in mode-600 files with handbook rows. **(go)**
2. A tailnet HTTPS name following the hub's pattern (`infra/reverse-proxy`: a new
   `bind tailscale/<name>` and a network join, so a restart of the production Caddy). **(go)**
3. Tracing for private chat (X1): a separate Langfuse project, or none, as decided. **(go)**
4. The operator installs it on the phone.

**Check:** a chat from the phone answers from the X3 model; the hub and Langfuse show it as local.

## Phase 7 — the use cases, in waves (read-only tools)

| Wave | Use cases | Tools | (go) |
|---|---|---|---|
| 1 | H1 (done in phase 2), X1, H4, H5, H6 | the status tool; GitHub read-only for H6's items | a GitHub token |
| 2 | H2, H7 | Grafana MCP server (viewer token); GlitchTip read-only | tokens, an install |
| 3 | X3, X4 | the `translate` alias (verify chat completions and its prompt format first); Home Assistant's states through Grafana MCP | a gateway alias |

Agents in the UI, each with a short prompt and only its tools: "homelab" (H2, H4–H7), plain chat
(X1), "translate" (X3), "home" (X4).

**Check, per wave:** a small labelled set per use case (wave 1 first, 5–10 questions each, answers
taken from the hub and the source systems), asked from the phone, answers matching. These sets are
the start of the later evaluation.

# Step 2 — the same model inside our tools

| Phase | Tool | Steps | Check |
|---|---|---|---|
| 8 | **Grafana** | check the Grafana LLM plugin's support for Grafana 11.6.16; install it through provisioning **(go)**; point it at LiteLLM's `assistant` alias with its own capped key **(go)** | Grafana's AI features answer from the X3 model; the calls show in Langfuse under that key |
| 9 | **Langfuse** | an LLM connection to LiteLLM (base URL, its own capped key) **(go)**; one LLM-as-a-judge evaluator on the assistant's traces (e.g. "answer grounded in its tool results"), the judge's key kept out of the scores | scores appear on new traces; the judge's own traces are tagged |
| 10 | **Home Assistant** (on the mini) | HA's Ollama integration pointed at the X3's assistant (100.92.54.65:11435; the phase 4 ACL already covers the mini) **(go)**; device control off first; then a short list of exposed entities | Assist in HA's companion app answers from the X3 model; with control on, only the exposed entities respond |

Note for phase 10: Home Assistant speaks the Ollama API, so its calls bypass LiteLLM (no failover,
no Langfuse trace). Accepted for home use, or revisited in step 3.

# Step 3 — use cases rebuilt around the tools

With step 2 running, go through the use cases and move each to where it works best, for example:
- H2 (alert explainer) inside Grafana, next to the alert;
- X4 / X5 (home status and actions) through Home Assistant's own agent and voice app, with HA's
  exposed-entity list as the control boundary;
- evaluation through Langfuse's evaluators on real traces, feeding the labelled sets.

**Check:** a revised use-case table in the RFC (where each one lives, and why), agreed with the
operator.

# After

1. The later use cases from the RFC, one at a time ("why did spend spike", the podcast corpus,
   voice notes, home actions with confirmation).
2. Evaluation and benchmarks against the use cases: Qwen3-30B against Qwen3.6-35B and gpt-oss-120b,
   quality on the labelled sets, first token and speed on the X3.
