# RFC-0008 — A local assistant on the X3, and the X3 as a deployment surface

**Status:** Proposed (2026-11-03; revised the same day after the operator's decisions and an
independent review)
**Relates to:** D-0005 and D-0007 (LibreChat picked, then removed from scope),
[`infra/observability/hosts/x3/`](https://github.com/chipi/agentic-ai-homelab/tree/main/infra/observability/hosts/x3)
(the X3's collector), the [agent access handbook](../recipes/agent-access.md), ADR-0009 (Docker on
the mini), the eval harness's triage results (`eval-harness/research/internal/TRIAGE_RESULTS_LIVE.md`).
**Plan:** [X3 assistant, version 1](../wip/x3-assistant-v1-plan.md).

## Motivation

The operator wants a smaller LLM running on owned hardware as a day-to-day assistant:

- for the homelab: what happened, what is red, what it costs, what needs them;
- as a personal assistant: a private, general-purpose chat (like ChatGPT, on our own model);
- around the house and the projects;

on their own infrastructure, private by default, reachable from the phone.

Two hosts could run it: the DGX Spark and the X3 (GMKtec EVO-X3). Until now the X3 has been a
workstation with a research collector on it, not a place services are deployed to. Running an
always-on assistant there makes it a third deployment surface next to the Mac mini and the DGX,
and that needs the same treatment the other two have: from the repo, through deploy, to running
and watching it.

## Facts this rests on (measured 2026-11-03)

| | DGX Spark (NVIDIA GB10) | X3 (AMD Ryzen AI Max+ 395, Radeon 8060S) |
|---|---|---|
| Memory | 121 GB unified, **16 GB available** in prod mode (`free -g`) | 124 GB RAM; the GPU can address **62.2 GiB** (`mem_info_gtt_total`; Ollama: `library=ROCm total="62.2 GiB"`). The operator will raise it to the full 128 GB with an X3 restart. 16 GB of swap already in use under dev load |
| In use | prod-vllm 26 GB, translate 30 GB, pyannote 3 GB, moss 2 GB, whisper 1.4 GB (`nvidia-smi`) | the desktop, the operator's dev agents, the eval harness's Ollama |
| Always serving? | No: `gpu-mode-swap` changes what runs (prod / ollama / code / research) | Yes: the operator says it is never off or asleep |
| Engine | vLLM: fast prefill, prefix cache, batching | Ollama 0.40.13 (llama.cpp, ROCm), run by the eval harness as a long-job on `127.0.0.1:11434` |
| Speed | Qwen3-30B-A3B on vLLM, 30 days: first token 230 ms median / 1.8 s p95 on 4.3k-token prompts, 53 tokens/s per stream | Ollama, all models, 30 days: output 47 tokens/s. Prompts in the log are short (none above 3k tokens), so long-prompt speed on the X3 is **not measured**; the review estimates ~18 s to the first word for a 20k-token prompt |
| Tailnet | `dgx-llm-1` | **`omarchy`** (100.92.54.65), an untagged user device; reaching it from the mini's services needs an ACL |
| Docker | yes | yes (`websites-preview` runs); the X3 collector's README says it runs none, which is out of date |

Quality: the eval harness's triage experiment has no assistant-style task. On triage, the same
model served by vLLM on the DGX leads (0.400), but the X3's Ollama 4-bit copy scored 0.723 (rank
29) and the OpenRouter copy 0.708. The harness says the order is not a ranking at 65 decisions.
**The model is not chosen on this eval.** Per the operator, it is evaluated later against the use
cases, once they exist.

## Use cases

### Version 1 (operator, 2026-11-03)

