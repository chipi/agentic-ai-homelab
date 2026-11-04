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

## Phase 1 — feasibility test on the X3 (about an hour) **(go)** — **done 2026-11-03**

Results and what they decide are in the RFC (section 1, "Feasibility test"): the memory cap does not
see the model (so no cap; one model and a 32k context instead); 2.2 s to the first word at 3.3k
tokens, 15.9 s at 16.4k; the eval harness loading a 65 GB model beside the assistant pushed the
workstation to 121 of 124 GB and into swap, so harness runs of models over ~35 GB stop the
assistant first. The test unit was removed afterwards.

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

## Phase 2 — the hub's status module, and the briefing on the failover model (in parallel with 1) — **live 2026-11-03**

`status.json` every 5 minutes and the 07:00 briefing (page + push to the phone) are live, with their
heartbeat alerts. Open: the week of briefings in the check below.

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

## Phase 3 — chat UI: LibreChat and Open WebUI side by side — **running since 2026-11-03**

On the X3's Docker (option A, the operator's choice: the mini's `tailscale` is a shim without
`serve`), `infra/x3/assistant-ui-eval/`, for a bounded window of about 3 days.

1. ~~Both UIs, pinned images, memory caps, loopback ports 3080/3081, LiteLLM as the only endpoint
   on the failover model through the capped key `assistant-ui-eval`~~ — done. LibreChat reaches the
   gateway by its full tailnet name (its musl resolver ignores the search domain).
2. ~~Phone access: `tailscale serve` on the X3 publishes them over HTTPS on 8443 (LibreChat) and
   8444 (Open WebUI)~~ — done by the operator; the operator's devices reach the X3 already
   (`autogroup:member` → `autogroup:self`), so no ACL change. Accounts on the operator's Gmail,
   sign-ups closed, logins in the hub's credentials table.
3. ~~Grafana's MCP server (viewer token, read-only, 19 tools) wired into both~~ — done. The status
   tool (one GET on `status.json`) is not wired yet. o11y: Langfuse through the gateway, both UIs'
   traces in VictoriaTraces, their logs and metrics through the X3 collector.
4. The same tasks in both, desktop and phone: X1 (a general chat with a pasted document), H4 (is
   prod healthy), H2 (explain a real alert).
5. Judged on: tool calls that work, use on the phone (including the microphone), upkeep (config,
   upgrades, backups).
6. Teardown: `tailscale serve --https=8443 off` and `--https=8444 off` on the X3 (the operator),
   `docker compose down -v` in `infra/x3/assistant-ui-eval/`, the key `assistant-ui-eval` revoked.

**Check:** a recorded decision (a `D-NNNN` entry superseding D-0007, or an ADR) naming the UI; the
teardown done (no serve config on 8443/8444, no eval containers or volumes, the key revoked).

## Phase 4 — the X3 as a deployment surface, and the assistant — **done 2026-11-03**

