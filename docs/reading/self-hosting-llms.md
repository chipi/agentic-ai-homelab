# Self-hosting LLMs — end-to-end

> Reading list for **deciding whether to self-host, choosing the
> serving stack, sizing hardware, picking a quantization format, and
> running it in production**. Keyed to the homelab's working stack
> (vLLM + Ollama on GB10 with NVFP4 / FP8) as the reference
> implementation.
>
> Legend (same as [`llm-end-to-end.md`](llm-end-to-end.md)):
> - ★ = mandatory, read/watch this first
> - ☆ = strongly recommended, second pass
> - · = reference / deep dive, read when you need it

## What this page is

The homelab runs two self-hosted vLLM stacks (coder-next on `:9000`,
autoresearch on `:8003`) coordinated by `gpu-mode-swap.sh`, plus
Ollama on `:11434` for the model catalog. This page is the
**reading list behind that stack** — the papers, framework docs, and
practitioner guides someone would need to read to build something
equivalent.

For the **practitioner-keyed transformer/serving foundations**, see
[`llm-end-to-end.md`](llm-end-to-end.md) § 11 (vLLM), § 12 (Ollama
internals), and § 15 (Quantization). That page covers the
*technical foundations*; this page covers the **decisions** (is
self-hosting right for you, which framework, which hardware, which
quant) plus **end-to-end deployment**.

---

## 0. Decide if self-hosting is right for you

Before any technical reading, the core question is **economic**:
break-even thresholds determine when self-hosting pays back vs.
cloud APIs.

