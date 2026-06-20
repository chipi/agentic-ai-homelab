# Agentic coding — autonomous code agents

> Reading list for **deeply autonomous coding workflows** — where you
> brief an agent on a goal ("fix this bug + add tests + open a PR")
> and the agent decomposes, plans, executes, and verifies without
> turn-by-turn driving. Goes deeper than
> [`coding-models-local.md`](coding-models-local.md), which covered
> the model + IDE-integration layer.
>
> Legend:
> - ★ = mandatory, read/watch this first
> - ☆ = strongly recommended, second pass
> - · = reference / deep dive, read when you need it

## What this page is

`coding-models-local.md` covered "which model, which IDE plugin"
— the *toolchain* shape. This page covers **the agent harness layer
on top**: how do autonomous coding agents actually plan, execute,
recover, multi-agent-coordinate, and stay safely sandboxed?

The single most important 2026 finding to internalize before reading
further: **the agent harness matters more than the model**. On
Terminal-Bench 2.0 the same model can swing **30-50 percentage
points** depending on which harness wraps it (Claude Code vs.
OpenHands vs. a homegrown loop). [Source: agentic.ai 2026 best
coding agents survey](https://agentic.ai/best/coding-agents).

This page is the reading list for picking, understanding, and
operating that harness.

---

## 0. The paradigm shift — beyond autocomplete

The 2024-2026 shift was from "Tab to complete a line" to "brief the
agent on a goal, walk away." Worth understanding before picking
tools.

| | Item | Why |
|---|---|---|
| ★ | [Beyond Autocomplete: Best Agentic Coding Workflow in 2026](https://kilo.ai/articles/beyond-autocomplete) — Kilo | The clearest framing of the paradigm shift: autocomplete → agentic. Concrete workflow examples, harness comparison.<br>**Why ★:** primary practitioner reference for the shift; cited as the canonical "what changed" essay. |
| ★ | [The Best LLMs for Agentic Coding in 2026 (Real-World, Not Just Benchmarks)](https://dev.to/danishashko/the-best-llms-for-agentic-coding-in-2026-real-world-not-just-benchmarks-96n) — DEV Community | The "real-world vs. benchmark" framing — many high-benchmark models fail in real agentic loops. Sobering reality check.<br>**Why ★:** primary source for the harness-matters-more-than-model insight; quantifies the Terminal-Bench swings. |
| ★ | [18 Best AI Coding Agents in 2026](https://agentic.ai/best/coding-agents) — Agentic.ai | Comprehensive 2026 agent landscape, including the autonomous-mode capabilities of each.<br>**Why ★:** primary 2026 landscape reference; covers Claude Code, Cursor, OpenHands, SWE-agent, Cline, Aider in agent mode, and emerging entrants. |

---

## 1. Plan → Execute → Reflect — the canonical loop

Every modern coding agent runs some variant of:
**Localize → Plan → Patch → Validate → (Reflect if failed → retry)**.
This is the dominant pattern; understanding it lets you reason about
any specific harness.

| | Item | Why |
|---|---|---|
| ★ | [ReAct: Synergizing Reasoning and Acting in LMs](https://arxiv.org/abs/2210.03629) — Yao et al. 2022 | The Thought-Action-Observation loop. Already in [`llm-end-to-end.md`](llm-end-to-end.md) § 20 as ★. **Foundational** — every modern coding agent is a ReAct derivative.<br>**Why ★:** primary source; short; self-contained; the loop every harness implements. |
| ★ | [Reflexion: an autonomous agent with dynamic memory and self-reflection](https://arxiv.org/abs/2303.11366) — Shinn et al. 2023 | Adds the reflection step: when a patch fails validation, the agent reflects on *why* before retrying.<br>**Why ★:** primary source for the "retry with reasoning" pattern that powers modern coder agents. |
| ★ | [From Plan to Action: How Well Do Agents Follow the Plan?](https://arxiv.org/html/2604.12147v1) — recent 2026 | Empirical study of plan-following in coding agents. Surprising failure modes (agents drift from their own plans mid-execution).<br>**Why ★:** primary source for the "your agent's plan ≠ what it executes" reality; important for failure analysis. |
| ☆ | [Code to Think, Think to Code: A Survey on Code-Enhanced Reasoning and Reasoning-Driven Code Intelligence](https://arxiv.org/abs/2502.19411) — 2025 | Recent survey of the interplay between reasoning and code generation. Useful background. |
| ☆ | [Ambig-SWE: Interactive Agents to Overcome Underspecificity in Software Engineering](https://arxiv.org/abs/2502.13069) — 2025 | What happens when the user's brief is ambiguous (which is most of the time). Important for production agent UX. |
| · | [Confucius Code Agent: Scalable Agent Scaffolding for Real-World Codebases](https://arxiv.org/abs/2512.10398) — 2025 | Scaling agent scaffolds to real (large) codebases. When toy benchmarks don't translate. |

---

## 2. Agent-Computer Interface (ACI) — how agents touch the system

SWE-agent's key contribution was formalizing the **Agent-Computer
Interface** — the structured surface that exposes editor, shell, and
test runners as agent actions. This is the architectural insight
behind every modern coding harness.

| | Item | Why |
|---|---|---|
| ★ | [SWE-agent — original paper](https://arxiv.org/abs/2405.15793) — Yang et al. 2024 + [GitHub](https://github.com/SWE-agent/SWE-agent) | Introduces the ACI concept. **Required reading** to understand why some harnesses outperform others on the same model.<br>**Why ★:** primary source for the architectural insight that explains the Terminal-Bench swing across harnesses. |
| ★ | [OpenHands (formerly OpenDevin) — GitHub](https://github.com/All-Hands-AI/OpenHands) | The most mature open-source agentic-coding framework. Sandboxed shell + bash + Python + file editing. ★ as the **primary open implementation** to learn from.<br>**Why ★:** primary open-source reference implementation of the ACI pattern; you can read the code. |
| ☆ | [Skywork-SWE: Unveiling Data Scaling Laws for Software Engineering in LLMs](https://arxiv.org/abs/2506.19290) — 2025 | Scaling laws specifically for coding-agent training data. Useful when you're considering fine-tuning. |
| ☆ | [daVinci-Env: Open SWE Environment Synthesis at Scale](https://arxiv.org/abs/2603.13023) — 2026 | Synthetic environment generation for training coder agents at scale. Frontier-research-level. |

---

## 3. Production coding agents — the picks for 2026

### Claude Code (cloud-bound, terminal-native)

| | Item | Why |
|---|---|---|
| ★ | [Claude Code — Anthropic docs](https://docs.anthropic.com/en/docs/claude-code) | Vendor primary source. Terminal-native agentic coder; reads codebase, edits files, runs commands, integrates with dev tools.<br>**Why ★:** primary vendor doc; the agent the homelab actually uses for cloud-routed coding. |
| ★ | [AI Coding Agents: Claude Code vs Cursor vs Codex 2026](https://www.digitalapplied.com/blog/ai-coding-agents-claude-code-cursor-codex-replit-2026) — Digital Applied | The clearest 2026 comparison. Claude Code = terminal-first goal-level delegation; Cursor = IDE-first inline assistance.<br>**Why ★:** primary practitioner comparison; the framing ("which mode are you in?") clarifies when to reach for which tool. |
| ★ | [Cursor vs Claude Code in 2026: Features, Pricing](https://claudefa.st/blog/tools/extensions/claude-code-vs-cursor) — ClaudeFast | Side-by-side feature comparison. **Most production teams in 2026 use both** — Cursor for line-level edits, Claude Code for goal-level autonomous work.<br>**Why ★:** primary source for the "use both" pattern; matches the homelab's actual workflow. |

**Distinctive Claude Code capability (2026): Agent Teams.** Multiple
Claude instances working as a coordinated team — one leads, others
execute in parallel, teammates communicate directly and work in
separate context windows. The Claude Code surface also exposes a
**1M-token native context** with no surcharge past 200K, enabling
much longer autonomous sessions before compaction. [Source: Digital
Applied 2026 comparison](https://www.digitalapplied.com/blog/ai-coding-agents-claude-code-cursor-codex-replit-2026).

### Cursor (cloud-bound, IDE-first)

| | Item | Why |
|---|---|---|
| ★ | [Cursor — official docs](https://docs.cursor.com/) | Vendor primary source. IDE-first; inline assistance + agent mode for multi-file edits. |
| ☆ | [Best AI Code Editors 2026: Comparison of Cursor, Lovable, Claude Code & More](https://ijonis.com/en/ai-code-editor-comparison) — IJONIS | Broader IDE-first comparison including emerging entrants. |

### OpenHands (open-source, sandboxed)

| | Item | Why |
|---|---|---|
| ★ | [OpenHands — GitHub + docs](https://docs.all-hands.dev/) | The leading open agentic-coding framework. Read this to understand how a serious agent harness is actually built.<br>**Why ★:** primary open-source reference; if you ever want to roll your own agent, this is the codebase to learn from. |
| ★ | [SWE-agent and OpenHands are purpose-built async PR solvers](https://www.morphllm.com/ai-coding-agent) — Morph | The "async PR solver" framing. These two are the production-grade picks for issue-ticket-triggered automation.<br>**Why ★:** primary practitioner reference for understanding when to reach for OpenHands vs. an interactive agent. |

### Cline + Aider (interactive open-source)

Already covered in [`coding-models-local.md`](coding-models-local.md)
§ 4. In agent mode:

- **Cline** in agent mode: VS Code-native; plan-then-execute with
  approval gates.
- **Aider** in `--browser` agent mode: terminal-native; git-commit-per-change.

### Codex (OpenAI's coder agent, May 2026 release)

| | Item | Why |
|---|---|---|
| ☆ | OpenAI Codex (2026) — referenced across the 2026 comparisons | Newer entrant in the autonomous-coding space; backed by the OpenAI Agents SDK + Codex-style filesystem tools. |

---

## 4. Multi-agent coding — coordinated teams of code agents

The 2026 frontier: instead of one agent doing the whole job, multiple
specialized agents (planner / coder / reviewer / debugger / tester)
coordinate. Distinct from "single agent with multiple tools" — this
is **multiple LLM instances in conversation**.

| | Item | Why |
|---|---|---|
| ★ | [Claude Code Agent Teams](https://docs.anthropic.com/en/docs/claude-code) — Anthropic | Production-grade multi-Claude coordination. Currently the most polished implementation.<br>**Why ★:** primary vendor doc for the most-deployed multi-agent coding pattern. |
| ★ | See [`agent-orchestration.md`](agent-orchestration.md) § 1 (Architecture patterns) | Supervisor / hierarchical / swarm — the architectural patterns. Apply to coding-specific multi-agent systems. |
| ☆ | [Skywork-SWE — multi-agent scaling laws](https://arxiv.org/abs/2506.19290) — 2025 | Empirical work on what scaling laws look like for multi-agent coding systems. |
| ☆ | [Confucius Code Agent — scalable scaffolding](https://arxiv.org/abs/2512.10398) — 2025 | Scaffolding patterns for large codebases. |

---

## 5. Sandboxes — running autonomous coding agents safely

If an agent has shell access, that shell access is real. Sandboxing
moved from "nice to have" to **mandatory infrastructure** in 2026.

Driving incident: frontier models' success on **apprentice-level
cybersecurity tasks** rose from under 10% in late 2023/early 2024 to
roughly 50% in 2025, with the first expert-level task completed by
a model during 2025. Pre-2026 sandbox designs are no longer
sufficient. [Source: BeyondScale 2026 AI Agent Sandboxing
Guide](https://beyondscale.tech/blog/ai-agent-sandboxing-enterprise-security-guide).

| | Item | Why |
|---|---|---|
| ★ | [Best Code Execution Sandboxes for AI Agents in 2026](https://modal.com/resources/best-code-execution-sandboxes-ai-agents) — Modal | Comprehensive 2026 platform comparison: Modal (gVisor), E2B (microVM), Blaxel (microVM), Daytona, Northflank (Kata + gVisor, 2M+ workloads/month).<br>**Why ★:** primary practitioner reference for picking a sandbox platform; covers isolation strength, session duration, GPU support tradeoffs. |
| ★ | [AI Agent Sandbox: How to Safely Run Autonomous Agents in 2026](https://www.firecrawl.dev/blog/ai-agent-sandbox) — Firecrawl | The "why sandboxing now matters more" framing. CVEs and incident reports from 2026.<br>**Why ★:** primary 2026 source for the threat model; specific CVEs (CVE-2025-59528, the Antigravity sandbox escape) calibrate what "secure" means. |
| ☆ | [What Is an Agent Execution Sandbox?](https://www.augmentcode.com/guides/agent-execution-sandbox) — Augment | Foundational explainer if you're new to the sandboxing question. |
| ☆ | [Top Sandbox Platforms for AI Code Execution in 2026](https://www.koyeb.com/blog/top-sandbox-code-execution-platforms-for-ai-code-execution-2026) — Koyeb | Companion comparison; useful as a sanity-check second source. |
| ☆ | [AI Agent Sandboxing: Enterprise Security Guide 2026](https://beyondscale.tech/blog/ai-agent-sandboxing-enterprise-security-guide) — BeyondScale | The enterprise-security framing; useful when you're justifying spend on real sandboxing infrastructure. |
| · | [What's the best code execution sandbox for AI agents in 2026?](https://northflank.com/blog/best-code-execution-sandbox-for-ai-agents) — Northflank | Vendor-biased but technically detailed. |
| · | [NVIDIA OpenShell and the Best AI Sandbox Platforms in 2026](https://www.alphamatch.ai/blog/nvidia-openshell-ai-sandbox-platforms-2026) — Alphamatch | NVIDIA's entry into the sandboxing space. |

### Isolation technology summary

| Platform | Isolation tech | Sweet spot |
|---|---|---|
| **Modal** | gVisor containers | General-purpose, GPU support, fast spin-up |
| **E2B** | microVM | Hardware-level isolation, longer sessions |
| **Blaxel** | microVM | Same; competitive alternative to E2B |
| **Daytona** | (mixed) | Dev-environment-flavored sandboxes |
| **Northflank** | Kata Containers + gVisor | High-scale production (2M+ workloads/month) |
| **NVIDIA OpenShell** | (NVIDIA-specific) | GPU-heavy agent workloads |

---

## 6. Benchmarks for coding agents

Already covered in [`coding-models-local.md`](coding-models-local.md)
§ 2 for raw models. For **agents specifically**, the relevant
benchmarks differ — they measure harness + model + sandbox together.

| | Item | Why |
|---|---|---|
| ★ | [Terminal-Bench](https://benchmarkingagents.com/terminal-bench/) — Stanford 2024-2025 | 89 hand-crafted human-verified tasks across scientific computing, SWE, ML, security, sysadmin, data science. Tier 1 / Tier 2 / Tier 3 difficulty. Frontier agents: 70s on tier 1, 50s on tier 2, 25-35% on tier 3.<br>**Why ★:** primary source for the "agent harness matters" insight; the same model swings 30-50pts across harnesses. |
| ★ | [SWE-Bench Verified leaderboard 2026](https://www.codeant.ai/blogs/swe-bench-scores) — CodeAnt | Already in [`coding-models-local.md`](coding-models-local.md) § 2. The standard "real GitHub bug fix" benchmark.<br>**Why ★:** primary live leaderboard; check before any major harness/model decision. |
| ☆ | [AI Agent Benchmarks 2026: 6 Tests That Matter](https://decodethefuture.org/en/ai-agent-benchmarks-2026/) — decodethefuture | The 6 benchmarks that carry signal: GAIA, SWE-Bench Verified, OSWorld, Tau²-Bench, WebArena, METR HCAST + Time Horizons. |
| ☆ | [AI Agent Benchmarking Infrastructure on GPU Cloud: Run SWE-bench, GAIA, Terminal-Bench, OSWorld at Scale](https://www.spheron.network/blog/ai-agent-benchmarking-gpu-cloud-swebench-gaia/) — Spheron | When you want to run the benchmarks yourself, not just read scores. |
| · | [The Hierarchy of Agentic Capabilities](https://arxiv.org/abs/2601.09032) — 2026 | Evaluation framework distinguishing capability tiers. |
| · | [Beyond Accuracy: A Multi-Dimensional Framework for Evaluating Enterprise Agentic AI Systems](https://arxiv.org/abs/2511.14136) — 2025 | Eval beyond pass/fail — latency, cost, safety, robustness. |

---

## 7. The homelab pattern — Claude Code + opencode + coder-next

The homelab's actual agentic-coding setup:

```
[ Claude Code         ] →  cloud Claude Opus 4.7    (hard tasks, cloud-bound)
[ opencode CLI        ] →  http://dgx:9000/v1       (local Qwen3-Coder-Next via vLLM)
[ Cursor / VS Code+Continue ] → mixed              (line-level edits)
```

Workflow: Claude Code for goal-level delegation when quality matters
more than latency or cost; opencode + vLLM coder-next for routine
agentic work on the homelab's own codebase; Cursor + Continue for
inline assistance.

This pattern is the **practical "use all three" pattern** the 2026
guides recommend (Digital Applied: "most production teams in 2026
use both Cursor and Claude Code") plus the local vLLM tier for the
cost-sensitive bulk of work.

References:
- [`coding-models-local.md`](coding-models-local.md) § 6 Recipe 3 —
  the hybrid local + cloud setup that maps to this pattern.
- [`infra/vllm/coder-next/`](https://github.com/chipi/agentic-ai-homelab/tree/main/infra/vllm/coder-next) —
  the working coder-next vLLM stack.
- [`infra/dgx/bin/gpu-mode-swap.sh`](https://github.com/chipi/agentic-ai-homelab/blob/main/infra/dgx/bin/gpu-mode-swap.sh)
  — the GPU-ownership contract.

---

## Reading order if you have a single afternoon

1. ★ Kilo "Beyond Autocomplete" — paradigm shift orientation
2. ★ "Real-World, Not Just Benchmarks" — the harness-matters insight
3. ★ ReAct paper (already in `llm-end-to-end` § 20) — the foundational loop
4. ★ SWE-agent paper — the ACI architectural insight
5. ★ Modal sandbox comparison — pick your sandbox platform
6. Skim Claude Code docs + OpenHands repo to see real implementations

## Reading order if you have a week

- **Day 1**: Paradigm shift (Kilo, DEV "Real-World")
- **Day 2**: Foundational loops — ReAct + Reflexion + Plan-to-Action
- **Day 3**: Agent-Computer Interface — SWE-agent paper + OpenHands codebase tour
- **Day 4**: Production agents — Claude Code, Cursor, OpenHands (read docs + try each)
- **Day 5**: Multi-agent coding — Claude Code Agent Teams, Skywork-SWE
- **Day 6**: Sandboxing — Modal comparison + Firecrawl threat model + pick a platform
- **Day 7**: Benchmarks — Terminal-Bench + SWE-Bench Verified + 6-tests survey

---

## Cross-references

- [`coding-models-local.md`](coding-models-local.md) — the **model
  + IDE-integration** layer this page builds on top of. Read it
  first if you're new to running local coding models at all.
- [`agent-orchestration.md`](agent-orchestration.md) — the
  **broader multi-agent orchestration** cousin of this page.
  Architecture patterns (supervisor, hierarchical, swarm) and
  framework choices (LangGraph, CrewAI, AutoGen) covered there
  apply to coding agents too.
- [`llm-end-to-end.md`](llm-end-to-end.md) § 20 (Tool use &
  function calling) — foundational ★ papers (ReAct, Toolformer,
  MCP).
- [`a16z-ai-canon.md`](a16z-ai-canon.md) § 6.4 Agents — historical
  baseline (Auto-GPT, BabyAGI, Generative Agents, Reflexion).
- [`README.md`](README.md) — section overview and the ★/☆/·
  criteria applied here.
