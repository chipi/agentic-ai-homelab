# Orchestrating agents in autonomous mode

> Reading list for **multi-agent systems and autonomous orchestration**
> — picking an architecture (supervisor / hierarchical / swarm),
> picking a framework (LangGraph / CrewAI / AutoGen / Semantic Kernel
> / Mastra / OpenAI Agents SDK), and the production concerns that
> determine whether agents actually work in autonomous mode.
> Domain-agnostic — coding-agent specifics are in
> [`agentic-coding.md`](agentic-coding.md).
>
> Legend:
> - ★ = mandatory, read/watch this first
> - ☆ = strongly recommended, second pass
> - · = reference / deep dive, read when you need it

## What this page is

The 2024-2025 explosion of agent frameworks consolidated in 2026 to a
small number of mature options. The dominant message from production
practitioners is **the framework debate is largely a distraction —
the gap between a good agent system and a bad one is almost never
the framework. It is the eval pipeline, the observability setup, and
the failure recovery logic.** [Source: Presenc AI 2026 multi-agent
research](https://presenc.ai/research/multi-agent-orchestration-frameworks-2026).

So this page is structured to push you past framework wars into
the questions that matter: **which architecture pattern**, **how do
you evaluate the resulting system**, **how do you recover when it
fails**, and **how do you sandbox the actions it takes**.

---

## 0. Architectures first, frameworks second

Before picking a framework, pick an architecture. Frameworks are
abstractions on top of these patterns; if you understand the
patterns, framework choice is straightforward (and often: doesn't
matter).

| | Item | Why |
|---|---|---|
| ★ | [Multi-Agent Architecture Guide (March 2026)](https://www.openlayer.com/blog/post/multi-agent-system-architecture-guide) — Openlayer | The cleanest 2026 framing of the three dominant topologies: supervisor/hierarchical, orchestrator-worker (~70% of production), swarm.<br>**Why ★:** primary practitioner reference; production-adoption percentages calibrated against real deployments. |
| ★ | [Swarm vs. Supervisor: Multi-Agent Architecture Guide](https://www.augmentcode.com/guides/swarm-vs-supervisor) — Augment | Side-by-side of the two main camps. The 2026 "should it have a coordinator?" decision.<br>**Why ★:** primary source for the binary architectural choice that drives everything else. |
| ★ | [Multi-Agent Systems Explained: 2026 Patterns](https://decodethefuture.org/en/multi-agent-systems-explained/) — decodethefuture | The most thorough pattern survey; covers all common topologies with use-case framing.<br>**Why ★:** primary 2026 pattern reference; comprehensive without being padded. |
| ☆ | [Agent Swarms: Multi-Agent Architectures for AI Systems](https://medium.com/@martinstm/agent-swarms-multi-agent-architectures-for-ai-systems-3e8f11bc1f48) — Tiago Martins, Medium | Deeper on swarm specifically: semantic routing, voting, hierarchical delegation, event-driven coordination. |
| ☆ | [Multi-agent system orchestration patterns](https://www.paiteq.com/blog/multi-agent-orchestration-patterns/) — Paiteq | Practitioner patterns for production multi-agent systems. |
| ☆ | [Multi-Agent AI Orchestration Guide & 2026 Updates](https://www.codebridge.tech/articles/mastering-multi-agent-orchestration-coordination-is-the-new-scale-frontier) — CodeBridge | "Coordination is the new scale frontier" framing — useful for understanding why 2026 attention shifted from model-size to system-design. |
| ☆ | [Multi-Agent Systems: How They Work, When to Use Them, Which Architecture to Choose](https://dev.to/agentsindex/multi-agent-systems-how-they-work-when-to-use-them-and-which-architecture-to-choose-flo) — Agents Index, DEV | Decision-tree framing for picking among the three main patterns. |
| · | [A Hierarchical Multi-Agent System for Autonomous Discovery in Geoscientific Data Archives](https://arxiv.org/abs/2602.21351) — 2026 | Domain-specific case study of a real hierarchical system. |

### The three dominant topologies (read these before picking a framework)

**Supervisor / orchestrator-worker** (~70% of production):
A central supervisor routes work to N specialist subagents and
aggregates their replies. Maintains global conversational state,
inspects retrieved resources, decomposes user queries into sub-tasks.

**Hierarchical** (supervisors of supervisors):
Tiered structure where higher-level agents supervise teams of
lower-level workers. Higher levels focus on coordination and
planning, lower levels on task execution. Used for genuinely complex
workflows.

**Swarm** (peer-to-peer):
Agents hand off to each other directly, no central coordinator, with
a termination rule. Coordinators incorporate semantic routing, voting,
hierarchical delegation, event-driven execution.

> **Production reality check**: Most production agent systems settle
> on a supervisor or sequential pipeline. A smaller but real cohort
> runs hierarchical for genuinely complex workflows. Swarm and
> blackboard shapes show up in research-and-summarise tasks where
> parallel exploration pays. The fanciest architecture isn't the
> best — the simplest one that solves your problem is.

---

## 1. Frameworks — the 2026 picks

The framework landscape consolidated. Six options carry most of the
production weight in 2026; pick by language stack + use case shape.

### Framework decision matrix

| Framework | Stack | Best for | Architecture style |
|---|---|---|---|
| **LangGraph** | Python | Production enterprise multi-agent | Directed graph with conditional edges |
| **CrewAI** | Python | Rapid prototyping, role-based teams | Role-based crews with process types |
| **AutoGen / Semantic Kernel** | Python + .NET | Microsoft stack, research | Conversational GroupChat → graph-based (unified successor) |
| **LlamaIndex Workflows** | Python | Document-heavy, event-driven | Event-driven orchestration |
| **OpenAI Agents SDK** | Python | GPT-centric, sandboxed tools | Native sandbox + sub-agents + MCP |
| **Mastra** | TypeScript | TypeScript stacks | The TS-ecosystem default |
| **Google ADK** | Python | Google Cloud / Vertex AI | Cloud-integrated |

### Reading list

| | Item | Why |
|---|---|---|
| ★ | [The best AI agent frameworks in 2026](https://www.langchain.com/resources/ai-agent-frameworks) — LangChain | Vendor-published comparison (LangChain owns LangGraph). Despite the bias, the comparisons of CrewAI, AutoGen, LlamaIndex Workflows, OpenAI Agents SDK are accurate and clear.<br>**Why ★:** primary vendor-comparison reference; useful even with the LangGraph-favorable bias because the alternatives are described accurately. |
| ★ | [10 AI Agent Frameworks You Should Know in 2026](https://medium.com/@atnoforgenai/10-ai-agent-frameworks-you-should-know-in-2026-langgraph-crewai-autogen-more-2e0be4055556) — ATNO, Medium | Comprehensive 2026 framework landscape with concrete use-case recommendations.<br>**Why ★:** primary practitioner overview; covers what's emerging (Mastra, Microsoft Agent Framework, Google ADK) alongside the established players. |
| ★ | [LangGraph vs CrewAI vs AutoGen vs Custom (2026 Benchmark)](https://tensoria.fr/en/blog/multi-agent-orchestration-comparison) — Tensoria | Quantitative benchmark across the three main frameworks plus "build your own."<br>**Why ★:** primary empirical source for framework throughput/cost differences; the "or just build your own" column is honest. |
| ★ | [Multi-Agent Orchestration Frameworks 2026 (LangGraph, CrewAI, AutoGen, Swarm)](https://presenc.ai/research/multi-agent-orchestration-frameworks-2026) — Presenc AI | The "framework debate is a distraction — what matters is eval + observability + recovery" essay.<br>**Why ★:** primary source for the meta-insight; once you internalize this, framework choice becomes easier. |
| ☆ | [A Detailed Comparison of Top 6 AI Agent Frameworks in 2026](https://www.turing.com/resources/ai-agent-frameworks) — Turing | Side-by-side of LangGraph, CrewAI, AutoGen, LlamaIndex, Semantic Kernel, Mastra. |
| ☆ | [Best Open-Source AI Agent Frameworks 2026: LangGraph, Mastra, CrewAI](https://aihaven.com/guides/best-open-source-ai-agent-frameworks/) — AI Haven | Open-source-first lens; relevant given the homelab's self-hosting orientation. |
| ☆ | [CrewAI vs LangGraph vs AutoGen vs OpenAgents](https://openagents.org/blog/posts/2026-02-23-open-source-ai-agent-frameworks-compared) — OpenAgents | Adds OpenAgents to the comparison. |
| ☆ | [AI Agent Frameworks Comparison 2026: LangGraph vs CrewAI vs AutoGen](https://arsum.com/blog/posts/ai-agent-frameworks/) — Arsum | Companion comparison. |
| ☆ | [LangGraph vs Semantic Kernel vs CrewAI vs LlamaIndex](https://servicesground.com/blog/ai-orchestration-frameworks-comparison/) — ServicesGround | Includes Semantic Kernel which most comparisons skip. |
| ☆ | [Agentic AI Frameworks 2026: LangGraph vs CrewAI vs OpenAI SDK](https://uvik.net/blog/agentic-ai-frameworks/) — Uvik | OpenAI SDK-focused angle. |
| · | [Top 15 AI Agent Frameworks in 2026](https://pickaxe.co/post/top-ai-agent-frameworks) — Pickaxe | When you want the long tail of options. |
| · | [The best open source frameworks for building AI agents in 2026](https://www.firecrawl.dev/blog/best-open-source-agent-frameworks) — Firecrawl | Open-source-only filter. |

### Quick recommendations (the homelab's read)

Based on the comparisons across all the above:

| If you want | Pick |
|---|---|
| **Production at enterprise scale** | LangGraph (largest production footprint) or custom orchestration |
| **Rapid prototyping, demo-to-prototype speed** | CrewAI (strongest demo ergonomics) |
| **Microsoft stack** | Semantic Kernel (the unified successor to AutoGen) |
| **TypeScript stack** | Mastra (19K+ stars, the de facto TS choice) |
| **OpenAI-centric with sandboxed tools** | OpenAI Agents SDK (April 2026 overhaul added native sandboxing + sub-agents + MCP) |
| **Document/data-heavy workflows** | LlamaIndex Workflows (event-driven, purpose-built) |
| **Research / academic** | AutoGen (now merging into Semantic Kernel) |

---

## 2. The Model Context Protocol (MCP) — the standard layer

MCP became the **tool-use standard** for cross-vendor agent
integration in 2025-2026. By 2026 it's table stakes for any serious
AI host — not a differentiator.

| | Item | Why |
|---|---|---|
| ★ | [The 2026-07-28 MCP Specification Release Candidate](https://blog.modelcontextprotocol.io/posts/2026-07-28-release-candidate/) — modelcontextprotocol.io | Official protocol governance announcement. RC locked May 21, 2026; final spec July 28, 2026.<br>**Why ★:** primary source for the protocol itself; required reading if you'll consume or expose MCP. |
| ★ | [MCP: Complete 2026 Guide for AI Integration](https://www.sitepoint.com/model-context-protocol-mcp/) — SitePoint | The clearest 2026 overview of what MCP is, how it works, and what's changed since launch.<br>**Why ★:** primary practitioner reference; the single best "what is MCP and why should I care" link. |
| ★ | [The Complete Guide to Model Context Protocol (MCP) in 2026: Building the USB-C for AI-Native Applications](https://www.essamamdani.com/blog/complete-guide-model-context-protocol-mcp-2026) — Essa Mamdani | The "USB-C for AI" framing — exactly what MCP is. Covers tools, resources, prompts primitives.<br>**Why ★:** primary developer-oriented reference; if you're building agents that use external tools, this is the implementation guide. |
| ☆ | [MCP Cheat Sheet (2026)](https://www.webfuse.com/mcp-cheat-sheet) — Webfuse | Quick-reference card; useful at the keyboard. |
| ☆ | [Developer's Guide to the Model Context Protocol](https://nerdleveltech.com/guides/model-context-protocol) — Nerd Level Tech | Companion implementation guide. |

### What MCP standardized in 2026

- **Three primitives**: tools (executable functions), resources
  (data the agent can read), prompts (reusable prompt templates).
- **Authentication**: OAuth 2.1 as the standard for production
  deployments.
- **SDKs**: TypeScript, Python, Go, Kotlin, Java, C#, Swift, Rust,
  Ruby, PHP — broad enough to consume from almost any stack.
- **Vendor support**: OpenAI added native support early 2026; Google
  followed for Gemini; Ollama, LM Studio, and Claude Code/Desktop
  all speak MCP. Claude Desktop is the canonical reference
  implementation.

The practical implication: **build your agent's tools as MCP servers**
and they work with any MCP-aware client (Claude Code, Cursor,
Cline, opencode, OpenAI Agents SDK, Mastra, etc.) without
re-implementation.

---

## 3. Autonomous loops — long-horizon execution

The hard part of autonomous mode isn't a single action — it's the
**hundred-action sequence** without a human in the loop. Specific
techniques and reading.

| | Item | Why |
|---|---|---|
| ★ | [ReAct paper](https://arxiv.org/abs/2210.03629) — Yao et al. 2022 | The Thought-Action-Observation loop is the foundation of every autonomous mode. Already in [`llm-end-to-end.md`](llm-end-to-end.md) § 20 ★. |
| ★ | [Reflexion: an autonomous agent with dynamic memory and self-reflection](https://arxiv.org/abs/2303.11366) — Shinn et al. 2023 | Adds the reflection step — critical for autonomous mode where failures must be self-detected and recovered.<br>**Why ★:** primary source for the memory + self-correction pattern; foundational. |
| ★ | [Generative Agents: Interactive Simulacra of Human Behavior](https://arxiv.org/abs/2304.03442) — Park et al. 2023 | The Stanford / Google paper on agents with persistent memory and emergent multi-agent behavior in a sandbox town.<br>**Why ★:** primary source for the long-horizon memory + multi-agent emergence research; cited everywhere. |
| ☆ | [From Plan to Action: How Well Do Agents Follow the Plan?](https://arxiv.org/html/2604.12147v1) — 2026 | Empirical study of plan-following over long horizons. Failure modes most teams discover the hard way. |
| ☆ | [SkyRL-Agent: Efficient RL Training for Multi-turn LLM Agent](https://arxiv.org/abs/2511.16108) — 2025 | When you're considering fine-tuning agents for better long-horizon performance. |
| · | [AOrchestra: Automating Sub-Agent Creation for Agentic Orchestration](https://arxiv.org/abs/2602.03786) — 2026 | Auto-generation of sub-agents from goal descriptions. Frontier research. |
| · | [Auto-GPT GitHub](https://github.com/Significant-Gravitas/Auto-GPT) | Already in [`a16z-ai-canon.md`](a16z-ai-canon.md). Historical reference for the first wave of autonomous agents. |
| · | [BabyAGI GitHub](https://github.com/yoheinakajima/babyagi) | Same. The Python script that crystallized "task-decomposition-as-agent." |

---

## 4. Production concerns — what actually matters

Per the meta-insight in the framework section: framework choice is
~10% of the gap; eval + observability + recovery is the other ~90%.
Reading list for the actual production work.

### Eval pipeline

| | Item | Why |
|---|---|---|
| ★ | See [`agentic-coding.md`](agentic-coding.md) § 6 + [`coding-models-local.md`](coding-models-local.md) § 2 | Benchmark literacy is foundational. For agents specifically: Terminal-Bench, GAIA, Tau²-Bench, OSWorld, WebArena, METR HCAST. |
| ★ | [AI Agent Benchmarks 2026: 6 Tests That Matter](https://decodethefuture.org/en/ai-agent-benchmarks-2026/) — decodethefuture | The 6 benchmarks that carry signal in 2026 across coding, general assistance, browser, computer use, policy adherence, long-task ability.<br>**Why ★:** primary 2026 benchmark survey; the "which benchmark for which agent" decision guide. |
| ★ | [AI Agent Benchmark Leaderboard 2026: AgentBench, SWE-bench, GAIA](https://benchmarkingagents.com/agent-benchmarks/) — BenchmarkingAgents | Live leaderboard plus per-benchmark methodology explanations.<br>**Why ★:** primary live-data reference; check before any major agent capability claim. |
| ☆ | [Beyond Accuracy: A Multi-Dimensional Framework for Evaluating Enterprise Agentic AI Systems](https://arxiv.org/abs/2511.14136) — 2025 | When "did it succeed" isn't enough — latency, cost, safety, robustness, drift detection. |
| ☆ | [MAPS: A Multilingual Benchmark for Agent Performance and Security](https://arxiv.org/abs/2505.15935) — 2025 | Security-aware multilingual eval. |
| ☆ | [AI Agent Benchmarking Infrastructure on GPU Cloud](https://www.spheron.network/blog/ai-agent-benchmarking-gpu-cloud-swebench-gaia/) — Spheron | When you want to run the benchmarks yourself. |

### Observability + monitoring

| | Item | Why |
|---|---|---|
| ★ | The homelab's [observability stack](https://github.com/chipi/agentic-ai-homelab/tree/main/infra/observability) | Working example: Grafana Alloy → Cloud, scraping vLLM `/metrics`, tracking KV cache + GPU mode-swap state. Pattern extends to agent telemetry. |
| ☆ | Lilian Weng — [LLM Powered Autonomous Agents](https://lilianweng.github.io/posts/2023-06-23-agent/) | Already in `llm-end-to-end` § 20. Covers the planning + memory + tool-use architecture; observability implications inferred. |

### Failure recovery

Frameworks differ widely on recovery patterns. Key insight: design
the recovery first, the happy path second.

| | Item | Why |
|---|---|---|
| ★ | The "framework debate is a distraction" essay — already linked above | The recovery-logic-matters-more insight. |
| ☆ | Empirical agent-failure case studies in [Multi-Agent AI Orchestration Guide](https://www.codebridge.tech/articles/mastering-multi-agent-orchestration-coordination-is-the-new-scale-frontier) — CodeBridge | Real-world examples of coordination failures and what recovery patterns worked. |

---

## 5. Sandboxing autonomous agents — non-negotiable in 2026

Already covered in detail in [`agentic-coding.md`](agentic-coding.md)
§ 5 with the platform comparison (Modal, E2B, Blaxel, Daytona,
Northflank, NVIDIA OpenShell). **The same considerations apply for
any autonomous agent**, not just coding agents.

Quick summary applicable beyond coding:

| Threat | Required isolation |
|---|---|
| **Untrusted content injection** (the agent reads a malicious doc) | Process-level sandboxing |
| **Tool misuse** (agent uses `rm -rf` when it shouldn't) | Capability-restricted sandbox |
| **Long-running autonomous execution** (agent runs for hours unattended) | Resource quotas + audit logging |
| **Multi-tenancy** (multiple agents on one host) | microVM or hardware-level isolation |
| **Sensitive data access** (agent has database credentials) | Network egress controls + secrets vaulting |

The 2026 reality: 1 in 8 reported AI security breaches involves an
agentic system (HiddenLayer 2026 AI Threat Landscape Report).
Designing without sandboxing is no longer defensible.

---

## 6. Sandboxes — bonus picks for orchestration (not just code)

Already cited in `agentic-coding.md` § 5 for code execution. For
**general autonomous orchestration** (browser automation, OS-level
agents, multi-modal agents), the same platforms apply with different
configurations:

| Platform | Sweet spot for orchestration | Reference |
|---|---|---|
| Modal | General-purpose, GPU support, fast spin-up | [Modal docs](https://modal.com/docs) |
| E2B | Browser + computer-use agents, longer sessions | [E2B docs](https://e2b.dev/) |
| Blaxel | Multi-agent system isolation | [Blaxel](https://blaxel.ai/) |
| Daytona | Dev-environment-flavored multi-agent | [Daytona](https://www.daytona.io/) |
| Northflank | High-scale production (2M+ workloads/month) | [Northflank](https://northflank.com/) |

---

## 7. Reading order if you have a single afternoon

1. ★ Openlayer Multi-Agent Architecture Guide — pick a topology
2. ★ Presenc AI "framework debate is a distraction" — internalize the meta-insight
3. ★ Tensoria 2026 benchmark — see the framework tradeoffs quantitatively
4. ★ MCP SitePoint guide — the standard tool-use layer
5. ★ Modal sandbox comparison — pick your sandbox platform

## Reading order if you have a week

- **Day 1**: Architecture patterns (Openlayer + Augment Swarm-vs-Supervisor + decodethefuture)
- **Day 2**: ReAct + Reflexion (from `llm-end-to-end` § 20) — the foundational loops
- **Day 3**: Framework comparisons (LangChain post, Turing 6-framework, Tensoria benchmark)
- **Day 4**: MCP — the protocol that makes it all interoperable (SitePoint + Essa Mamdani guide)
- **Day 5**: Generative Agents (Park et al.) + From Plan to Action — long-horizon research
- **Day 6**: Benchmarks (decodethefuture 6 tests + BenchmarkingAgents leaderboard)
- **Day 7**: Sandboxing + production patterns (Modal sandbox comparison + the homelab's observability stack)

---

## Cross-references

- [`agentic-coding.md`](agentic-coding.md) — the **coding-specific**
  cousin of this page. Same orchestration concerns applied to code
  agents specifically.
- [`coding-models-local.md`](coding-models-local.md) — the model +
  IDE-integration layer. Read first if you're new to running local
  models for agent workloads.
- [`llm-end-to-end.md`](llm-end-to-end.md) § 20 (Tool use &
  function calling) — foundational ★ papers (ReAct, Toolformer,
  MCP). This page builds on top.
- [`a16z-ai-canon.md`](a16z-ai-canon.md) § 6.4 Agents — historical
  baseline (Auto-GPT, BabyAGI, Generative Agents, Reflexion).
- [`lilian-weng-blog.md`](lilian-weng-blog.md) — Lilian Weng's
  "LLM Powered Autonomous Agents" survey is the long-form companion
  to this page.
- [`README.md`](README.md) — section overview and the ★/☆/·
  criteria applied here.