| # | Use case | What it is | Inputs | Done when |
|---|---|---|---|---|
| **H1** | **Morning briefing** (first, the key one) | waiting every morning, without being asked: what happened overnight and what needs the operator today | alerts fired and cleared, deploys, new GlitchTip issues, prod health, fleet queue, spend and credit, capacity | a briefing arrives at the agreed time, every number in it matches the hub, and it says what to look at first |
| **H2** | **Alert explainer** | a Grafana alert fires → "is this real, what do I do?" | the alert rule and its query, recent logs and metrics for the target, the matching runbook | it reads the rule, says whether it looks real with the evidence, and names the next step |
| **H4** | **Is prod healthy** | "anything red on Close Listening / Orrery?", "safe to deploy?" | probes, the Close Listening o11y MCP, GlitchTip, recent deploys | the answer matches the hub's lamps, with the reason for anything not green |
| **H5** | **Spend and capacity** | "what did OpenRouter cost this week, who called it, how much credit is left?", "how much memory is free on the DGX?" | the hub's series (spend, callers, credit, DCGM, node) | the numbers match the hub's Spend and Hosts tabs |
| **H6** | **Fleet queue** | "what does the triage fleet want from me?" | GitHub issues with the fleet's labels | the list matches the hub's "Needs you" count, with one line per item |
| **H7** | **Incident write-up draft** | "draft a timeline of last night's Cloudflare alerts" | alert history, logs, deploys in the window | a timeline the operator can edit, every timestamp traceable to a source |
| **X1** | **Private chat** | general-purpose chat about anything, like ChatGPT, on our own model; drafting, summaries, pasted text and files | the conversation itself | it answers from the X3 model (or says it came from the failover) |
| **X3** | **Translation** | "translate this into Serbian / German" | TranslateGemma on the DGX, through the gateway | a translation comes back; limits stated (below) |
| **X4** | **Home status** | "is anything offline at home?", "is the garage open?" | Home Assistant, UniFi (reads only) | the answer matches Home Assistant |

Dropped from version 1: **runbook lookup** (operator: not a good choice).

Notes:
- **H1 reuses H4, H5 and H6.** The briefing is those reads plus alerts and GlitchTip, run on a
  schedule. Building the tools for H4–H6 builds most of H1.
- **Numbers come from code, not the model.** For H1, H4, H5 and H6, a script gathers the data
  with fixed queries, the same ones the hub uses. The model writes and orders; it does not compute.
  That is how "every number matches the hub" can hold.
- **X3 limits:** TranslateGemma serves only in prod GPU mode (`gpu-mode-swap` stops it otherwise).
  It is a production service for Close Listening. It runs with `--max-model-len=4096`, so texts
  must be short. Assistant use adds load to a production model; acceptable at personal volume,
  measured once used.
- **X4 needs** Home Assistant's address and a read-only token, and the read tools (Home Assistant's
  MCP server integration). Not checked yet.

### The morning briefing, to define with the operator

| Question | Options |
|---|---|
| Goal | what to act on today, first; or everything that happened |
| When | a fixed time (e.g. 07:00) for the window since the evening before (e.g. 18:00) |
| Where it waits | a push notification to the phone with a link; a "Briefing" page on the hub; a conversation in the chat UI; email. The phone push could come through Home Assistant's companion app, ntfy, or Telegram |
| Inputs | alerts, deploys, GlitchTip, prod health, fleet queue, spend and credit, capacity, home (X4) |
| Length and shape | a headline ("2 things need you"), then sections; links to the hub, Grafana and GitHub for each item |

### Later (the catalogue)

| # | Use case | Notes |
|---|---|---|
| H3 | Runbook lookup | dropped from version 1 |
| — | "Why did spend spike?" | over LiteLLM and Langfuse data (from the review) |
| P1 | Ask the podcast corpus | the Close Listening corpus MCP exists |
| P2 | Site and product stats | Umami |
| P3 | Eval results | the harness's results docs |
| P4 | Design and code questions | weak locally; Claude / opencode stay the tools |
| X2 | Voice notes | phone recording → faster-whisper → summary and to-dos |
| X5 | Home actions | needs a confirmation design |

### Inside our tools (the tools call the model)