| | Item | Why |
|---|---|---|
| ★ | [Local LLMs vs Cloud APIs: 2026 TCO Analysis](https://www.sitepoint.com/local-llms-vs-cloud-api-cost-analysis-2026/) — SitePoint | Single best break-even framing: 500K tok/day for 7B, 2M tok/day for 70B. Clear cost model.<br>**Why ★:** primary practitioner reference on the cost decision; the single most-cited "should I self-host" data point. |
| ★ | [Self-Hosted LLM vs API: Real Cost Breakdown 2026](https://devtk.ai/en/blog/self-hosting-llm-vs-api-cost-2026/) — DevTk | Companion to SitePoint: hidden costs (DevOps, electricity, downtime, opportunity). Self-hosting costs 3-5× the raw GPU price.<br>**Why ★:** balances the optimistic break-even framing with realistic operational overhead; both should be read together. |
| ☆ | [LLM Inference On-Premise vs GPU Cloud: 2026 Cost & Break-Even Analysis](https://www.spheron.network/blog/llm-inference-on-premise-vs-cloud/) — Spheron | Most rigorous GPU-utilization-based analysis: at <70% util cloud wins; at 80%+ on-prem wins over 3 years. |
| ☆ | [On-Premise vs Cloud: Generative AI Total Cost of Ownership (2026 Edition)](https://lenovopress.lenovo.com/lp2368-on-premise-vs-cloud-generative-ai-total-cost-of-ownership-2026-edition) — Lenovo Press | Enterprise-angle framing; useful when you're explaining the decision to leadership. |
| · | [Self-Hosted LLM Guide: Costs, Architecture & Breakeven Point](https://alpacked.io/blog/self-hosted-llm-guide/) — Alpacked | Tour-of-options reference; less specific than the SitePoint/DevTk pair. |

**The takeaway shaping the homelab's choice:** at the homelab's
workload (sweeps + IDE coding + autoresearch), the break-even is
clearly met, and the GB10 unified-memory architecture removes the
"you don't have enough VRAM" friction. Read all five if you're
deciding from scratch; read the first two if you've already decided.

---

## 1. Hardware: GPU, Apple Silicon, or mini-PC

The single biggest constraint is VRAM. Pick a tier first, then a
specific chip.

| | Item | Why |
|---|---|---|
| ★ | [Local LLM Hardware Requirements 2026: VRAM Guide (3 Tiers)](https://www.kunalganglani.com/blog/local-llm-hardware-requirements-2026) — Kunal Ganglani | The clearest per-tier breakdown: 8 GB → 7B Q4, 16-24 GB → 14-32B Q4, 48-96 GB → 70B Q4/FP8. Realistic, tested.<br>**Why ★:** primary practitioner reference; the single best "what GPU do I need" link to send a colleague. |
| ★ | [I Tested 7 GPUs Running Local LLMs: Exact VRAM Numbers (Real Hardware)](https://mustafa.net/llm-vram-requirements-2026/) — Mustafa.net | Actual benchmarks of consumer GPUs (3090 / 4090 / 5090 / etc.) running real models. Cuts through marketing.<br>**Why ★:** primary empirical source — no extrapolation from spec sheets, just measured VRAM with the model loaded. |
| ☆ | [VRAM Requirements for Local LLMs: The Complete Guide](https://llmconfigurator.com/en/guides/vram-requirements-guide/) — LLM Configurator | Lookup tool for matching model+context to VRAM. |
| ☆ | [Local LLM Hardware in 2026: GPU vs Mini PC vs Mac](https://www.promptquorum.com/local-llms/local-llm-hardware-guide-2026) — Promptquorum | Side-by-side of the three viable architectures (discrete GPU, mini-PC with iGPU, Apple Silicon unified memory). |
| · | [Local LLM Hardware Requirements in 2026](https://overchat.ai/ai-hub/llm-hardware-requirements) — Overchat AI Hub | Tier breakdown with model-specific recommendations. Less original than Kunal's guide but more comprehensive table. |

**Apple Silicon note:** if you're not buying a dedicated GPU, an
**M5 Max with 64 GB unified memory** runs models that would otherwise
need an H100. Unified memory is the same architecture as GB10
(homelab's actual stack) — the framework support landscape is
narrower (vLLM has Apple Silicon as a plugin per v0.21.0, not
core), but for single-user inference, llama.cpp + Ollama work
natively and well.

**Consumer-GPU sweet spot:** RTX 4090 (24 GB) → RTX 5090 (variable
VRAM) remain the price-performance leaders for discrete-VRAM
self-hosting at single-user scale.

---

## 2. Quantization formats — which one + when

The serving framework's quant support determines what models you can
run. The 2026 production defaults converged.

| | Item | Why |
|---|---|---|
| ★ | See [`llm-end-to-end.md`](llm-end-to-end.md) § 15 — Quantization | The homelab's own reading list already covers GPTQ, AWQ, FP8, NVFP4, and the canonical primary papers (Frantar 2022 GPTQ, Lin 2023 AWQ, Micikevicius 2022 FP8). Read those before the practitioner blogs below. |
| ★ | [llama.cpp K-quants original PR thread (#1684)](https://github.com/ggerganov/llama.cpp/pull/1684) | The primary source for Q4_K_M / Q5_K_M etc. — the quant suffix you'll meet every time you load an Ollama model.<br>**Why ★:** primary source for GGUF's per-tensor quantization scheme; required reading for understanding `ollama show <model>` output. |
| ☆ | [Maxime Labonne — "Quantize Llama models with GGUF"](https://mlabonne.github.io/blog/posts/Quantize_Llama_2_models_using_ggml.html) | Practical: which K-quant gives you which quality/size trade. |
| ☆ | [A Visual Guide to Quantization](https://newsletter.maartengrootendorst.com/p/a-visual-guide-to-quantization) — Maarten Grootendorst | Mental-model intro. Pair with the GPTQ/AWQ papers. |
| ☆ | [NVIDIA Model Optimizer — NVFP4 Quantization](https://nvidia.github.io/TensorRT-Model-Optimizer/) | The homelab's autoresearch stack runs NVFP4. Vendor docs are the primary source. |

**The takeaways shaping the homelab's choices:**

- **For vLLM-served models**: AWQ has become the default 4-bit
  format (Qwen, Llama variants ship AWQ as primary). FP8 is the new
  production-default precision for Hopper / Blackwell hardware.
  NVFP4 is the new Blackwell-class option for further compression.
- **For Ollama-served models**: GGUF + K-quants (Q4_K_M, Q5_K_M).
  Different code path entirely; can't mix-and-match with vLLM
  formats.

Both paths are documented end-to-end in the homelab's existing
[`autoresearch/KV_CACHE_SIZING.md`](https://github.com/chipi/agentic-ai-homelab/blob/main/infra/vllm/autoresearch/KV_CACHE_SIZING.md)
and the GB10-specific decisions in
[`autoresearch/decisions/`](https://github.com/chipi/agentic-ai-homelab/tree/main/infra/vllm/autoresearch/decisions).

---

## 3. Serving frameworks — vLLM vs Ollama vs SGLang vs llama.cpp

The 2026 landscape converged on three production-grade frameworks
plus llama.cpp as the underlying engine for the consumer-focused
ones. Choose by **workload shape**, not by marketing.

### Decision matrix (at a glance)

| Framework | Best for | NOT for | Underlying engine |
|---|---|---|---|
| **vLLM** | Production multi-tenant serving; concurrent batched workloads; OpenAI-compatible API | Single-user development on tiny VRAM | Native (PagedAttention) |
| **SGLang** | Structured-output workloads (JSON schemas, tool-use); agent loops; lowest single-user latency | Pure throughput maximization in some cases | Native (RadixAttention) |
| **Ollama** | Development; consumer hardware; model catalog management; single-user IDE workflows | Production high-concurrency serving | llama.cpp |
| **llama.cpp** | Apple Silicon native; embedded / edge; one-off CLI experiments | Multi-user production | Native (CPU+GPU) |

### Reading list

| | Item | Why |
|---|---|---|
| ★ | See [`llm-end-to-end.md`](llm-end-to-end.md) § 11 (vLLM) + § 12 (Ollama internals) | The homelab's existing reading list covers the foundational papers (PagedAttention, FlashAttention) + the llama.cpp wiki. Read those first; the framework comparisons below assume that foundation. |
| ★ | [llama.cpp vs Ollama vs vLLM: One User vs Many (2026)](https://insiderllm.com/guides/llamacpp-vs-ollama-vs-vllm/) — InsiderLLM | The cleanest framing of the workload-shape question. "One user vs many" is exactly the choice that determines your stack.<br>**Why ★:** primary practitioner reference; explicit recommendations (Ollama for dev, vLLM for production) that match what production teams actually do. |
| ★ | [vLLM vs Ollama: Performance Benchmark 2026](https://www.sitepoint.com/ollama-vs-vllm-performance-benchmark-2026/) — SitePoint | Quantified: vLLM beats Ollama 16-29× in aggregate throughput at concurrency >10. Ollama hits request timeouts at 20 concurrent.<br>**Why ★:** primary empirical data point on the throughput gap; explains *why* the "Ollama for dev, vLLM for production" pattern is actually correct, not just folklore. |
| ★ | [vLLM vs Ollama vs SGLang vs TensorRT-LLM Serving 2026](https://theaiengineer.substack.com/p/vllm-vs-ollama-vs-sglang-vs-tensorrt) — The AI Engineer | Adds SGLang and TensorRT-LLM to the comparison. SGLang at single-user is 6.6× faster than vLLM for structured workloads.<br>**Why ★:** primary source for the SGLang-vs-vLLM decision, which is the actual hard call in 2026 (Ollama vs vLLM is easy; vLLM vs SGLang depends on your workload). |
| ☆ | [Benchmarking SGLang, vLLM, and Ollama across Ampere and Hopper GPU](https://medium.com/@me.shivansh007/benchmarking-sglang-vllm-and-ollama-0179e3a5cbaa) — Shivansh Singh, Medium | Adds hardware-tier breakdown; confirms SGLang's structured-output lead persists across GPU generations. |
| ☆ | [vLLM vs llama.cpp vs Ollama: Benchmarks & Latency](https://www.quantizelab.dev/articles/vllm-vs-llama-cpp-vs-ollama-benchmark-guide) — QuantizeLab | Throughput vs first-token-latency tradeoffs across all three. Useful when latency matters more than throughput. |
| ☆ | [vLLM vs Ollama vs llama.cpp vs SGLang 2026](https://vrlatech.com/llm-inference-engine-comparison-2026/) — VRLA Tech | Engineering-focused breakdown including device support, quantization compatibility, deployment patterns. |
| · | [SGLang paper — Efficient Programming and Execution for LLMs](https://arxiv.org/abs/2312.07104) — Zheng et al. 2023 | Primary source for SGLang's RadixAttention and the structured-output execution model. |

### Architectural intuition you actually need

- **vLLM's edge**: PagedAttention + continuous batching. Hides the
  KV cache fragmentation problem; high GPU utilization under
  concurrent load.
- **SGLang's edge**: RadixAttention shares KV cache across requests
  with common prefixes. Massive speedup for agent workloads where
  many requests share a long system prompt. Also: native FSM-based
  constrained-decoding (XGrammar integration) is faster than vLLM's
  for structured output.
- **Ollama's tradeoffs**: fixed-slot parallelism (each parallel slot
  processes one request start-to-finish). Simpler, but no
  iteration-level scheduling means concurrent requests are bound by
  the slot count, not the GPU. At single-user load this is fine; at
  >5 concurrent it starts queueing.

---

## 4. End-to-end deployment patterns

### Single-user developer workflow

**Stack:** Ollama (port 11434) + IDE integration (Continue / Aider /
opencode) + a coder model (Qwen3-Coder, Codestral). See
[`coding-models-local.md`](coding-models-local.md) for the IDE
integrations specifically.

| | Item | Why |
|---|---|---|
| ★ | [Ollama Modelfile reference](https://github.com/ollama/ollama/blob/main/docs/modelfile.md) | When you need to customize a model's template / parameters. |
| ★ | [Ollama install + getting started](https://ollama.com/) | Vendor primary source. |
| ☆ | [Hakunamatata — Local LLM for Coding 2026: The Free, Private Alternative](https://www.hakunamatatatech.com/our-resources/blog/local-llm-for-coding) | E2E walkthrough for the dev-laptop case. |

### Production multi-tenant serving

**Stack:** vLLM or SGLang behind an OpenAI-compatible gateway,
typically with a routing layer (LiteLLM, OpenRouter-style) in front.

| | Item | Why |
|---|---|---|
| ★ | [Self-Hosting Open-Weight LLMs: 2026 Decision Guide](https://www.digitalapplied.com/blog/self-hosting-open-weight-llms-2026-deployment-decision-guide) — Digital Applied | The most thorough 2026 production deployment guide. Covers infra, monitoring, scaling.<br>**Why ★:** primary 2026 practitioner reference; covers the questions the smaller blogs don't (capacity planning, observability, model lifecycle). |
| ★ | [Self-Hosted LLM Guide: Setup, Tools & Cost Comparison (2026)](https://dev.to/jaipalsingh/self-hosted-llm-guide-setup-tools-cost-comparison-2026-3m34) — DEV Community | Practical setup with cost tracking baked in. Pairs with the Decision Guide above. |
| ★ | The homelab's own [`infra/vllm/autoresearch/`](https://github.com/chipi/agentic-ai-homelab/tree/main/infra/vllm/autoresearch) + [`infra/vllm/coder-next/`](https://github.com/chipi/agentic-ai-homelab/tree/main/infra/vllm/coder-next) | Working production composes with `.env` discipline, healthchecks, decisions/ records, KV cache sizing methodology. Concrete reference implementation.<br>**Why ★:** *the* primary source — you can clone, customize, deploy. |
| ☆ | [Self-Hosting LLMs in 2026: The Complete Guide](https://codersera.com/blog/self-hosting-llms-complete-guide-2026/) — Codersera | Tour-of-options reference covering hardware → model → quant → framework. |
| ☆ | [Self-Hosted LLM: Run, Train & Deploy (2026)](https://solguruz.com/blog/how-to-run-llm-locally/) — SolGuruz | Less original but complete walkthrough; useful as a sanity-check second source. |

### Hybrid (cloud + local) — the actually-pragmatic pattern

Most teams that "self-host" actually run a **hybrid**: high-volume,
sensitive, or routine traffic goes to the local model; complex
reasoning or edge cases go to a cloud API. Per the cost research
above, this pattern saves 40-70% vs. fully API-dependent stacks
while keeping cloud quality available when needed.

The homelab pattern (autoresearch local + cloud fallback per
`podcast_scraper#996` guardrails) is exactly this shape.

| | Item | Why |
|---|---|---|
| ★ | [`podcast_scraper#996`](https://github.com/chipi/podcast_scraper) — guardrails routing pattern | The homelab's working example of consumer-side guardrails routing failures from local → cloud fallback. Concrete recipe.<br>**Why ★:** the primary working reference for the hybrid pattern at the homelab's actual scale; everything else is theory. |

---

## 5. Production concerns nobody mentions until production hurts

Once you're running, the operational reality includes things the
"how to self-host" guides skip.

| | Item | Why |
|---|---|---|
| ★ | Lilian Weng — [Large Transformer Model Inference Optimization](https://lilianweng.github.io/posts/2023-01-10-inference-optimization/) | Production-optimization survey (already in [`llm-end-to-end.md`](llm-end-to-end.md) § 11). Quantization, distillation, MoE serving, spec-dec — read this for the "why is my flag doing what it's doing" understanding. |
| ★ | The homelab's [observability stack docs](https://github.com/chipi/agentic-ai-homelab/tree/main/infra/observability) | Grafana Alloy → Cloud, scraping vLLM `/metrics` at port 8003, KV cache usage tracking, GPU mode-swap state. Concrete monitoring recipe.<br>**Why ★:** working example of the observability gap most "self-host" guides skip. |
| ☆ | [Self-Hosted LLM Costs 2026 — Pricing Comparison](https://www.sitepoint.com/self-hosted-llm-costs-2026/) — SitePoint | Calibrates the ongoing costs (electricity, depreciation, ops time) against your initial estimate. |
| ☆ | The homelab's [`autoresearch/decisions/`](https://github.com/chipi/agentic-ai-homelab/tree/main/infra/vllm/autoresearch/decisions) durable-records pattern | When-and-why a workload-driven decision was made. Pattern is more important than the specific entries. |

---

## 6. Reading order if you have a single afternoon

For "should I and how do I self-host":

1. ★ SitePoint TCO analysis — break-even reality check
2. ★ Kunal Ganglani's hardware tiers — match VRAM to your model
3. ★ InsiderLLM "One user vs many" — pick your framework class
4. ★ vLLM vs Ollama benchmark — see the actual concurrency numbers
5. Skim the homelab's [`infra/vllm/autoresearch/README.md`](https://github.com/chipi/agentic-ai-homelab/blob/main/infra/vllm/autoresearch/README.md) — a working concrete example

After that, depth on specifics by topic.

## Reading order if you have a week

- **Day 1**: TCO + hardware tiers (decide if + which GPU)
- **Day 2**: vLLM PagedAttention + FlashAttention papers (from [`llm-end-to-end.md`](llm-end-to-end.md) § 11)
- **Day 3**: SGLang paper + InsiderLLM framework comparison
- **Day 4**: Quantization (GPTQ + AWQ from `llm-end-to-end` § 15) + Ollama internals (`llm-end-to-end` § 12)
- **Day 5**: 2026 deployment decision guide (Digital Applied) + the homelab's `infra/vllm/` stack
- **Day 6**: Lilian Weng inference optimization + observability patterns
- **Day 7**: Hybrid cloud-local routing patterns + `podcast_scraper#996` guardrails

---

## Cross-references

- [`llm-end-to-end.md`](llm-end-to-end.md) §§ 11, 12, 15, 16, 17
  — the **technical foundations** behind the decisions this page
  covers.
- [`coding-models-local.md`](coding-models-local.md) — the
  coding-specific cousin of this page. Same self-hosting concerns,
  IDE-integration focus.
- [`a16z-ai-canon.md`](a16z-ai-canon.md) § Tech Deep Dive + § Practical
  Guides — older but still-relevant foundational reading for
  understanding the stack.
- [`README.md`](README.md) — section overview and the ★/☆/· criteria
  applied here.
