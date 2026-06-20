# Running your own coding models — end-to-end

> Reading list for **running an open-source coding LLM locally,
> wiring it into your IDE / terminal, and getting end-to-end
> productivity** from autocomplete through agentic refactoring.
> Keyed to the homelab's working stack (Qwen3-Coder-Next on vLLM
> coder-next at port 9000, Ollama for the wider model catalog at
> port 11434, opencode / Claude Code as the agent layer).
>
> Legend:
> - ★ = mandatory, read/watch this first
> - ☆ = strongly recommended, second pass
> - · = reference / deep dive, read when you need it

## What this page is

Two distinct things are bundled under "coding LLM":

1. **Fill-in-the-middle (FIM) autocomplete** — what fires when you
   hit Tab in VS Code. Small fast model + IDE plugin.
2. **Agentic coding** — multi-turn refactors, "fix this bug,"
   "add tests for this file." Larger reasoning-capable model +
   agent framework.

These have **different model requirements** and **different
integration shapes**. This page covers both; the homelab's actual
stack uses Qwen3-Coder-Next for both (via opencode / Claude Code)
because the GB10 has enough VRAM headroom that a separate
autocomplete model isn't required.

For **self-hosting concerns generally** (frameworks, hardware,
quantization, TCO) see [`self-hosting-llms.md`](self-hosting-llms.md).
This page assumes you've made the "yes, self-hosting makes sense"
decision and focuses on the coding-specific choices.

---

## 0. Starter pack: decide which model + which integration shape