| # | Use case | How | Notes |
|---|---|---|---|
| I1 | **Grafana LLM plugin** | available for self-hosted Grafana; takes any OpenAI-compatible URL, so the `assistant` alias | "Grafana Assistant" itself is Cloud-only; support for our Grafana 11.6.16 not checked |
| I2 | **Langfuse evaluators** | LLM-as-a-judge is in the free self-hosted Langfuse; an OpenAI-compatible connection to LiteLLM | could score the assistant's answers and the fleet's decisions; needs tool calling through the gateway |
| I3 | **Home Assistant Assist** | HA's official Ollama integration, pointed at the X3's assistant Ollama (Ollama API, not the gateway) | device control is experimental in HA; fewer than 25 exposed entities suggested |

Umami and GlitchTip have no LLM features of their own; the assistant reads them instead.

## Proposal

### 1. The X3 becomes a deployment surface

| Concern | Mini | DGX | X3 (proposed) |
|---|---|---|---|
| Where it lives in the repo | `infra/mini-*`, `infra/observability/backend/` | `infra/dgx/`, `infra/vllm/` | **`infra/x3/`** with its own `AGENTS.md` and README |
| Deploy checkout | `~/agentic-ai-homelab` | `/home/ops/agentic-ai-homelab` (user `ops`) | **a separate checkout on `main`** (e.g. `~/deploy/agentic-ai-homelab`), never the dev tree at `/work/agentic-ai-homelab` |
| How services run | launchd + Docker (prod engine) | Docker compose in place | **systemd user units** linked from the deploy checkout, as `alloy-research` already does |
| Deploy | `git pull` + kickstart / compose | `git pull` + compose | `git pull` + `systemctl --user restart <unit>` |
| Observability | Alloy, VictoriaMetrics | Alloy, DCGM, cAdvisor | Alloy already runs (`alloy-research`): add the assistant's Ollama log (to a file the existing `*ollama*.log` source reads, with its own `service` label) and a probe |
| Health | probes, alerts | probes, alerts, `gpu-mode` | a probe on the assistant endpoint, an alert, a lamp on the hub (Hosts → X3) |
| Network | tailnet, tagged | tailnet, tagged | tailnet name `omarchy`; **Tailscale ACLs** let the mini's services reach the assistant port, nothing else |
| Upgrades | per stack | per stack | Ollama is a hand-installed binary; Omarchy's rolling updates (kernel, Mesa, ROCm) can break it, so the README names who upgrades it and how to roll back |
| Undo | per stack | per stack | `systemctl --user disable --now <unit>`, remove the link |

Rules that come with it:
- **One model in version 1** (operator): Qwen3-30B only; no heavy or small second model.
- **Separate from the eval harness, with a rule, not just a port.** Both Ollama instances share one
  GPU: when the harness loads a large model, the assistant's model can be evicted, and the
  assistant's resident model changes the harness's timings. The feasibility test (plan, phase 1)
  measures this; the outcome is a written rule, e.g. the assistant pauses while a harness run is
  on, or memory is split.
- **The workstation comes first.** Whether a systemd memory cap even counts GPU-mapped model
  memory on this kernel is unverified; the feasibility test checks it before a cap is relied on.

### 2. The model

`qwen3:30b-a3b-instruct-2507-q4_K_M` (18 GB, already on disk): 3B active parameters, tool calling,
262k native context (run at 32k). Chosen as a start, not on an eval; the use cases are evaluated
later with a labelled set per use case, and the model with them.

### 3. One gateway, with a failover

The mini's LiteLLM gets an alias, `assistant`, routed to the X3 over the tailnet (by IP: the
mini's LiteLLM container cannot resolve MagicDNS names), each client with its own capped virtual
key. Every client uses the same endpoint; Langfuse traces it; the hub's Spend tab shows it.

**Failover (operator):** to `qwen/qwen3-30b-a3b-instruct-2507` on OpenRouter, the same model, so
prompts and tool calls behave the same:
- a fallback on the `assistant` alias only (not router-wide), with its own capped key and budget;
- a per-alias timeout (~30 s) and few retries; with the gateway's global settings (120 s, 6
  retries) a hung X3 would take minutes to fail over;