Results: `ollama-assistant` (user unit, from `~/deploy/agentic-ai-homelab`) holds
`qwen3:30b-a3b-instruct-2507-q4_K_M` loaded, 21.8 GB all on the GPU, 32k context, on
100.92.54.65:11435 only; ufw allows 11435 on `tailscale0` (the operator); chipi/infra f74785f lets
`tag:homelab-host` reach `omarchy:11435`. From the mini: 11435 answers 200; :22, :11434 and :3080
time out. The harness's Ollama kept its PID (1520051). Probe `job="assistant-probe"` reads 1; the
alert `x3-assistant-down` is loaded. The eval harness wrote the stop/start rule into its
`examples/triage-fleet/README.md` (pending the operator's push there). Not done: log rotation for
the assistant's log file.

1. `infra/x3/`: an `AGENTS.md` (the deploy checkout, user units only, the rule for the eval
   harness from phase 1, who upgrades Ollama) and a README; a row in the root `AGENTS.md` table.
2. The deploy checkout on `main`: `~/deploy/agentic-ai-homelab`; re-link `alloy-research` to it
   (it runs from the dev tree today).
3. `infra/x3/ollama-assistant.service` (systemd user unit), with the settings phase 1 measured:
   port 11435 on the tailnet address, ordered after `tailscaled`, the shared model directory, 32k
   context, the one model kept loaded, no memory cap (phase 1: it does not count the model). The
   README states the eval-harness rule (stop the assistant before a harness run of a model over
   ~35 GB, start it after) and the eval harness's runbook gets the same line. **(go)**: a new
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

## Phase 5 — one gateway, with the failover — **done 2026-11-03**

Results (LiteLLM 1.96.2, `assistant` = the X3, 30 s, no retries, fallback `assistant-cloud`; each
call checked by its `x-litellm-model-api-base` / `x-litellm-attempted-fallbacks` headers):

| X3 | Result |
|---|---|
| up | served by the X3 in 0.1–0.2 s |
| stopped | 200 from OpenRouter in 2.7 s, then 0.5 s |
| hung (SIGSTOP) | 200 from OpenRouter in ~31 s, **on every call**: LiteLLM does not cool down a group's only deployment |
| started / resumed | the next call served by the X3 again |

The briefing writes with `assistant` and says which side wrote it ("the X3, local" or
"OpenRouter, failover"). The chat UI key for the evaluation (`assistant-ui-eval`) has `assistant`
too; the UI's own key comes with phase 6. Open: the Spend tab's explicit "N local / $X failover"
line (today the callers card splits each key's tokens into local and OpenRouter).

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

**Progress (2026-11-04):**

- **Phase 8, Grafana — done.** `grafana-llm-app` 1.0.8 (the last version for Grafana < 13), provider
  `custom` → `litellm:4000` (Grafana joins `litellm_default`), base and large → `assistant`, key
  `grafana-llm` ($2). Plugin health OK; a call through it is served by `assistant`. On 11.6 it powers
  generated panel/dashboard titles and descriptions and the change summary on save. Use case shown:
  131 of 316 panels (41%) have no description; the Mac mini dashboard's 13 got one each in ~11 s,
  12 correct, 1 slightly wrong (a ratio called a percentage). Not written back to the dashboards yet
  (a reviewed repo change).
- **Phase 9, Langfuse — done.** LLM connection `homelab-gateway` (model `assistant`, key
  `langfuse-judge`, $2) through `host.docker.internal:4001`, which Langfuse allows only with
  `LANGFUSE_LLM_CONNECTION_WHITELISTED_HOST/_IPS` (compose). Default evaluation model = `assistant`
  (max_tokens 3000: at 800 the judge's answer was cut and the job failed with "No output generated").
  Evaluator `briefing-faithfulness` (built-in Faithfulness v2, context = trace input, answer = trace
  output) on traces tagged `hub-briefing` (the briefing now names its calls). First score: 0.78, with
  the two wrong claims named: "prod origin remains unreachable" (resolved) and "two timeouts" (three).
  The connection, default model and evaluator were set through Langfuse's API and web-app API; they
  are not yet in a repo script.
- **Phase 10, Home Assistant — waiting** for the home-automation session (HA's config is theirs):
  the plan and questions were sent 2026-11-04. HA reaches the X3 model (HTTP 200). The integration
  must pin `qwen3:30b-a3b-instruct-2507-q4_K_M`: the same Ollama lists the eval harness's large models,
  and loading one would evict the assistant.
- **GlitchTip and Umami** have no built-in LLM features; they join as read-only tools in the chat UIs
  (phase 7, wave 2).

**For the evaluation (with the eval harness, at the end):** besides the chat sets (H4/H5 runner in
`infra/x3/assistant-ui-eval/`), evaluate these tool use cases: Grafana panel descriptions (correct
metric, unit and reading, against the panel's query), briefing faithfulness (the Langfuse judge's
scores against a labelled set), and Home Assistant answers (against entity states at the time).

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
