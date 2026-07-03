# Multi-Agent Fleets in Pi and OpenCode

A practical guide to building the same thing twice: a team of specialized agents, each
with its own default model, fronted by an **orchestrator you talk to** that dispatches
work to the rest. Build it once in Pi and once in OpenCode so you can compare the
harnesses on real projects.

Stack assumption: TypeScript/Node greenfield project. Both tools are BYOK and speak
OpenAI-compatible endpoints, so every model below runs either self-hosted (Ollama /
vLLM / SGLang / LM Studio) or cloud (direct provider API, OpenRouter, or each tool's own
gateway).

> Model IDs drift fast. Treat every `provider/model` string here as a placeholder and
> confirm the exact slug against your provider, `models.dev`, or the tool's model list
> before relying on it.

---

## 0. Read this first — your Anthropic subscription

As of early 2026, Anthropic **only permits Claude Free/Pro/Max subscription tokens in its
own clients** (Claude Code and Claude.ai). Using those subscription credentials inside a
third-party harness — Pi or OpenCode included — violates the Consumer Terms and risks an
account ban. OpenCode removed its built-in subscription login in v1.3.0 for exactly this
reason. Community OAuth plugins that "restore" it exist; don't use them.

**The compliant pattern (what this guide uses):**

**Chosen architecture: zero Anthropic spend in the fleet, Claude as an out-of-loop reviewer.**

- The autonomous fleet is **fully open and self-hostable** — open models for every role,
  including the in-loop reviewer. No Anthropic credentials live in Pi or OpenCode at all,
  so there's nothing to violate.
- Your **Max subscription stays on Claude Code**, where it's licensed. Claude reviews the
  fleet's output **at the diff/PR level**, on your initiative, in Claude Code — outside the
  harness entirely. See the two-gate review in §1.

This is the single architecture mapped below.

---

## 1. The fleet design (tool-agnostic)

Eight roles. The principle: **cheap models for bounded/mechanical work, strong models for
ambiguous/coordination work.** You only pay top dollar where reasoning actually moves the
needle (planning, review, debugging, coordination).

| Agent | Role | Tier | Model (all-open) |
|---|---|---|---|
| **orchestrator** | You talk to it; plans & dispatches | strong | Qwen 3.6 Plus / DeepSeek V4 Pro |
| **planner** | Breaks features into tasks | strong | GLM 5.2 / DeepSeek V4 Pro |
| **backend** | Implements API/server in TS/Node | coder | DeepSeek V4 / Qwen3-Coder |
| **ui** | Implements frontend | coder | Qwen3-Coder / DeepSeek V4 |
| **tester** | Writes/runs tests | cheap | DeepSeek V4 Flash |
| **reviewer** | In-loop code review / red-team | strong | GLM 5.2 / DeepSeek V4 Pro |
| **docs** | Docs & comments | cheap | small Qwen / DeepSeek Flash |
| **debugger** | Troubleshoots failures | strong | DeepSeek V4 Pro / Qwen 3.6 Plus |

Rule of thumb that matches both tools' defaults: the orchestrator is your strongest model;
workers inherit a cheaper default unless a role specifically benefits from more horsepower
(reviewer, debugger). Start cheaper than you think and promote roles that visibly struggle.
For concrete current models and OpenRouter slugs per role, see §2.4.

### Two review gates

With Claude out of the harness, the fleet needs its own automatic quality gate — so there
are **two** reviews, at different altitudes:

1. **In-loop reviewer (open model, automatic).** Fires on *every* change before work is
   reported back to you. It's the fleet's only self-check, so keep it on a strong model
   (GLM 5.1 / DeepSeek V4 Pro) — do **not** let it drift to a cheap tier just because
   Claude backstops it later. Nothing reaches you un-reviewed.
2. **Out-of-loop reviewer (Claude, on your call).** The fleet produces a **branch or PR**;
   you open that diff in **Claude Code** and have Claude review it at the artifact level.
   Claude never touches the harness — the review target is a concrete git diff, which fits
   the worktree + verification-in-the-environment approach.

The seam between them is **git**: the fleet's deliverable is a reviewable diff, not a live
agent transcript. Gate 1 keeps the loop honest cheaply; gate 2 is your high-signal human
+ Claude pass before anything merges.

### Roles & built-ins per tool

You don't author every role from scratch — each tool ships some OOB. The roles cluster into
four families, and which model tier they want follows **cost of being wrong**, not prestige:

