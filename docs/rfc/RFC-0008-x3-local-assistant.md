# RFC-0008 — A local assistant on the X3, and the X3 as a deployment surface

**Status:** Proposed (2026-11-03; revised twice the same day after the operator's decisions and
two independent reviews)
**Relates to:** D-0005 and D-0007 (LibreChat picked, then removed from scope),
[`infra/observability/hosts/x3/`](https://github.com/chipi/agentic-ai-homelab/tree/main/infra/observability/hosts/x3)
(the X3's collector), the [agent access handbook](../recipes/agent-access.md), ADR-0009 (Docker on
the mini), the eval harness's triage results (`eval-harness/research/internal/TRIAGE_RESULTS_LIVE.md`).
**Plan:** [X3 assistant: implementation plan](../wip/x3-assistant-v1-plan.md).

## Motivation

The operator wants a smaller LLM running on owned hardware as a day-to-day assistant:

- for the homelab: what happened, what is red, what it costs, what needs them;
- as a personal assistant: a private, general-purpose chat (like ChatGPT, on our own model);
- around the house and the projects;
- and the same model inside the tools that can use one (Grafana, Langfuse, Home Assistant);

on their own infrastructure, private by default, reachable from the phone.

Two hosts could run it: the DGX Spark and the X3 (GMKtec EVO-X3). Until now the X3 has been a
workstation with a research collector on it, not a place services are deployed to. Running an
always-on assistant there makes it a third deployment surface next to the Mac mini and the DGX,
and that needs the same treatment the other two have: from the repo, through deploy, to running
and watching it.

## The three steps

1. **The assistant (version 1):** the model on the X3, one gateway with a failover, a chat UI on
   the mini, the phone, and the version 1 use cases led by the morning briefing.
2. **The same model inside our tools:** Grafana's LLM plugin, Langfuse's LLM connection and
   evaluators, Home Assistant's conversation agent.
3. **Use cases rebuilt around the tools:** with step 2 in place, move each use case to where it
   works best: inside the tool, in the chat, or in the briefing.

Then: evaluate the model against the use cases (labelled sets), and benchmarks.

## Facts this rests on (measured 2026-11-03)

| | DGX Spark (NVIDIA GB10) | X3 (AMD Ryzen AI Max+ 395, Radeon 8060S) |
|---|---|---|
| Memory | 121 GB unified, **16 GB available** in prod mode (`free -g`) | 124 GB RAM; the GPU can address **62.2 GiB** (`mem_info_gtt_total`, and `ttm.pages_limit` = 16,310,633 pages). Raising it takes both the GTT size and `ttm.pages_limit`; the operator plans it with a restart. The 18 GB assistant does not need it. 16 GB of swap already in use under dev load |
| In use | prod-vllm 26 GB, translate 30 GB, pyannote 3 GB, moss 2 GB, whisper 1.4 GB (`nvidia-smi`) | the desktop, the operator's dev agents, the eval harness's Ollama |
| Always serving? | No: `gpu-mode-swap` changes what runs (prod / ollama / code / research) | Yes: the operator says it is never off or asleep |
| Engine | vLLM: fast prefill, prefix cache, batching | Ollama 0.40.13 (llama.cpp, ROCm), run by the eval harness as a long-job on `127.0.0.1:11434` |
| Speed | Qwen3-30B-A3B on vLLM, 30 days: first token 230 ms median / 1.8 s p95 on 4.3k-token prompts, 53 tokens/s per stream | Ollama, all models, 30 days: output 47 tokens/s. No prompt above 3k tokens in the log, so long-prompt speed is **not measured** (a review estimates ~18 s to the first word at 20k) |
| Network | tailnet `dgx-llm-1`, tagged | tailnet **`omarchy`** (100.92.54.65), untagged; **ufw drops inbound** by default (only 22/tcp on `tailscale0` and one app port open) |
| Docker | yes | yes (`websites-preview` runs); the X3 collector's README says none, which is out of date |

Where things already run on the mini: LiteLLM, Grafana, Langfuse, GlitchTip, Umami, the hub, and
**Home Assistant** (the home-automation repo's `deploy/homelab`, port 8123). The mini's services
reach the tailnet as the host node, **`tag:homelab-host`** (the rule that lets LiteLLM reach the
DGX today has that source). The tailnet policy lives in git (chipi/infra `tailscale/policy.hujson`,
applied by its `tailscale-acl.yml` workflow), so an ACL change is a PR.

Quality: the eval harness's triage experiment has no assistant-style task. On triage, the same
model served by vLLM on the DGX leads (0.400); the X3's Ollama 4-bit copy scored 0.723 (rank 29)
and the OpenRouter copy 0.708. **The model is not chosen on this eval**; it is evaluated later
against the use cases (operator).

## Use cases

### Version 1 (operator, 2026-11-03), delivered in three waves

| Wave | # | Use case | What it is | Inputs | Done when |
|---|---|---|---|---|---|
| 1 | **H1** | **Morning briefing** (the key one) | waiting every morning: what happened overnight and what needs the operator today | the hub's status (below), alerts, deploys, GlitchTip | it arrives on time, every number matches the hub's status snapshot for that hour, and it says what to look at first |
| 1 | **X1** | **Private chat** | general-purpose chat about anything, like ChatGPT, on our own model; drafting, summaries, pasted text and files | the conversation | it answers from the X3 model; failover use is visible on the hub |
| 1 | **H4** | **Is prod healthy** | "anything red on Close Listening / Orrery?", "safe to deploy?" | the hub's status | the answer matches the hub's lamps, with the reason for anything not green |
| 1 | **H5** | **Spend and capacity** | "what did OpenRouter cost this week, who called it, credit left?", "memory free on the DGX?" | the hub's status | the numbers match the hub's Spend and Hosts tabs |
| 1 | **H6** | **Fleet queue** | "what does the triage fleet want from me?" | the hub's status for the count; GitHub for the items | the count matches the hub's "Needs you"; each item links to its issue (the list can differ from the count by design: the count is the fleet's metric) |
| 2 | **H2** | **Alert explainer** | a Grafana alert fires → "is this real, what do I do?" | the alert rule and query, recent logs and metrics, the alert's runbook link if it has one | it says whether it looks real, with the evidence, and the next step |
| 2 | **H7** | **Incident write-up draft** | "draft a timeline of last night's Cloudflare alerts" | alert history, logs, deploys in the window | an editable timeline, every timestamp traceable to a source |
| 3 | **X3** | **Translation** | "translate this into Serbian / German" | TranslateGemma on the DGX | a translation comes back; limits below |
| 3 | **X4** | **Home status** | "is anything offline at home?", "is the garage open?" | Home Assistant's states, already in VictoriaMetrics | the answer matches Home Assistant |

Wave 1 proves every layer (phone, UI, gateway, X3 model, the status module, the briefing), and H4,
H5 and H6 come almost free from the same status data. Dropped from version 1: **runbook lookup**
(operator).

Notes:
- **X3 limits:** TranslateGemma serves only in prod GPU mode, is a production service for Close
  Listening, runs with `--max-model-len=4096` (short texts only), and expects its own prompt format;
  chat completions through a gateway alias are unverified.
- **X4 without an admin token:** every Home Assistant long-lived token is full admin, but its
  states already flow into VictoriaMetrics (the mini's Alloy, job `home-assistant`), so X4 reads
  them there, read-only by construction.

### The morning briefing (first version; the operator accepted it as a start, easy to change)

| | Decided |
|---|---|
| Goal | what needs the operator today, first; then a short account of the night |
| When | 07:00 local time, for the 12 hours since 19:00; on Mondays since Friday 19:00 |
| Where it waits | a "Briefing" page on the hub (the last 30 kept), and a push to the phone with the headline and a link, through Home Assistant's companion app (on the operator's phone, confirmed 2026-11-03; HA runs on the mini) |
| Content, in order | **headline** "N things need you"; **needs you** (at most 5, each linked): lamps not green and since when, new GlitchTip issues, the fleet's "Needs you" and new escalations, OpenRouter credit below $10; **overnight**: alerts fired and resolved with times, deploys; **numbers**: OpenRouter spend yesterday against the 7-day average, local tokens, credit left, the busiest caller; **capacity**: warnings only (disk, memory, swap); **all green**: one line |
| Home | joins with wave 3 (X4), exceptions only (devices offline) |
| Robustness | every number from the status snapshot; the model only writes; if the model call fails, a plain template version is delivered, so no morning is skipped silently |

### Later (the catalogue)

| # | Use case | Notes |
|---|---|---|
| H3 | Runbook lookup | dropped from version 1 |
| — | "Why did spend spike?" | over LiteLLM and Langfuse data |
| P1 | Ask the podcast corpus | the Close Listening corpus MCP exists |
| P2 | Site and product stats | Umami |
| P3 | Eval results | the harness's results docs |
| P4 | Design and code questions | weak locally; Claude / opencode stay the tools |
| X2 | Voice notes | phone recording → faster-whisper → summary and to-dos |
| X5 | Home actions | needs a confirmation design; Home Assistant's own agent (step 2) may be the place |

## Proposal

### 0. One source of truth for the hub's semantics

The hub decides what is green, amber or red, what "Needs you" counts, what spend means, in its
browser JavaScript (`infra/homelab-home/gen.sh`): each function runs the queries, applies the rules
and draws HTML in one go. A briefing script with its own copies of those queries would drift.

Split deciding from drawing:
- **`hub-status.js`**, plain JavaScript with no page code: one function per area returns data
  (`{ id, label, state, value, reason, since, link }`). The queries, thresholds and rules live
  only here.
- **The page** imports it and only draws.
- **A Node job on the mini** (launchd, every 5 minutes; Node is installed there) runs the same file
  against localhost and writes `status.json`, served by the hub at `/status.json`. Each run's
  snapshot goes to VictoriaLogs with its timestamp, so any hour can be checked afterwards.
- **Everything else reads `status.json`:** the briefing, the assistant's H4 / H5 / H6 (one tool,
  one HTTP GET), later alerts.

Moved area by area: version 1 needs prod health, "Needs you", spend and credit, and capacity. The
rest of the hub stays as it is until there is a reason to move it. Tests get simpler: the module
returns data, not HTML.

### 1. The X3 becomes a deployment surface

| Concern | Mini | DGX | X3 (proposed) |
|---|---|---|---|
| Where it lives in the repo | `infra/mini-*`, `infra/observability/backend/` | `infra/dgx/`, `infra/vllm/` | **`infra/x3/`** with its own `AGENTS.md` and README |
| Deploy checkout | `~/agentic-ai-homelab` | `/home/ops/agentic-ai-homelab` (user `ops`) | **a separate checkout on `main`** (`~/deploy/agentic-ai-homelab`), never the dev tree. The X3's Alloy (`alloy-research`) runs from the dev tree today and is re-linked |
| How services run | launchd + Docker (prod engine) | Docker compose in place | **systemd user units** linked from the deploy checkout; ordered after `tailscaled` when they bind the tailnet address |
| Deploy | `git pull` + kickstart / compose | `git pull` + compose | `git pull` + `systemctl --user restart <unit>` |
| Observability | Alloy, VictoriaMetrics | Alloy, DCGM, cAdvisor | the assistant logs to its own file, read by a second block in the X3 collector with `service="assistant"` (the existing block's label is fixed); a probe from the mini, an alert, a lamp under Hosts on the hub |
| Network | tailnet, tagged | tailnet, tagged | an ACL rule (PR in chipi/infra): source `tag:homelab-host`, destination a `hosts` entry for `omarchy` (100.92.54.65), port 11435 only; and a ufw rule for that port on `tailscale0` |
| Upgrades | per stack | per stack | Ollama is a hand-installed binary; Omarchy's rolling updates (kernel, Mesa, ROCm) can break it; the README names who upgrades it and how to roll back |
| Undo | per stack | per stack | `systemctl --user disable --now <unit>`, remove the link, revert the ufw and ACL rules |

**Feasibility test (plan phase 1, 2026-11-03, on the X3).** A throwaway second Ollama on
`127.0.0.1:11435`, `qwen3:30b-a3b-instruct-2507-q4_K_M` at a 32k context, in a transient systemd
unit with `MemoryHigh=28G` / `MemoryMax=32G`:

| Measured | Result |
|---|---|
| Load | 5.8 s from a warm page cache; 21 GB, 100% on the GPU |
| Memory cap | **does not see the model**: the unit's `memory.current` stayed under 1 GB while GPU-mapped memory (`mem_info_gtt_used`) rose by 22 GB and system RAM in use from 50 to 70 GB. A systemd cap cannot protect the workstation from the model |
| 3.3k-token prompt | 1,532 tokens/s prompt processing, **2.2 s to the first word**, 61 tokens/s out |
| 16.4k-token prompt | 1,032 tokens/s, **15.9 s to the first word**, 47 tokens/s out |
| With the eval harness loading gpt-oss:120b (65 GB) beside it | the harness's model got the remaining GPU memory only: **37% on the CPU**, 78 s to load; system RAM in use 121 of 124 GB and swap from 16 to 41 GB, so the workstation itself was under pressure. Unloaded at once; RAM recovered (58 GB used) |
| After that | the assistant answered as before (2.3 s, 61 tokens/s) |

What it decides:
- **No memory cap on the unit** (it would only cap the small CPU side); the protection is one
  resident model, a fixed 32k context and the GPU memory limit.
- **The eval harness and the assistant share one memory pool.** Raising the GPU limit to 128 GB
  does not add RAM: the assistant's 21 GB plus a 65 GB model plus the desktop and the dev agents
  already filled 124 GB. **Rule:** before a harness run of a model that does not fit beside the
  assistant (over ~35 GB), the assistant unit is stopped (the gateway fails over to OpenRouter),
  and started again after the run.
- **Prompts stay compact.** At 20k tokens the first word takes ~16 s, so the briefing and the tools
  send structured summaries (the status file), not raw logs.

Rules that come with it:
- **One model in version 1** (operator).
- **Separate from the eval harness, with a rule, not just a port:** the rule above (stop the
  assistant for harness runs of models over ~35 GB). Harness runs of small models can share.
- **The workstation comes first:** one resident model, 32k context; no systemd memory cap, since
  the test showed it does not count the model.

### 2. The model

`qwen3:30b-a3b-instruct-2507-q4_K_M` (18 GB, already on disk): 3B active parameters, tool calling,
262k native context (run at 32k). A start, not an eval result.

### 3. One gateway, with a failover

The mini's LiteLLM gets an alias, `assistant`, routed to the X3 by IP (its container cannot resolve
MagicDNS), each client with its own capped virtual key; Langfuse traces it.

**Failover (operator):** to `qwen/qwen3-30b-a3b-instruct-2507` on OpenRouter, the same model:
- a fallback on the `assistant` alias only, its own capped key and budget;
- the local deployment with a ~30 s timeout and **no retries**, so a stopped or hung X3 fails over
  within about 35 s (the gateway's global 120 s and 6 retries would take minutes);
- a cold model load (15–22 s in the logs) is latency, not failure; after a failure, LiteLLM's
  cooldown keeps traffic on the failover for a while, so "the next call is local again" holds only
  after the cooldown;
- **provenance on the hub, not in the UI:** neither UI shows LiteLLM's fallback (they display the
  alias). The hub's Spend tab already splits OpenRouter from local per key; it gets a line
  "assistant: N local / $X failover", and Langfuse shows each call's model.

### 4. Chat UI: LibreChat and Open WebUI, side by side

Both are self-hosted chat harnesses with no model of their own: they hold conversations, route to
models, call tools and run agents.

- **LibreChat** (three containers: API, MongoDB, Meilisearch). Per its documentation:
  - OpenAI-compatible endpoints (LiteLLM and everything behind it);
  - MCP servers in `librechat.yaml` or at runtime, in chat or in agents (a saved prompt, model and
    toolset);
  - chat with files (an extra RAG API and vector database);
  - email, LDAP, SAML or OIDC sign-in, registration closable.
- **Open WebUI** (one container): chat, files and RAG built in; MCP support in recent versions,
  not verified.

**Why D-0007 dropped LibreChat, and what changed.** In June it fronted one coder model and Chatbox
did the same with nothing to maintain. Now there is a gateway with every model behind it, tools
worth calling and the use cases above. The cost that matters is wiring the tools, which both need.

**The evaluation:** the same tasks in both (X1, H4 through the status tool, H2 with Grafana's MCP
server), from the desktop and the phone, against the OpenRouter Qwen through a capped key; judged on
tool use, phone use and upkeep.

**Where (operator): the mini's dev engine** (ADR-0009), the final host's platform. The phone is on
the tailnet, but the dev engine is a VM whose container ports are forwarded only to the mini's
`127.0.0.1`, which nothing on the tailnet reaches, and the tailnet policy lets the operator's
devices reach the mini only on listed ports. The bridge, for the evaluation only:
- both UIs on two fixed loopback ports on the mini (a recorded exception to the dev engine's
  random-port rule), with memory caps;
- `tailscale serve` on the mini publishes them over HTTPS on ports 8443 and 8444 (real HTTPS, so
  the phone allows the microphone and the home-screen install);
- a temporary ACL rule (PR in chipi/infra): `autogroup:admin` → `tag:homelab-host:8443,8444`;
- a bounded window (about 3 days; while up, the dev engine holds 26 of the mini's 32 GiB in VMs);
  afterwards serve off, the ACL reverted, `devengine stop`.

The winner moves to the mini's production engine; the decision is recorded and supersedes D-0007.

**Placement (operator):** the chosen UI on the mini; the model on the X3.

**The LibreChat on the DGX today** is a leftover from June, never really used (operator): untracked
files, a floating `librechat-dev-api:latest` (v0.8.6), pointed only at coder-next, an `.env` naming
OpenAI, Anthropic and Google API keys (names checked, values not read). It is retired first, its
keys checked and rotated if live, and its row removed from the hub (`gen.sh` watches its three
containers, so the lamp would turn red).

### 5. Mobile

The phone is on the tailnet. The chosen UI gets a tailnet HTTPS name following the hub's pattern
(Caddy with a tailnet node of its own, `infra/reverse-proxy`: a new `bind tailscale/<name>` and a
network join, so a restart of the production Caddy) and is installed as a home-screen web app.
Nothing is exposed to the internet. Chatbox on the `assistant` alias stays the zero-maintenance
fallback (no tools).

### 6. Tools, read-only

| Tool | Serves | How |
|---|---|---|
| The hub's `status.json` | H1, H4, H5, H6 | one HTTP GET on the hub |
| GitHub (read-only token) | H6 items, H1 | issues with the fleet's labels |
| Grafana MCP server (viewer token) | H2, H7, X4 | alerts, rules, Prometheus-style queries on VictoriaMetrics (Home Assistant's states included) |
| GlitchTip (read-only token) | H1, H2, H7 | its Sentry-compatible API |
| `translate` alias in LiteLLM | X3 | TranslateGemma on the DGX; format and chat completions to verify |
| The briefing job | H1 | reads `status.json` history and the sources above; the model writes; runs on a schedule on the mini |

MCP servers: LibreChat runs stdio servers in its own container; Grafana's MCP server is a separate
binary, so a container with its own token. Tokens live in mode-600 files on the mini, with rows in
the handbook's credentials table.

**Security:** read-only tools bound writes, not exfiltration: a tool result can carry instructions
that make the model repeat other tool results into the chat. Acceptable for a single operator on a
private tailnet, and stated. Write tools wait for a confirm-each-action design.

**Privacy:** Langfuse would store private chats (X1); decided before X1 goes live: a separate
Langfuse project, or no tracing for X1.

### 7. Step 2 — the same model inside our tools

| Tool | What it gives | How | Notes |
|---|---|---|---|
| **Grafana** | Grafana's AI features (writing and explaining panels, queries, dashboards) on our model | the Grafana LLM plugin (available for self-hosted Grafana), pointed at LiteLLM's `assistant` alias with its own capped key | "Grafana Assistant" itself is Cloud-only; plugin support for our Grafana 11.6.16 is checked first |
| **Langfuse** | the model scores traces automatically: the assistant's answers, the briefing, the triage fleet's decisions | an LLM connection (OpenAI-compatible base URL = LiteLLM) and LLM-as-a-judge evaluators, free in self-hosted Langfuse | the gateway must pass tool calls; the judge's own calls are traced too, so its key is tagged and kept out of the scores |
| **Home Assistant** | chat and voice at home (Assist) on our model, through HA's companion app | HA's official Ollama integration, pointed at the X3's assistant Ollama; HA runs on the mini, so it reaches the X3 through the same ACL rule | HA speaks the Ollama API, so it bypasses LiteLLM: no failover and no Langfuse trace for these calls; start with device control off, then fewer than 25 exposed entities |

### 8. Step 3 — use cases rebuilt around the tools

With step 2 in place, each use case moves to where it works best, for example:
- **H2 alert explainer** inside Grafana, next to the alert, instead of only in the chat;
- **home status and actions (X4, X5)** through Home Assistant's own agent and its voice app, with
  HA's exposed-entity list as the control boundary;
- **evaluation** through Langfuse's evaluators on real traces, feeding the labelled sets;
- **the briefing** keeps its own job, and links into each tool.

Which use cases move, and how, is decided once step 2 runs.

## Non-goals

- Replacing Claude Code / opencode for project work.
- Changing what the DGX serves, or using its production chat model for the assistant.
- Fine-tuning, or training anything.
- Exposing anything outside the tailnet.
- Benchmarks and model comparison before the use cases run (operator).

## Open questions

1. **LibreChat or Open WebUI** (the comparison runs on the mini's dev engine).
2. ~~The briefing's push channel~~: Home Assistant's companion app (on the phone).
3. **Separation from the eval harness:** the rule, after the feasibility test.
4. **Memory caps** on the X3: whether they count model memory, and what to set.
5. **Tracing private chats** (X1): separate Langfuse project or none.
6. **Grafana LLM plugin** support for Grafana 11.6.16.
7. **Voice:** speech to text through our faster-whisper, not tested.

Settled: the UI on the mini and the model on the X3; the X3 always on; failover to OpenRouter
Qwen3-30B; one model; the version 1 use cases and their waves; the hub's status module as the one
source of the briefing's numbers; Tailscale ACLs for access; step 2 (Grafana, Langfuse, Home
Assistant) and step 3 (use cases around them).

## Alternatives considered

- **Host it on the DGX.** Best engine and prefill, but 16 GB free in prod mode and swapping GPU
  modes. Rejected for the always-on assistant.
- **Use the production Qwen on the DGX through LiteLLM.** Shares a production KV cache that already
  peaked at 99%. Rejected.
- **The briefing with its own copies of the hub's queries.** Drifts from the hub. Rejected for the
  status module.
- **Run the hub's functions in Node against a fake page (as `test_page.js` does), or scrape the
  rendered hub with a headless browser.** Brittle: the output is HTML, or depends on the layout.
- **VictoriaMetrics recording rules for the hub's semantics.** Fits the metric-only rules, not the
  parts on logs, Umami's SQL or Grafana. Possible later for a few headline signals.
- **Chatbox only (D-0007).** No tools. Kept as the fallback.
- **vLLM on ROCm on the X3.** Less proven on this APU. Revisit at the benchmark stage.

## Reviews

**First review** (2026-11-03, independent advisor, Fable 5.1): proceed with changes.

| Finding | Status |
|---|---|
| The RFC said the local model "leads the triage eval" | corrected |
| The X3's GPU addresses 62.2 GiB; a 65 GB model evicted the loaded one | corrected; one model |
| Long-prompt speed on the X3 unmeasured | the feasibility test |
| Tailnet name `omarchy`, untagged | corrected |
| Memory caps may not count GPU-mapped memory | the feasibility test |
| Two Ollama instances evict each other | the feasibility test, then a rule |
| Failover timing and provenance | redesigned (section 3) |
| Gaps: UI backups, secrets, MCP hosting, tracing of private chats, agent design, a labelled set | in the plan |

**Second review** (2026-11-03, independent advisor, Fable 5.1): proceed with changes. Each item
below was checked against the system.

| Finding | Status |
|---|---|
| The ACL source is `tag:homelab-host`, not `tag:homelab-svc`; the policy is a PR in chipi/infra; `omarchy` needs a `hosts` entry | corrected (section 1) |
| ufw drops inbound on the X3; no step opened the port | added |
| The GPU raise needs `ttm.pages_limit` too; the assistant does not need it | corrected; off the critical path |
| "Every number matches the hub" cannot hold with copied queries | the status module (section 0) |
| H6's list and count come from different sources | done-criterion restated |
| Neither UI shows LiteLLM's fallback | provenance on the hub and in Langfuse |
| Phone access to the dev engine is unsolved | the comparison's location is open, with the X3 as the alternative |
| No read-only Home Assistant token exists | X4 reads HA's states in VictoriaMetrics |
| TranslateGemma through a chat alias unverified | wave 3, verify first |
| Retiring the DGX LibreChat turns a hub lamp red | its row removed with it |
| Failover check needs no retries; cooldown; unit after tailscaled; a second collector block; the X3's Alloy runs from the dev tree | added |
| Nine use cases is too many at once | delivered in three waves; wave 1 proves every layer |

## Discussion

- 2026-11-03 — Written from the session that measured both hosts.
- 2026-11-03 — Operator: the UI on the mini, the model on the X3; failover to OpenRouter
  (`qwen/qwen3-30b-a3b-instruct-2507`). Use-case catalogue; tools with their own LLM features.
- 2026-11-03 — First review. Operator: evaluate the model later; raise the X3's GPU memory; add
  ACLs; a feasibility test as the MVP start; one model; retire the DGX LibreChat; compare the two
  UIs; the briefing waits every morning. Version 1: H1, H2, H4, H5, H6, H7, X1, X3, X4.
- 2026-11-03 — Second review. Operator: the hub's semantics must not be duplicated (the status
  module); add step 2 (the same model in Grafana, Langfuse and Home Assistant) and step 3 (use cases
  rebuilt around them). The nine use cases are delivered in three waves.
- 2026-11-03 — Operator: the UI comparison runs on the mini's dev engine, reached from the phone
  over the tailnet (bridge: `tailscale serve` + a temporary ACL). The briefing's first version as
  proposed (07:00, needs-you first, hub page + phone push), easy to change later.