- a cold model load (15–22 s in the logs) is latency, not failure;
- **provenance:** LiteLLM reports the model that answered; the chat UI has to show it, so "local
  and private" is never silently untrue. How each UI shows it is part of the UI evaluation;
- tested for a stopped, a slow and a hung X3.

### 4. Chat UI: LibreChat and Open WebUI, side by side

Both are self-hosted chat harnesses: no model of their own. They hold conversations, route to
models, call tools and run agents.

- **LibreChat** (three containers: API, MongoDB, Meilisearch). Per its documentation:
  - OpenAI-compatible endpoints, so LiteLLM and everything behind it;
  - MCP servers, configured in `librechat.yaml` or at runtime, used in chat or by agents (a saved
    prompt, model and toolset);
  - chat with files (a RAG API and a vector database, extra services);
  - email, LDAP, SAML or OIDC sign-in, with registration closable.
- **Open WebUI** (one container): chat, files and RAG built in; MCP support in recent versions,
  not verified yet.

**Why D-0007 dropped LibreChat, and what changed.** In June it fronted one coder model, and
Chatbox (a phone app, no server) did the same with nothing to maintain. Now there is a gateway
with every model behind it, tools worth calling, and the use cases above. The cost that matters
is wiring the tools, which both UIs need, more than the number of containers.

**The evaluation:** both on the mini's dev Docker engine (ADR-0009: on demand, 6 GiB, memory cap
per container), against LiteLLM with the OpenRouter Qwen and Grafana's MCP server. The same tasks
in both: H2, H4 and X1, from the desktop and the phone. Judged on tool use, showing which model
answered, phone use, and upkeep (config, upgrades, backups). The winner moves to the mini's
production engine; the decision is recorded and supersedes D-0007.

**Placement (operator):** the chosen UI on the mini (always-on service host); the model on the X3.

**The LibreChat running on the DGX today** is a leftover from June, never really used (operator).
Its files are untracked, the image is a floating `librechat-dev-api:latest` (v0.8.6), it points
only at coder-next (down in prod mode), and its `.env` names OpenAI, Anthropic and Google API keys
(names checked, values not read). It is retired first, and the keys checked and rotated if live.

### 5. Mobile

The phone is on the tailnet (Tailscale app). The UI gets a tailnet HTTPS name and is installed as a
home-screen web app. The hub uses Caddy and a tailnet node of its own (`infra/reverse-proxy`), not
`tailscale serve`; the UI follows one of the two, decided when it is deployed. Nothing is exposed
to the internet. Chatbox on the `assistant` alias stays the zero-maintenance fallback (no tools).

### 6. Tools, read-only in version 1

| Tool | Serves | How |
|---|---|---|
| Grafana MCP server (viewer token) | H2, H4, H5, H7, H1 | alerts, rules, Prometheus-style queries on VictoriaMetrics |
| GlitchTip (read-only token) | H1, H4, H7 | its Sentry-compatible API |
| GitHub (read-only token) | H6, H1 | issues with the fleet's labels |
| Close Listening o11y MCP | H4, H1 | exists; how the UI authenticates to it is open |
| Home Assistant (read-only token) | X4 | Home Assistant's MCP server integration |
| `translate` alias in LiteLLM | X3 | TranslateGemma on the DGX |
| The briefing script | H1 | fixed queries, then the model writes; runs on a schedule on the mini |

**Where MCP servers run:** LibreChat runs stdio servers inside its own container; Grafana's MCP
server is a separate binary, so its own container with its own token. Tokens live in mode-600
files on the mini and get rows in the handbook's credentials table.

**Security:** read-only tools bound writes, not exfiltration: a tool result (a log line, an issue)
can carry instructions that make the model repeat other tool results into the chat. For a single
operator on a private tailnet that is acceptable, and stated. Write tools (Home Assistant
actions, GitHub writes) wait for a confirm-each-action design.

**Privacy:** Langfuse would store private chats (X1). Decided before X1 goes live: a separate
Langfuse project, or no tracing for X1.

## Non-goals