| | Item | Why |
|---|---|---|
| ★ | [Best Open-Source LLM Models in 2026: Coding, Local, Agentic AI, Benchmarks](https://huggingface.co/blog/daya-shankar/open-source-llms) — HuggingFace blog | Most comprehensive 2026 model landscape: benchmarks (SWE-Bench, HumanEval, LiveCodeBench), license, agent capability scoring.<br>**Why ★:** primary practitioner reference; HuggingFace-hosted so the model links are direct + maintained. |
| ★ | [Best Open-Source AI Coding Agents 2026: The Complete Comparison](https://wetheflywheel.com/en/guides/open-source-ai-coding-agents-2026/) — WeTheFlywheel | The IDE / agent layer landscape: Continue (VS Code + JetBrains), Aider (terminal/git-native), opencode (terminal TUI), Cline (VS Code-native), Kilo Code.<br>**Why ★:** primary 2026 comparison of the integration layer. The model-vs-agent decisions are independent — you can mix any of these. |
| ★ | [Best Local Coding Models in 2026: Qwen3-Coder vs DeepSeek vs Codestral](https://www.promptquorum.com/power-local-llm/best-local-coding-models-2026) — Promptquorum | Direct model-vs-model comparison on the three production-defaults. Specific VRAM + benchmark numbers per model.<br>**Why ★:** primary practitioner-keyed model-choice guide. |
| ☆ | [The Best Open-Source LLMs for Agentic Coding in 2026](https://www.mindstudio.ai/blog/best-open-source-llms-agentic-coding-2026) — MindStudio | Agentic-specific (not autocomplete) lens; useful when you've already decided on agent workflows over IDE autocomplete. |

---

## 1. The coder LLM landscape (model choice)

### Production-default open-source coders, 2026

| | Model | Best for | VRAM (Q4) | SWE-Bench V | HF link |
|---|---|---|---|---|---|
| ★ | **Qwen3-Coder-Next** | Agentic + long-context (256K). Single 24GB GPU. | 18-22 GB | 58.7% | [Qwen/Qwen3-Coder-Next-FP8](https://huggingface.co/Qwen/Qwen3-Coder-Next-FP8) (currently on coder-next vLLM stack) |
| ★ | **Qwen 3.5-27B** | Single-GPU agentic. 20+ languages. | 18 GB | 49.2% | [Qwen/Qwen3.5-27B](https://huggingface.co/Qwen) |
| ★ | **Codestral 25.12** | Fast inline FIM autocomplete (95.3% FIM pass@1). | 16 GB | — | [mistralai/Codestral-25.12](https://huggingface.co/mistralai) |
| ★ | **DeepSeek V3.2** | Reasoning-heavy / algorithmic (LeetCode shape). | varies (large) | — | [deepseek-ai/DeepSeek-V3](https://huggingface.co/deepseek-ai) |
| ☆ | **DeepSeek-Coder V3 (Distilled)** | Best quality-per-GB; 12 GB VRAM. | 12 GB | 40.5% | [deepseek-ai](https://huggingface.co/deepseek-ai) |
| ☆ | **Llama 4 Scout** | Largest context (10M tokens). | larger | — | [meta-llama](https://huggingface.co/meta-llama) |
| ☆ | **Gemma 4 26B A4B** | Fastest local tokens/sec (trades some quality). | 16-20 GB | — | [google/gemma](https://huggingface.co/google) |

### Reading list

| | Item | Why |
|---|---|---|
| ★ | [Best Local LLM for Coding in 2026: Developer's Guide](https://overchat.ai/ai-hub/best-local-llm-for-coding) — Overchat AI Hub | Tier-by-VRAM model picks with specific benchmark numbers. The "what to actually pin" reference.<br>**Why ★:** primary practitioner-keyed reference; matches the homelab's pattern of "pick by hardware, then validate per workload." |
| ★ | [Best Local LLM for Coding 2026 — Ranked by GPU Tier](https://llmhardware.io/guides/best-llm-for-coding) — LLM Hardware | Companion to Overchat: same data, different framing (GPU tier → model). Pick whichever cut suits your decision shape.<br>**Why ★:** primary GPU-keyed reference; useful when hardware is fixed and you're picking the model. |
| ☆ | [Best Open Source Self-Hosted LLMs for Coding in 2026](https://pinggy.io/blog/best_open_source_self_hosted_llms_for_coding/) — Pinggy | Tour-of-options with deployment notes. |
| ☆ | [Best Open-Source LLMs for Coding (June 2026)](https://dev.to/zyvop/the-best-open-source-llms-for-coding-right-now-june-2026-n10) — DEV Community | Practitioner update; refresh point for what's changed quarter-over-quarter. |
| ☆ | [Best LLM for Coding in 2026: Ranked by Real Benchmarks](https://whatllm.org/best-llm-for-coding) — WhatLLM.org | Benchmark-first sort; useful when you want raw numbers. |
| · | [Best Open-Source & Open-Weight Coding Models (2026)](https://kilo.ai/open-source-models) — Kilo.ai | Vendor blog (Kilo.ai is one of the IDE integrations); slightly biased but the model-list reference is solid. |

---

## 2. Benchmarks — what the numbers actually mean

Before picking a model on "SWE-Bench Verified: 58%", understand what
that number tests.

| | Item | Why |
|---|---|---|
| ★ | [Understanding LLM Code Benchmarks: From HumanEval to SWE-bench](https://runloop.ai/blog/understanding-llm-code-benchmarks-from-humaneval-to-swe-bench) — Runloop | Single best primer on which benchmark measures what. HumanEval = isolated function stubs; SWE-Bench = real GitHub bugs; LiveCodeBench = contamination-free contest problems.<br>**Why ★:** primary practitioner reference for benchmark literacy; cited everywhere as the "what do these scores mean" entry point. |
| ★ | [SWE-bench Leaderboard 2026: All Model Scores, Rankings & What They Actually Mean](https://www.codeant.ai/blogs/swe-bench-scores) — CodeAnt | Current scores + how the leaderboard's evolved with SWE-Bench Pro / Verified variants.<br>**Why ★:** primary live-data reference; the leaderboard moves so the explainer-of-the-current-shape matters. |
| ☆ | [Best LLMs for Coding in 2026: SWE-bench, HumanEval breakdown](https://onyx.app/insights/best-llms-for-coding-2026) — Onyx | Side-by-side scores across the major benchmarks. Useful for picking which benchmark matters for your workload. |
| ☆ | [LongCodeBench: Evaluating Coding LLMs at 1M Context Windows](https://arxiv.org/abs/2505.07897) — arXiv 2025 | Long-context-specific eval. Relevant when your workload involves whole-repo refactors. |
| · | [SWE-Lancer: Can Frontier LLMs Earn $1 Million from Real-World Freelance Software Engineering?](https://arxiv.org/abs/2502.12115) — OpenAI / Penn 2025 | Workforce-shaped eval. Less useful for model picking, more for "what's the agent gap to real productivity." |
| · | [TREAT: A Code LLMs Trustworthiness / Reliability Evaluation Framework](https://arxiv.org/abs/2510.17163) — arXiv | When "does it pass the test" isn't enough and you want trustworthiness measures. |

### Frontier comparison (cloud models, for context)

Open coders haven't caught Claude Opus 4.6 yet, but the gap is
closing fast. As of 2026:

- **Claude Opus 4.6**: 80.8% SWE-Bench Verified, 95.0% HumanEval,
  76.0% LiveCodeBench
- **Qwen3-Coder-Next** (best open): 58.7% SWE-Bench Verified
- **Gap**: ~22 pts on SWE-Bench Verified

The homelab's pattern (Qwen3-Coder local + Claude cloud fallback for
the hardest cases via guardrails) is the practical answer to that
gap.

---

## 3. Fill-in-the-middle (FIM) — the autocomplete path

When you hit Tab in VS Code, the model sees code before AND after
the cursor and fills the gap. This is a **different request shape**
than chat — different training data, different inference pattern,
different model picks.

| | Item | Why |
|---|---|---|
| ★ | Codestral 25.12 — [Mistral release notes + HF page](https://huggingface.co/mistralai) | Codestral was built specifically for FIM. 95.3% FIM pass@1 (Codestral 25.01) beats DeepSeek-Coder V2 (83.5%) and Llama 3 70B (81.7%).<br>**Why ★:** primary source for the specialized FIM model. If your use case is pure inline autocomplete, this is the pick. |
| ★ | [Continue.dev — Autocomplete + Chat split](https://docs.continue.dev/) | Vendor doc explaining the "small fast FIM model for autocomplete + larger model for chat" split. Cleanest framing of the architectural choice.<br>**Why ★:** primary vendor doc; the framework that everybody actually uses for this split. |
| ☆ | [DeepSeek-Coder + FIM training mode](https://github.com/deepseek-ai/DeepSeek-Coder) — DeepSeek docs | Alternative to Codestral if you're staying in the DeepSeek family. |
| ☆ | [StarCoder2 + FIM](https://github.com/bigcode-project/starcoder2) — BigCode | The other major FIM-capable open model. Good fallback. |
| · | [The original FIM paper — "Efficient Training of Language Models to Fill in the Middle"](https://arxiv.org/abs/2207.14255) — Bavarian et al. 2022 | Primary source for the FIM training paradigm. Necessary if you want to understand WHY autocomplete is a different problem from chat. |

### Practical setup (FIM-specific)

| | Pattern | Models | IDE |
|---|---|---|---|
| ★ | **Codestral autocomplete + Qwen 3.5-27B chat** | Codestral 22B FIM + Qwen 3.5 chat | Continue (VS Code + JetBrains) |
| ☆ | **Qwen3-Coder for both** | Single model, simpler, costs more VRAM at idle | Continue, Aider, opencode |
| ☆ | **DeepSeek-Coder + Continue** | If you're in the DeepSeek family already | Continue |

---

## 4. Agentic coding — multi-turn refactoring shape

When you say "fix this bug and add tests," that's not autocomplete —
it's a multi-turn agent with tool use (read file, write file, run
tests, inspect output). Different requirements.

### The agent layer in 2026

| | Tool | Best for | License | GitHub stars |
|---|---|---|---|---|
| ★ | **Continue** | IDE-native (VS Code + JetBrains) with Agent/Chat/Edit/Autocomplete modes. Best when you want one tool that does all four. | Apache 2.0 | 26K+ |
| ★ | **Aider** | Git-native terminal workflow. Auto-commits per change, deep git integration. Best when you live in the terminal + git. | Apache 2.0 | 40K+ |
| ★ | **OpenCode** | Terminal TUI with IDE-level intelligence (LSP, multi-session). 75+ LLM providers. Local-first, privacy-focused. Fastest community growth. | MIT | 100K+ |
| ★ | **Claude Code** | Anthropic's official CLI. Cloud-bound (Claude API). Excellent code-aware agent. Used heavily in the homelab. | Proprietary | (vendor) |
| ☆ | **Cline** (formerly Claude Dev) | VS Code-native agentic. Vibrant ecosystem of derivatives (Kilo Code, Roo Code, PearAI). | Apache 2.0 | 50K+ |
| ☆ | **Kilo Code** | Cline derivative with enhanced features (model routing, custom modes). | Apache 2.0 | growing |
| · | **Zed AI** | Built into the Zed editor; different paradigm but worth knowing about. | (mixed) | (editor) |

### Reading list

| | Item | Why |
|---|---|---|
| ★ | [Best Open-Source AI Coding Agents 2026: The Complete Comparison](https://wetheflywheel.com/en/guides/open-source-ai-coding-agents-2026/) — WeTheFlywheel | The single best landscape comparison. Covers all of the above with use-case framing.<br>**Why ★:** primary practitioner reference; updated for 2026 with concrete tradeoff guidance. |
| ★ | [Aider vs OpenCode: Best Open-Source AI Coding CLI in 2026](https://www.nxcode.io/resources/news/aider-vs-opencode-ai-coding-cli-2026) — NxCode | Head-to-head on the two best terminal-native options. Detailed feature comparison + workflow examples.<br>**Why ★:** primary source for the "I'm a terminal person, which one?" decision. The homelab uses both (opencode for vLLM coder-next, Claude Code for cloud). |
| ★ | [11 AI Coding Agents Ranked (2026): Terminal-Bench Scores, Price, License](https://www.morphllm.com/ai-coding-agent) — Morph | Quantitative ranking on Terminal-Bench. Adds objective scoring to the qualitative comparisons.<br>**Why ★:** primary empirical source on agent capability — most agent comparisons are vibes-based; this one has scores. |
| ☆ | [Best Cline Alternatives 2026: 10 Open-Source VS Code AI Coding Agents](https://baeseokjae.github.io/posts/cline-alternatives-2026/) — RockB | Deep dive on the VS Code-native ecosystem. Useful if Cline-shape is your starting point. |
| ☆ | [Best Local-First AI Coding Tools 2026: 14 Compared](https://nimbalyst.com/blog/best-local-first-ai-coding-tools-2026/) — Nimbalyst | Local-first filter; excludes cloud-bound options like Cursor. Matches the homelab's "self-host first" philosophy. |
| ☆ | [12 Best Open-Source AI Coding Tools (2026)](https://frontman.sh/blog/best-open-source-ai-coding-tools-2026/) — Frontman | Tour-of-options. |
| · | [9 Best Open Source AI Coding Assistants in 2026](https://www.opensourcealternatives.to/blog/best-open-source-ai-coding-assistants) — Open Source Alternatives | Open-source-purity filter. Excludes anything with proprietary components. |

### Foundational research papers (where these agents came from)

Already covered in [`llm-end-to-end.md`](llm-end-to-end.md) § 20:

- ★ **ReAct** (Yao et al. 2022) — the Thought-Action-Observation loop
- ★ **Toolformer** (Schick et al. 2023) — self-supervised tool-use training
- ☆ **Model Context Protocol (MCP)** — cross-vendor tool-server protocol
  used by Claude Code, opencode, and others

---

## 5. The IDE integration layer — how the model actually plugs in

### Continue (VS Code + JetBrains)

The IDE-extension path. Same plugin for chat, autocomplete, edit,
agent — provider selection per use.

| | Item | Why |
|---|---|---|
| ★ | [Continue.dev — official docs](https://docs.continue.dev/) | Vendor primary source. Setup, model providers, configuration.<br>**Why ★:** primary vendor doc; the single official reference. |
| ★ | [Continue + Ollama setup walkthrough](https://docs.continue.dev/customize/model-providers/ollama) | Concrete walkthrough for the local-model path. Five-minute setup. |
| ☆ | Continue's [`config.yaml` reference](https://docs.continue.dev/customize/yaml-reference) | When defaults don't work. |
| ☆ | [Local LLM for Coding 2026: The Free, Private Alternative to ChatGPT](https://www.hakunamatatatech.com/our-resources/blog/local-llm-for-coding) — Hakunamatata | Full e2e setup: install Continue → set provider to Ollama → select model. |

### Aider (terminal + git)

| | Item | Why |
|---|---|---|
| ★ | [Aider — official docs](https://aider.chat/) | Vendor primary source. Aider's value prop is the git-native commit-per-change pattern. |
| ★ | [Aider + Ollama walkthrough](https://aider.chat/docs/llms/ollama.html) | Concrete setup for the local-model path. |

### opencode (terminal TUI)

| | Item | Why |
|---|---|---|
| ★ | [OpenCode — GitHub repo + docs](https://github.com/opencode-ai/opencode) | Vendor primary source. Go-based TUI; 75+ LLM providers; local-first.<br>**Why ★:** primary repo; this is what the homelab actually runs against the coder-next vLLM. |
| ★ | [OpenCode + local vLLM setup](https://github.com/opencode-ai/opencode) — Provider configuration for OpenAI-compatible endpoints | Critical: opencode talks to anything OpenAI-API-compatible, which is what vLLM serves. The homelab's coder-next stack on port 9000 plugs straight in. |

### Cline + derivatives (VS Code-native agentic)

| | Item | Why |
|---|---|---|
| ☆ | [Cline — GitHub](https://github.com/cline/cline) | Primary repo for the ecosystem progenitor. |
| ☆ | [Kilo Code — GitHub](https://github.com/Kilo-Org/kilocode) | Most popular Cline derivative. Adds model routing + custom modes. |

### Claude Code (cloud-bound, mentioned for context)

The homelab uses Claude Code heavily for the cloud-routed coding
workload. Not local, not self-hosted, but worth knowing about as the
benchmark for "what does a really good code agent feel like":

- [Claude Code — Anthropic docs](https://docs.anthropic.com/en/docs/claude-code)
- Combined with the local opencode+coder-next pattern, you get
  "Claude when it matters, local when it doesn't" — same hybrid
  shape as [`self-hosting-llms.md`](self-hosting-llms.md) § 4.

---

## 6. End-to-end recipes for the homelab pattern

### Recipe 1 — Pure local (terminal-native, vLLM-served Qwen3-Coder-Next)

What the homelab actually runs:

```bash
# On the DGX:
# 1. coder-next vLLM (homelab repo)
~/bin/gpu-mode-swap.sh code

# 2. Verify the OpenAI-compatible endpoint
curl http://<dgx-tailnet>:9000/v1/models \
  -H "Authorization: Bearer buddy-is-the-king"

# 3. On your laptop, configure opencode/Aider to use the vLLM endpoint
#    as an OpenAI-compatible provider:
#    base_url:  http://<dgx-tailnet>:9000/v1
#    api_key:   buddy-is-the-king
#    model:     coder-next
```

References:
- [`infra/vllm/coder-next/`](https://github.com/chipi/agentic-ai-homelab/tree/main/infra/vllm/coder-next) — working compose
- [`infra/dgx/bin/gpu-mode-swap.sh`](https://github.com/chipi/agentic-ai-homelab/blob/main/infra/dgx/bin/gpu-mode-swap.sh) — the GPU-ownership contract

### Recipe 2 — Pure local (IDE-native, Ollama-served + Continue)

The lighter-weight path:

```bash
# 1. On your dev machine (Mac, Linux, Windows):
ollama pull qwen3-coder:30b
ollama pull codestral:22b  # FIM autocomplete

# 2. Install Continue extension in VS Code or JetBrains

# 3. Configure Continue's config.yaml:
#    - models:
#        chat: qwen3-coder:30b (via Ollama provider)
#        autocomplete: codestral:22b (via Ollama provider)
```

References:
- [Continue.dev + Ollama walkthrough](https://docs.continue.dev/customize/model-providers/ollama)

### Recipe 3 — Hybrid (local + cloud)

Local for routine, cloud for hard problems. This is the actually
pragmatic pattern.

```
[ opencode CLI ] ─┬→ http://dgx:9000/v1/chat/completions   (local Qwen3-Coder-Next via vLLM)
                  ├→ Claude Code              (cloud Claude 4.7 for hard cases)
                  └→ guardrails / routing decision lives in the agent
```

References:
- The homelab's [`docs/recipes/consuming-homelab-services.md`](https://github.com/chipi/agentic-ai-homelab/blob/main/docs/recipes/consuming-homelab-services.md) — `${VAR}` substitution convention so the same client config can switch between local + cloud
- `podcast_scraper#996`-style consumer-side guardrails to detect when local fails and route to cloud

---

## 7. Specific topics worth their own deep dive

### Code review and PR generation

| | Item |
|---|---|
| ☆ | [SWE-Bench Pro — real PR-shape eval](https://www.codeant.ai/blogs/swe-bench-scores) — newer benchmark targeting real PR-style work, not just bug fixing |
| ☆ | [CursorCore: Assist Programming through Aligning Anything](https://arxiv.org/abs/2410.07002) — methodology for code-context-aligned models |

### Code completion training / FIM specifics

| | Item |
|---|---|
| · | [Efficient Training of Language Models to Fill in the Middle](https://arxiv.org/abs/2207.14255) — Bavarian et al. 2022 — the foundational paper |
| · | [CodeEvo: Interaction-Driven Synthesis of Code-centric Data](https://arxiv.org/abs/2507.22080) — synthetic data for training coders |

### Multi-turn coding agents under load

| | Item |
|---|---|
| · | [Training Versatile Coding Agents in Synthetic Environments](https://arxiv.org/abs/2512.12216) — recent (2025) research on training coder-agents in sandbox environments |

---

## Reading order if you have a single afternoon

For "I want a local coder agent today":

1. ★ WeTheFlywheel agent comparison — pick your integration layer
2. ★ Promptquorum model comparison — pick your model
3. ★ Continue.dev + Ollama walkthrough — execute the simpler recipe
4. Optionally: read the homelab's `coder-next` compose for a more
   serious deployment shape

## Reading order if you have a week

- **Day 1**: Agent landscape (WeTheFlywheel) + Model landscape (Promptquorum + Overchat)
- **Day 2**: Benchmarks (Runloop + SWE-Bench leaderboard) — develop benchmark literacy
- **Day 3**: Continue setup + Aider setup + opencode setup — try each, decide preference
- **Day 4**: FIM specifically (Codestral release notes + Bavarian 2022 paper)
- **Day 5**: ReAct + Toolformer (from [`llm-end-to-end.md`](llm-end-to-end.md) § 20) — agent design foundations
- **Day 6**: The homelab's `infra/vllm/coder-next/` + `gpu-mode-swap.sh` working stack
- **Day 7**: Hybrid routing + guardrails patterns; integrate cloud fallback

---

## Cross-references

- [`self-hosting-llms.md`](self-hosting-llms.md) — the **non-coding-specific
  cousin** of this page. Same self-hosting concerns (framework
  choice, hardware, quant) without the IDE / agent layer.
- [`llm-end-to-end.md`](llm-end-to-end.md) §§ 1 (Tokenization),
  4 (Modern decoder design), 6 (MoE — relevant to Qwen3-Coder),
  11 (vLLM), 12 (Ollama), 13 (Sampling), 14 (Constrained decoding),
  15 (Quantization), 20 (Tool use) — all the foundations this page
  builds on.
- [`a16z-ai-canon.md`](a16z-ai-canon.md) § 6.5 Code Generation —
  historical baseline (Codex, AlphaCode, CodeGen) that the modern
  coders descend from.
- [`README.md`](README.md) — section overview and the ★/☆/· criteria
  applied here.