| Family | What it does | Tier | Why |
|---|---|---|---|
| **Recon** (scout / explore / explorer) | Finds relevant code, returns a brief | cheap | bounded, verifiable, high-volume |
| **Plan** (planner / Plan mode) | Decomposes work, freezes contracts | strong | sets what everyone downstream inherits |
| **Build** (worker / backend / ui / build) | Implements against a spec | mid | real judgment, but tests catch errors |
| **Verify** (reviewer) | Audits before merge — your Gate 1 | strong | the only automatic gate; hard to re-check |
| **Advise** (oracle / advisor) | Diagnoses hard calls, *doesn't edit* | strong | ambiguous, high blast radius |
| **Research** (researcher / OpenCode's scout) | External docs/deps with sources | cheap | bounded lookup, isolatable |
| **Support** (tester / docs) | Tests, docs — bounded mechanical work | cheap | self-checking, high-volume |

What actually ships OOB, and the gaps:

- **Pi** — richest set: `scout, researcher, planner, worker, reviewer, context-builder,
  oracle, delegate`. You get reviewer **and** oracle for free. Rule of thumb (Pi's own):
  scout before you understand the code, researcher before you trust external facts, planner
  before a bigger change, worker to implement, reviewer to check, oracle when the decision
  is hard.
- **OpenCode** — leaner: primaries `Build` + `Plan`; subagents `General`, `Explore`,
  `Scout`. **Gap: no built-in reviewer or oracle** — author them as `review.md` /
  `advisor.md` subagents. Note `Plan` is a first-class read-only planning primary.
- **Codex** — built-in `explorer`, `worker`, `default`, plus a built-in **review** agent
  (separate agent reviews before commit). Custom agents are TOML in `~/.codex/agents/`.
- **Cursor** — subagents since 2.4 (`.cursor/agents/*.md`); ships examples like
  `code-reviewer` / `search-agent`, plus **Bugbot/fixer** (reviews PRs, spins a cloud agent,
  tests a fix). Plan Mode built in.
- **Claude Code** — author subagents in `.claude/agents/*.md`; Plan mode + an Explore
  subagent. This is your Gate-2 surface, not a fleet host.

**Two naming traps.** (1) "Scout" means *codebase recon* in Pi but *dependency/upstream
research* in OpenCode — in OpenCode the codebase-recon seat is **`explore`**. (2) Four of the
five (all but Codex) use the same markdown + YAML frontmatter with `name`/`description`/
`model`, so a scout/reviewer/oracle agent file ports across Claude Code, OpenCode, and Cursor
with just a directory change; Codex needs a TOML rewrite.

The two families you're most likely to under-use relative to their payoff are **Verify** and
**Advise** — they're exactly what protect an autonomous fleet, and OpenCode makes you build
them yourself.

---

## 2. Providers (set up once)

Your design is per-role model selection, so the thing that must stay cheap is *swapping a
role's model*. Route the cloud models through **one gateway — OpenRouter** — and keep
self-hosted models on a **separate local provider**. Assigning a model to a role then
becomes a one-line string edit, not a new key + base URL + SDK quirk each time.

**Why OpenRouter over per-vendor keys:** one key and one OpenAI-compatible endpoint for
DeepSeek, Qwen, GLM, Kimi, MiniMax *and* US models; one bill with unified token/cost
attribution (folds into your observability); automatic failover when a provider
rate-limits or 500s (direct keys just die mid-run); zero-onboarding experimentation when
you want a different model on a role.

**Trade-offs:** a small inference markup vs. going direct (at volume, pin one heavy-hitter
role straight to its vendor and leave the rest on OpenRouter); your prompts transit
OpenRouter — a privacy hop, the opposite of the air-gapped local path, so keep
proprietary-only work local; slightly less control over per-provider params.

**Local never routes through OpenRouter.** Ollama / llama.cpp / FastContext are a
*separate* local provider pointing at `localhost`. Both tools support multiple providers at
once, so the topology is: OpenRouter for cloud/strong roles, local provider for self-hosted
+ FastContext. Register both, assign per role.

### 2.1 Pi

`~/.pi/agent/auth.json`:

```json
{ "openrouter": { "type": "api_key", "key": "sk-or-..." } }
```

`~/.pi/agent/models.json` — OpenRouter + local side by side:

```json
{
  "providers": {
    "openrouter": {
      "baseUrl": "https://openrouter.ai/api/v1",
      "api": "openai-completions",
      "models": [
        { "id": "deepseek/deepseek-chat" },
        { "id": "qwen/qwen3-coder" },
        { "id": "z-ai/glm-4.6" },
        { "id": "moonshotai/kimi-k2" },
        { "id": "anthropic/claude-sonnet-4.5" }
      ]
    },
    "local": {
      "baseUrl": "http://localhost:11434/v1",
      "api": "openai-completions",
      "apiKey": "ollama",
      "models": [{ "id": "fastcontext-4b" }, { "id": "qwen3-coder" }]
    }
  }
}
```

Assign per role in `settings.json`. Note the **nested slug**: `openrouter/` prefix plus the
model's own `vendor/model`, so it's three segments.

```json
{
  "subagents": { "agentOverrides": {
    "reviewer": { "model": "openrouter/z-ai/glm-4.6", "thinking": "high" },
    "worker":   { "model": "openrouter/deepseek/deepseek-chat" },
    "scout":    { "model": "local/fastcontext-4b" }
  }}}
```

### 2.2 OpenCode

```bash
opencode auth login        # pick OpenRouter, paste key
opencode auth login        # again → Ollama, for the local / FastContext side
```

Then reference `openrouter/<vendor>/<model>` for cloud and `ollama/<model>` for local:

```json
{
  "$schema": "https://opencode.ai/config.json",
  "agent": {
    "build":   { "model": "openrouter/deepseek/deepseek-chat" },
    "plan":    { "model": "openrouter/z-ai/glm-4.6" },
    "explore": { "model": "ollama/fastcontext-4b" }
  }
}
```

In OpenCode the codebase-recon seat is **explore**, not scout — FastContext goes there.
(OpenCode's `scout` is dependency/upstream research, ≈ Pi's `researcher`.)

### 2.3 Set these on day one

- **Spend limit / per-key budget** on the OpenRouter dashboard — a runaway parallel fleet
  burns credits fast.
- **Data-policy toggle** — exclude any upstream provider that trains on inputs, since your
  code transits them.
- **Verify every slug** at `openrouter.ai/models` and via `opencode models` / Pi's model
  list; they drift (GLM is often `z-ai/glm-…`, Kimi `moonshotai/kimi-…`).

### 2.4 Per-role model map (OpenRouter, mid-2026)

Concrete picks by role, following the cost-of-failure tiering. **Slugs drift fast — confirm
each at `openrouter.ai/models` before pasting; treat these as the model *names* to look up,
not guaranteed strings.**

| Role | Model | OpenRouter slug (verify) | Why |
|---|---|---|---|
| orchestrator | GLM 5.2 | `z-ai/glm-5.2` | highest open-weight intelligence; best on ambiguous coordination |
| planner | Qwen 3.6 Plus | `qwen/qwen3.6-plus` | strongest on long-horizon planning; 1M ctx to hold the plan |
| backend / ui | DeepSeek V4 Pro | `deepseek/deepseek-v4-pro` | best performance-per-cost for implementation |
| tester | DeepSeek V4 Flash | `deepseek/deepseek-v4-flash` | cheap, high-volume (but see test caveat) |
| reviewer | GLM 5.2 | `z-ai/glm-5.2` | your Gate 1 — never downgrade; catches subtle issues |
| docs | MiMo V2.5 Pro | `xiaomi/mimo-v2.5-pro` | fewest tokens/task; built for high-volume |
| debugger | GLM 5.2 | `z-ai/glm-5.2` | ambiguous, high blast radius |
| oracle / advise | GLM 5.2 | `z-ai/glm-5.2` | hard-call diagnosis wants top intelligence |
| scout / explore | FastContext-4B (local) | — (local, see §7) | dedicated recon; general fallback: DeepSeek V4 Flash |

Three hand-adjustments worth making:

- **Long-running builders → Kimi K2.7 Code** (`moonshotai/kimi-k2.7-code`) over DeepSeek.
  Kimi is the most disciplined Chinese family on tool-call stability across long sessions and
  is purpose-built for sub-agent parallelism; DeepSeek's edge is price, but its tool support
  lags on long trajectories. If a builder fires hundreds of tool calls per task, Kimi earns
  its slightly higher cost.
- **Token-efficiency tier → MiMo V2.5 Pro** for any high-volume cheap role (tester / docs /
  a general-model scout). It uses the fewest tokens per task in the group — exactly your
  outcome-per-token goal.
- **The routing rule in one line:** easy / high-volume → DeepSeek V4 Flash or MiMo;
  hard / ambiguous → GLM 5.2. That single split is most of the cost optimization.

Two caveats specific to an all-Chinese fleet:

- **Tests are the universal weak spot.** Across benchmarks, Chinese models write plenty of
  tests but under-mock and skimp on error handling ("coverage theater"). Don't trust the
  tester tier on its own — this is *why* Gate 1's reviewer stays on GLM 5.2.
- **Jurisdiction & content.** Direct Chinese APIs route through Chinese-jurisdiction servers
  and carry content restrictions on politically sensitive topics. Routing via OpenRouter
  (US-proxied) or self-hosting sidesteps the data-residency issue; the content restrictions
  are irrelevant to coding but worth knowing.

---

## 3. Pi

Pi gives you orchestration **primitives** and expects you to assemble the topology. That
matches the "own your harness" goal — your coordination logic lives in TS/YAML you control.

### 3.1 Install & auth

```bash
npm install -g @mariozechner/pi-coding-agent      # provides the `pi` command
# or run ephemerally: npx @mariozechner/pi-coding-agent
```

Put provider keys in `~/.pi/agent/auth.json` (these take priority over env vars):

```json
{
  "deepseek":  { "type": "api_key", "key": "sk-..." },
  "zhipuai":   { "type": "api_key", "key": "..." },
  "openrouter":{ "type": "api_key", "key": "sk-or-..." }
}
```

Env vars work too (`DEEPSEEK_API_KEY`, `OPENROUTER_API_KEY`, ...). No Anthropic key belongs
in the harness — the fleet is all-open, and Claude reviews out-of-loop in Claude Code (§0).
Do **not** use `/login` with a Claude Pro/Max account here — see §0.

### 3.2 Register your models

`~/.pi/agent/models.json` — define any provider that speaks an OpenAI-compatible API
(cloud or local). The `api: "openai-completions"` routing is what makes arbitrary
endpoints work.

```json
{
  "providers": {
    "deepseek": {
      "baseUrl": "https://api.deepseek.com/v1",
      "api": "openai-completions",
      "models": [{ "id": "deepseek-chat" }, { "id": "deepseek-reasoner" }]
    },
    "ollama": {
      "baseUrl": "http://localhost:11434/v1",
      "api": "openai-completions",
      "apiKey": "ollama",
      "models": [{ "id": "qwen3-coder" }, { "id": "qwen2.5-coder:7b" }]
    }
  }
}
```

Useful compat flags for self-hosted / partially-compatible servers:
- `compat: { "maxTokensField": "max_tokens", "supportsUsageInStreaming": false }` per
  provider or per model.
- For local Qwen servers needing `chat_template_kwargs.enable_thinking`, use the
  `qwen-chat-template` api variant.

### 3.3 Define the agents

Agents are **markdown files with YAML frontmatter** plus a system-prompt body. Global:
`~/.pi/agent/agents/*.md`. Project-specific: `.pi/agents/*.md` (project wins on name
collisions). Frontmatter fields include: `name`, `description`, `model`, `tools`,
`disallowedTools`, `color`, `maxTurns`, `initialPrompt`, `background`,
`criticalSystemReminder`.

`~/.pi/agent/agents/backend.md`:

```markdown
---
name: backend
description: Implements backend/API features in TypeScript/Node. Use for server-side work.
model: deepseek/deepseek-chat
color: blue
maxTurns: 40
---
You are the backend specialist for a TypeScript/Node project.
- Follow the existing error-handling and module patterns.
- Run `npm run check` after edits; do not touch frontend code.
- Hand back a short summary of what changed and why.
```

Repeat for `ui.md`, `tester.md`, `reviewer.md`, `docs.md`, `debugger.md`, `planner.md`.
Pi also ships built-ins you can reuse instead of authoring from scratch: **scout,
researcher, planner, worker, reviewer, oracle**.

### 3.4 Per-agent models (two ways)

1. **Inline** — the `model:` field in each agent's frontmatter (shown above). Simplest.
2. **Central override** — `~/.pi/agent/settings.json` (user) or `.pi/settings.json`
   (project). Built-in agents otherwise inherit your default model, so this is how you pin
   them and add fallbacks:

```json
{
  "subagents": {
    "agentOverrides": {
      "reviewer": {
        "model": "zhipuai/glm-5",
        "thinking": "high",
        "fallbackModels": ["deepseek/deepseek-reasoner"]
      },
      "docs": { "model": "deepseek/deepseek-flash" }
    }
  }
}
```

### 3.5 The orchestrator + the team

In Pi, **the interactive `pi` session you're typing into is the lead/primary** — that's
your orchestrator. It dispatches to the other agents. Two composition styles:

- **Teams** (parallel dispatch): list the agents that form a team in
  `~/.pi/agent/agents/teams.yaml`. Calling `team_create` makes your current session the
  team lead; it then dispatches to the named agents, each running in its own isolated
  context with its own model.

  ```yaml
  # illustrative — confirm exact keys against your Pi version
  teams:
    dev:
      - planner
      - backend
      - ui
      - tester
      - reviewer
  ```

- **Chains** (sequential pipeline): `agent-chain.yaml` / `*.chain.md`, where one agent's
  output becomes `$INPUT` to the next (e.g. plan → build → review → verify).

Give the lead an orchestrator persona by putting routing rules in `~/.pi/agent/AGENTS.md`
(global) or the project `AGENTS.md` — e.g. "Delegate server work to `backend`, UI to
`ui`, always send finished work through `reviewer` before reporting back."

### 3.6 Run

```bash
cd my-project
pi                      # interactive; you talk to the lead/orchestrator
pi -p "Ship the auth endpoints"   # one-shot, non-interactive
```

---

## 4. OpenCode

OpenCode is batteries-included: you declare agents in config, set a model per agent, and
a **primary** agent delegates to **subagents** via the built-in Task tool.

### 4.1 Install & auth

```bash
npm i -g opencode-ai@latest
# or: curl -fsSL https://opencode.ai/install | bash   |   brew install sst/tap/opencode
```

```bash
opencode auth login     # pick a provider, repeat per provider
```

- **No Anthropic provider here.** The fleet is all-open, so skip Anthropic in
  `opencode auth login` entirely — Claude reviews out-of-loop in Claude Code (§0).
- **Open models:** run `opencode auth login` for DeepSeek, GLM/Z.ai, Moonshot
  (Kimi), Qwen, MiniMax — or point at a local Ollama/vLLM endpoint. Exact provider slugs
  come from `models.dev`; the login picker lists them. Auth is stored in
  `~/.local/share/opencode/auth.json`.
- **Shortcut option:** OpenCode Zen (pay-as-you-go gateway) or **OpenCode Go**
  (~$10/mo bundling GLM, Kimi, Qwen, DeepSeek, MiniMax, MiMo, hosted US/EU/SG,
  zero-retention) if you'd rather not juggle keys. Trade-off: you depend on their failover
  instead of your own.

### 4.2 Define agents — JSON config

`opencode.json` at the project root. Model format is `provider/model-id`. If an agent has
no `model`, primary agents use the global model and subagents inherit the model of the
primary that invoked them — so set `model` explicitly to get distinct defaults.

```json
{
  "$schema": "https://opencode.ai/config.json",
  "agent": {
    "orchestrator": {
      "mode": "primary",
      "model": "qwen/qwen3.6-plus",
      "prompt": "You are the orchestrator. You talk to the user and coordinate the team. Delegate server work to @backend, UI to @ui, tests to @tester, and always route finished work through @reviewer before reporting back. Produce a branch/PR as the deliverable. Keep a running plan.",
      "permission": { "task": { "*": "allow" } }
    },
    "backend": {
      "mode": "subagent",
      "model": "deepseek/deepseek-chat",
      "description": "Implements backend/API features in TypeScript/Node.",
      "tools": { "write": true, "edit": true, "bash": true }
    },
    "reviewer": {
      "mode": "subagent",
      "model": "zhipuai/glm-5",
      "description": "Reviews code for security, performance, correctness before merge.",
      "temperature": 0.1,
      "tools": { "write": false, "edit": false }
    },
    "docs": {
      "mode": "subagent",
      "model": "deepseek/deepseek-flash",
      "description": "Writes docs and comments."
    }
  }
}
```

### 4.3 Define agents — Markdown (good for long prompts)

Filename becomes the agent name. Global: `~/.config/opencode/agents/`. Project:
`.opencode/agents/`.

`.opencode/agents/tester.md`:

```markdown
---
description: Writes and runs tests; verifies nothing broke. Invoke after implementation.
mode: subagent
model: deepseek/deepseek-flash
temperature: 0.1
tools:
  write: true
  edit: true
  bash: true
---
You are the test specialist. Write focused tests for the change at hand, run the suite,
and report pass/fail with the minimal diff needed to go green. Don't refactor app code.
```

### 4.4 Orchestrator & delegation control

- `mode: primary` = an agent you talk to directly (switch primaries with Tab / `@`).
  `mode: subagent` = invoked by a primary via the Task tool, or by you with `@name`.
- Subagents are auto-selected by their `description`, so write descriptions as routing
  triggers ("Invoke for server-side work", "Invoke before merge").
- Gate who-can-call-whom with `permission.task` glob rules (last match wins):

  ```json
  "permission": { "task": { "*": "deny", "orchestrator-*": "allow" } }
  ```
- `hidden: true` keeps an internal subagent out of the `@` menu while still callable by
  the model.

### 4.5 Run

```bash
cd my-project
opencode                # talk to the primary (orchestrator); it delegates
opencode run "Add the auth endpoints and get them reviewed"   # headless
```

---

## 5. Self-hosted vs cloud

| | Self-hosted | Cloud |
|---|---|---|
| **Serve with** | vLLM, SGLang, Ollama, LM Studio, llama-server | provider API, OpenRouter, OpenCode Zen/Go |
| **Good fit** | data control, fixed cost, the cheap worker tier | the strong orchestrator/reviewer tier, bursty load |
| **Wire-up (Pi)** | `models.json` provider w/ local `baseUrl` | `auth.json` key + built-in/`models.json` provider |
| **Wire-up (OpenCode)** | `opencode auth login` → local endpoint / Ollama | `opencode auth login` per provider |

Practical hybrid: self-host the **tester/docs** tier on a local GPU box (high call volume,
low stakes), and use cloud for **orchestrator/reviewer/debugger** (low volume, high stakes).
Both tools let you mix freely per agent.

---

## 6. Suggested split & first-run checklist

**Which tool on which project**
- Put **Pi** on the project where you want to *author the coordination logic* — custom
  teams/chains, Pi-to-Pi peer messaging, hooks. It rewards owning the harness.
- Put **OpenCode** on the project where you want a *working fleet fast* — declarative
  agents, per-agent model + fallback, and the Go/Zen bundle for cheap Chinese models.

**Before you scale up, verify the spine on one tiny task each:**
1. Orchestrator receives your request and *delegates* (you see a subagent fire), rather
   than doing everything itself.
2. Each agent is actually running its assigned model (check logs / token attribution — not
   silently inheriting the default).
3. **Gate 1** — the in-loop reviewer runs **before** work is reported back as done, on a
   strong open model (not a cheap tier).
4. The tester's failures actually loop back to the builder, not get summarized away.
5. **No Anthropic credentials in the harness.** The fleet's deliverable is a branch/PR;
   **Gate 2** is you opening that diff in Claude Code for Claude's review, out-of-loop.

Get those five green on a one-file change before pointing the fleet at the real brief.

---

## 7. Scout + FastContext-4B for code search

The recon seat (scout / explore / explorer) is your biggest token lever, because repository
exploration is ~46% of a main agent's tokens. Two stacked savings live here:

1. **Context isolation (the pattern, free today).** The scout does the greps and file reads
   in its *own* throwaway context and returns only a short brief; your main agent never
   carries the twenty files it read. Works with any cheap model in the seat — Pi's `scout`,
   OpenCode's `explore` — with zero infra. Start here.
2. **FastContext-4B (the upgrade).** Microsoft's trained 4B repo-explorer that issues
   parallel READ/GLOB/GREP and returns compact `file:line` citations. It's tuned to do the
   recon in fewer tokens than a general small model. The ~60% headline is the increment over
   an *already-isolated* scout — not over inline exploration.

**Order of operations:** prove the cheap path first. Put a cheap model in the scout seat,
measure main-agent tokens with vs. without on ~5 real tasks. Only if you want tighter
precision do you stand up FastContext. If the FastContext delta is small on your repo, you
never need it.

### Serving FastContext-4B

It's a vanilla Qwen3-4B finetune (MIT-licensed, ChatML), so on your Mac serve it via **Ollama
or MLX with a stock GGUF** — skip SGLang (CUDA-oriented, painful on Apple Silicon). One
caveat: the community ROCmFP4 GGUF is AMD-Strix-only and won't load in stock Ollama; grab or
convert a normal `Q4_K_M`/`Q6_K`/`Q8` GGUF.

### Wiring it in — as a service, not a model

FastContext carries its own tools and loop. If you just set it as a subagent's `model`, the
host feeds it the host's tools (different names than it trained on) and it misfires. Two
clean routes:

- **Service (recommended):** expose one `explore(query) → file:line` call (its CLI, or a thin
  MCP wrapper). Each tool then registers a single external tool; same shape everywhere. In
  the agent's rules file: "to locate code, call `fastcontext explore '<query>'` and read the
  returned ranges — don't grep yourself."
- **Native model:** point the recon subagent's `model:` at the local endpoint — but only
  after confirming the host feeds it READ/GLOB/GREP-shaped tools. Pi/OpenCode/Claude
  Code/Codex can; Cursor's recon is MCP/shell only.

Per tool, the seat is: Pi → `scout`; **OpenCode → `explore`** (not `scout` — that's
dependency research); Codex → `explorer`; Claude Code / Cursor → an explore agent you author.

### Worktrees & scale

FastContext **doesn't index** — it greps live each call, so for parallel worktrees there's
nothing to build or keep in sync. Point each call at that worktree's root; N worktrees = N
path-scoped calls, zero staleness. The flip side: nothing is amortized, so on true
millions-of-LOC the live scan starts to drag — that's the only point you'd add a coarse
retrieval/index substage underneath it (and then per-worktree index invalidation comes back).

### The one verify step

Run a single exploration and confirm the agent gets **correct `file:line` citations and
actually reads those lines** — not that FastContext's tool calls printed as raw text in the
transcript (printing-vs-parsing is the failure mode). Test on your **weakest language** (the
Python infra / any legacy code), not the TS UI — FastContext's trained priors are strongest
on modern mainstream repos and fray on older or niche code. A token saving that points at the
wrong lines is negative value.

---

## 8. Orchestration & coordination

You talk to **one agent — the orchestrator.** It decomposes goals, dispatches to specialists,
collects results, and comes back to you. This is the orchestrator-worker pattern; the rules
below are what keep it from degenerating.

**Hub, not mesh.** Subagents report *up* to the orchestrator; they do **not** message each
other. A reviewer that finds a bug doesn't ping the backend agent — it returns the finding to
the orchestrator, which dispatches the fix. This is what preserves your single point of
visibility. (Pi's direct Pi-to-Pi mailbox is the mesh model — skip it; it undercuts the
orchestrator-only design.)

**Routing a found issue** (e.g. reviewer → fix): four separate roles, no agent does two.
1. Reviewer reports **what, not who** — a structured finding `{file, line, severity, problem,
   suggested fix}`. It has no write access, so the gate stays honest.
2. Orchestrator maps **file → owner** (it assigned ownership during decomposition).
3. Orchestrator dispatches a fix task to that builder, then **re-runs the reviewer**. Loop
   until clean, then report up to you.

**Escalation discipline.** The orchestrator comes back to *you* only for genuine forks — a
product decision, a contract change, an agent stuck after N retries — and decides everything
else itself. Define that threshold in its prompt; too chatty wastes the point, too autonomous
guesses wrong on things you cared about.

**Durability:** back the loop with a shared findings file (`REVIEW.md` / `findings.json` the
orchestrator reads/writes) so issues survive context limits and you can see the queue.

**Parallel changes the orchestrator's hard job from *dispatch* to *decompose + merge*.** With
parallel agents in worktrees (§9), coordination becomes **waves**: sequence the dependencies,
parallelize within a wave.
- **Contract-first:** a sequential planning step *freezes the shared interface/types*, then
  backend + ui build against that frozen contract in parallel. (Don't fan out dependent tasks.)
- **Disjoint ownership:** assign non-overlapping files per agent so change sets don't collide.
  A shared file (route registry, barrel export) is its own small *sequential* step, not two
  agents editing it at once.
- **Integrate, then verify:** Gate 1 (reviewer) and the meaningful test run happen on the
  **merged** tree, not per-worktree — per-worktree tests only prove a slice works in isolation.

---

## 9. Parallel execution, worktrees & git

**Built-in fan-out isolates *context*, not the *filesystem*.** When the orchestrator spawns
parallel subagents (OpenCode Task tool, Pi team dispatch), each gets its own context window
but they share one working directory by default — so parallel writers collide. Worktree-per-
agent in Pi/OpenCode is a **layer you add**, not a native flag (contrast Claude Code, which
has `isolation: worktree` built in).

Two ways to add it:
- **Runner (least work):** `git-worktree-runner` (supports OpenCode) or `agent-of-empires`
  (tmux + worktrees for OpenCode/Pi); for Pi, the community `oat` runner. These handle branch
  creation, dependency install, and cleanup.
- **DIY:** provision per task from a hook/the orchestrator —
  ```bash
  git worktree add -b wt/backend ../wt/backend main      # sibling dir, branched off main
  cp .env ../wt/backend/ && (cd ../wt/backend && npm install)   # worktrees have neither
  git merge wt/backend                                   # integrate (= Gate-1 + Claude-diff target)
  git worktree remove ../wt/backend && git branch -d wt/backend
  ```

**Git strategy: one branch, no PRs.** Work lands on `main` directly. No feature branches, no
PR ceremony — Gate 2 needs a *diff*, not a PR (`git diff` is enough). The only branches are the
**throwaway per-worktree handles** git requires (two worktrees can't share one) — created and
destroyed per task, not workflow. **Commit per step, merge often:** at volume, big infrequent
merges are what hurt; small frequent integrations stay clean and give granular rollback.

**Worktrees isolate files, not shared services** — the gotchas that bite:
- **Ports** — offset per worktree (`PORT=$((3000 + i))`), or the 2nd dev server fails.
- **Database** — per-worktree SQLite / test-DB-prefixed-by-branch; shared DB + parallel
  migrations corrupt state.
- **Docker** — prefix container/compose names by branch.
- **`.env` + `node_modules`** — a fresh worktree has neither; the provisioning step must copy
  `.env` and install deps (pnpm shared store helps at many worktrees).
- **Cleanup** — prune on completion or stale worktrees pile up fast.

Only turn this on at **Phase 4** (§10) — sequential phases need none of it.

---

## 10. Rollout — add one axis at a time

Don't stand the whole fleet up at once; light up one new thing per phase, so when something
breaks you know what broke.

- **Phase 0 — environment.** Scaffold + a real `npm run check` (typecheck+lint+test) that runs
  green fast from the CLI, plus a thin `AGENTS.md` (repo-wide facts only). The fleet delegates
  its judgment to this; if it's not trustworthy, every agent is blind. *No agents yet.*
- **Phase 1 — one agent, one tree, manual review.** Agent edits → runs check → you review the
  diff in Claude Code (Gate 2 only). Move on when the loop is dull.
- **Phase 2 — Gate 1 + mixed models.** Cheap builder + strong reviewer that critiques before
  work returns to you. Proves the self-check works and per-agent routing actually routes.
- **Phase 3 — orchestrator as a chain.** planner → backend → tester → reviewer, **sequential**
  (one writer, no collisions); you talk only to the orchestrator. Proves dispatch + handoffs.
- **Phase 4 — parallel + worktrees.** Turn on the hard part last: disjoint-file agents, worktree
  each, decompose → wave → integrate. Prove merge on the easy case first.
- **Phase 5 — harden + second tool.** Test-on-edit hooks, CI, worktree cleanup, skills accreted
  from real failures — then stand up the second harness on a second project.

Skills don't belong on Day 0 — the only knowledge you write up front is the thin `AGENTS.md`;
skills accrete from Phase 2 on, from failures the tests actually expose.

---

## 11. Telemetry & cost

You can't optimize outcome-per-token without per-agent attribution, and tokens are only half —
the join to pass/fail is the other half.

**Capture seam: a self-hosted LiteLLM proxy** between harness and OpenRouter. One base-URL
swap, no per-harness SDK wiring — whatever tool you run, the proxy sees every token. It logs
prompt/completion/**cached** tokens + cost + latency, and feeds your existing **Langfuse**
(LiteLLM has built-in Langfuse logging — keep your dashboards, the proxy just feeds them
uniformly). For a setup others replay, "run this proxy, point your tool here" beats
instrumenting an SDK into four harnesses.

**Attribution — two tags on every call:**
- **agent** — which role spent it. Most replay-friendly mechanism: a **per-agent OpenRouter
  virtual key** (pure config, works even on harnesses with no metadata passthrough).
- **task_id** — propagated from orchestrator down to every subagent call. This is the **join
  key to `scores.json`** → *tokens per **passing** task* (failed-task tokens are pure waste —
  surface them). Verify your harness actually forwards metadata to subagents; if not, you fall
  back to time-window inference (messy).

**Metrics that matter:** net total tokens/task, tokens-per-passing-task, per-agent share,
prompt-vs-completion-**vs-cached** split (caching/compression shows up here), exploration-token
share (recon's target, §7).

**Cost, for orientation:** an all-open per-role fleet at a moderate cadge (~100 tasks/mo)
lands roughly **$50–75/month** — and the bill is dominated by your *strong* tier (GLM 5.2 on
orchestrator/reviewer/debugger); the cheap tier is rounding error. So cost control = tightening
how much the strong roles *think* (review-loop max rounds, thinking budget), not penny-pinching
the workers. That's ~3× under metered Claude, with parallelism added rather than removed.

---

## Sources / further reading

- OpenCode agents & config: https://opencode.ai/docs/agents/
- OpenCode providers/auth: https://opencode.ai/docs/providers/
- Pi models & custom providers: https://pi.dev/docs/latest/models
- Pi subagents & per-agent overrides: https://pi.dev/packages/pi-subagents
- OpenCode built-in agents (build/plan/general/explore/scout): https://opencode.ai/docs/agents/
- FastContext (Microsoft repo-explorer, 4B/30B): https://github.com/microsoft/fastcontext
- Worktree runners: git-worktree-runner (CodeRabbit); agent-of-empires (tmux + worktrees)
- Telemetry: LiteLLM proxy (docs.litellm.ai) → Langfuse (self-hosted)
- Anthropic third-party subscription-auth policy (Jan–Feb 2026): firecrawl.dev "Claude Code vs OpenCode"; alternativeto.net policy summary.