- Replacing Claude Code / opencode for project work.
- Changing what the DGX serves, or using its production chat model for the assistant.
- Fine-tuning, or training anything.
- Exposing anything outside the tailnet.
- Benchmarks and model comparison before the use cases run (operator).

## Open questions

1. **LibreChat or Open WebUI:** the side-by-side evaluation decides. Fallback: Chatbox and the
   gateway, no tools.
2. **The briefing's goal, time, delivery and shape** (table above).
3. **Separation from the eval harness:** the rule, after the feasibility test.
4. **Memory caps** on the X3: whether they count model memory, and what to set.
5. **Tracing private chats** (X1): separate Langfuse project or none.
6. **Home Assistant access** for X4: address, token, MCP integration.
7. **Voice:** speech to text through our faster-whisper, not tested.

Settled: the UI on the mini and the model on the X3; the X3 always on; failover to OpenRouter
Qwen3-30B; one model; the version 1 use cases; the X3's GPU memory raised to 128 GB by the
operator; Tailscale ACLs added for access.

## Alternatives considered

- **Host it on the DGX.** Best engine and prefill, but 16 GB free in prod mode and swapping GPU
  modes. Rejected for the always-on assistant; the DGX stays the heavy-batch and production host.
- **Use the production Qwen on the DGX through LiteLLM.** No new memory, but it shares a
  production KV cache that already peaked at 99%. Rejected.
- **Chatbox only (D-0007).** Zero maintenance, no tools, so most version 1 use cases are out.
  Kept as the fallback.
- **vLLM on ROCm on the X3.** Better prefill and batching than Ollama, but less proven on this
  APU. Revisit at the benchmark stage.

## Review (2026-11-03, independent advisor, Fable 5.1)

Verdict: proceed with changes. What it found, and what was done:

| Finding | Status |
|---|---|
| The RFC said the local model "leads the triage eval"; the leader is the vLLM copy on the DGX, the X3's Ollama copy is rank 29 | corrected; the operator chooses the model by use-case evaluation later |
| The X3's GPU can address 62.2 GiB, not 128 GB; a 65 GB model evicted the loaded one on 10-31 | corrected; one model only; the operator raises the limit to 128 GB with a restart |
| Long-prompt speed on the X3 is not measured | the feasibility test measures 4k and 20k |
| The tailnet name is `omarchy`, untagged; the mini's LiteLLM needs the IP and an ACL | corrected; ACLs in the plan |
| Memory caps may not count GPU-mapped memory | the feasibility test checks |
| Two Ollama instances on one GPU evict each other | the feasibility test measures; a rule follows |
| Failover timing (120 s, 6 retries) and provenance | per-alias timeout, provenance shown, slow and hung tests |
| Gaps: UI backups and versions, secrets, MCP hosting and auth, tracing of private chats, agent design, a labelled test set | in the plan |
| Order: test feasibility first; retire the DGX LibreChat first; decide the UI independently of the X3 | the plan's phases follow this |
| Use cases: the briefing as a scheduled push; "why did spend spike" | adopted |

## Discussion

- 2026-11-03 — Written from the session that measured both hosts. The operator asked to treat
  the X3 as a full deployment surface, to start with one model, focus on use cases, then return
  to benchmarks; LibreChat to be considered as the UI, including from the phone.
- 2026-11-03 — Operator: the UI on the mini, the model on the X3; the X3 is never off, but plan a
  failover to OpenRouter (`qwen/qwen3-30b-a3b-instruct-2507`). Use cases replaced with a
  catalogue; tools with their own LLM features added (I1–I3).
- 2026-11-03 — Review (above). Operator: evaluate the model later against the use cases; raise the
  X3's GPU memory to 128 GB; add Tailscale ACLs; a feasibility test as the MVP start; one model;
  retire the DGX LibreChat; compare LibreChat and Open WebUI side by side; the briefing waits
  every morning. Version 1 use cases: H1, H2, H4, H5, H6, H7, X1, X3, X4; runbook lookup dropped.
