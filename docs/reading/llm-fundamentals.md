# LLM Fundamentals — Mandatory Reading List

> Living doc, built up alongside a teaching arc on LLMs / vLLM / Ollama
> for the homelab. Each entry is tagged with what conversation topic it
> backs — section titles call out specific homelab connections
> ("relevant to your `Qwen3-30B-A3B-Instruct-2507` serve", "relevant to
> your LanceDB stack").
>
> Legend:
> - ★ = mandatory, read/watch this first
> - ☆ = strongly recommended, second pass
> - · = reference / deep dive, read when you need it
>
> ★ criteria: an item earns ★ only if it is **(1) a primary source or
> foundational explainer**, **(2) short enough to finish**, **(3) self-contained
> (no prereqs)**, **(4) still correct / not superseded in its core claims**, and
> **(5) self-evidently load-bearing — everyone downstream cites or references
> it**. Items failing any one of the five drop to ☆ or ·.
>
> Format per item: `tag` — **title** — author/source — practical why.<br>
> Each ★ item also carries a `**Why ★:**` line explaining which of the five
> criteria it satisfies. A `Why ☆ not ★` line is used when an item *looks
> like* a ★ but is intentionally downgraded for a workload-relative or
> scoping reason.

---

## 0. The absolute starter pack (read these even if you read nothing else)

| | Item | Why |
|---|---|---|
| ★ | **The Illustrated Transformer** — Jay Alammar (jalammar.github.io/illustrated-transformer) | The clearest visual explanation of attention. Most ML engineers learned the transformer from this post.<br>**Why ★:** foundational explainer; ~30 min read; self-contained; the visual mental model has not been superseded; cited as the canonical intro everywhere. |
| ★ | **Let's build GPT: from scratch, in code, spelled out.** — Andrej Karpathy (YouTube, "Neural Networks: Zero to Hero" series) | 2 hours; builds a tiny transformer from nothing. After this, attention/MLP/residual/layernorm stop being mysterious.<br>**Why ★:** primary instructor (the field's most respected teacher); finite (2 hrs); self-contained — starts from a character dataset; still current; recommended by literally everyone entering the field. |
| ★ | **Attention Is All You Need** — Vaswani et al. 2017 — arxiv.org/abs/1706.03762 | The transformer paper. Short, dense, foundational. Read after Karpathy's video so it actually makes sense.<br>**Why ★:** primary source, not a summary; 8 pages; self-contained (builds from seq2seq); core mechanism (Q/K/V, multi-head, residual+LN) is exactly what every modern LLM still uses; cited by ~everything. |
| ★ | **Intro to Large Language Models** — Andrej Karpathy (YouTube, ~1hr talk) | Single best plain-English overview of what an LLM is, how it's trained, and what it can do. Send this to non-ML colleagues.<br>**Why ★:** foundational orientation; 1 hour; zero prereqs; nothing since has displaced it as the canonical "explain LLMs to me" link. |

---

## 1. Decoder-only transformer (Part A of our walkthrough)

| | Item | Why |
|---|---|---|
| ★ | **The Annotated Transformer** — Sasha Rush, Harvard NLP (nlp.seas.harvard.edu/annotated-transformer) | Same paper as above, but interleaved with runnable PyTorch. Read alongside the Vaswani paper.<br>**Why ★:** primary-source-adjacent — quotes the paper line by line with code; finite (single page); self-contained; not superseded — still the reference implementation tutorial. |
| ★ | **The Illustrated GPT-2** — Jay Alammar (jalammar.github.io/illustrated-gpt2) | Decoder-only specifically. Walks through masked self-attention and per-token generation.<br>**Why ★:** foundational explainer for the decoder-only family; visual; self-contained; the architecture it describes is structurally what every modern open LLM still is. |
| ☆ | **Transformer from Scratch** — Brandon Rohrer (e2eml.school/transformers.html) | Mechanical, slow, fully verbal. Good if formulas don't click. |
| ☆ | **A Mathematical Framework for Transformer Circuits** — Anthropic (transformer-circuits.pub/2021/framework) | What attention heads actually compute — induction heads, QK/OV circuits. The interpretability lens. |
| · | **Layer Normalization in the Transformer Architecture** — Xiong et al. 2020 — arxiv.org/abs/2002.04745 | Pre-LN vs post-LN. Why modern stacks put LayerNorm BEFORE the sub-layers. |

## 2. MLP / FFN (Part B of our walkthrough)

| | Item | Why |
|---|---|---|
| ★ | **Transformer Feed-Forward Layers Are Key-Value Memories** — Geva et al. 2020 — arxiv.org/abs/2012.14913 | The "FFN as key-value lookup" mental model. This is where the intuition I gave you came from.<br>**Why ★:** primary source for the dominant mental model of what the FFN does; short; self-contained; not retracted and the model has only been reinforced by later interpretability work (ROME, MEMIT). |
| ☆ | **GLU Variants Improve Transformer** — Shazeer 2020 — arxiv.org/abs/2002.05202 | Why modern LLMs use SwiGLU instead of plain ReLU/GELU. Tiny paper, big result. |
| ☆ | **Locating and Editing Factual Associations in GPT** — Meng et al. 2022 (ROME) — arxiv.org/abs/2202.05262 | Demonstrates that facts live in specific FFN rows. Makes "MLP stores knowledge" concrete. |

## 3. Modern decoder-only LLM design (Llama / Qwen / Mistral lineage)

| | Item | Why |
|---|---|---|
| ★ | **The Llama 3 Herd of Models** — Meta 2024 — arxiv.org/abs/2407.21783 | The most comprehensive open recipe: data, architecture, scaling, post-training. The single best modern LLM tech report.<br>**Why ★:** primary source; long but section-skimmable; self-contained (recaps every choice); not yet superseded as the most thorough public end-to-end recipe; foundational reference for everything from data curation to post-training. |
| ☆ | **Llama 2: Open Foundation and Fine-Tuned Chat Models** — Touvron et al. 2023 — arxiv.org/abs/2307.09288 | Reads cleanly; introduces GQA, RoPE choices, RLHF pipeline. Good for "why Llama looks the way it does." |
| ☆ | **RoFormer: Rotary Position Embedding** — Su et al. 2021 — arxiv.org/abs/2104.09864 | RoPE — how modern LLMs encode position. Replaces the sinusoidal embeddings from the original transformer. |
| ☆ | **GQA: Grouped-Query Attention** — Ainslie et al. 2023 — arxiv.org/abs/2305.13245 | The KV-cache memory trick used in Llama-2 70B onward. Important for serving cost. |

## 4. Mixture-of-Experts (relevant to your `Qwen3-30B-A3B-Instruct-2507` serve)

| | Item | Why |
|---|---|---|
| ★ | **Mixtral of Experts** — Mistral 2024 — arxiv.org/abs/2401.04088 | The cleanest modern MoE report. Read this first for "what is an MoE and why does it work."<br>**Why ★:** primary source; short; self-contained; the canonical "what is an open MoE" reference; not superseded as the entry point even though larger MoEs exist. |
| ★ | **DeepSeek-V3 Technical Report** — DeepSeek 2024 — arxiv.org/abs/2412.19437 | 671B/37B-active. State of the art for open MoE. The auxiliary-loss-free routing trick alone is worth the read.<br>**Why ★:** primary source from the current frontier of open MoE; introduces production techniques (aux-loss-free routing, MLA) you will literally meet in vLLM/SGLang flags; self-contained recap of the design. **Read AFTER Mixtral** — DeepSeek-V3 assumes you already understand the basic top-K router + expert-balancing loss setup that Mixtral introduces cleanly. |
| ☆ | **Switch Transformer** — Fedus et al. 2021 — arxiv.org/abs/2101.03961 | The paper that put modern MoE on the map. Explains routing, load balancing, expert capacity. |
| · | **GShard** — Lepikhin et al. 2020 — arxiv.org/abs/2006.16668 | Earlier; explains expert parallelism across many devices. Background for vLLM's EP. |

## 5. State-space / hybrid models (Mamba, Jamba)

| | Item | Why |
|---|---|---|
| ☆ | **Mamba: Linear-Time Sequence Modeling with Selective State Spaces** — Gu & Dao 2023 — arxiv.org/abs/2312.00752 | The selective SSM paper. Dense but essential reading **once you actively consider non-transformer serving.**<br>**Why ☆ not ★** *(workload-relative)*: there's a real gap between "everyone cites it" and "everyone *runs* it." Production stacks — yours included — remain transformer-only. ★ implies "mandatory for orientation"; Mamba is mandatory only when a Mamba/hybrid model lands in autoresearch or coder-next. Promote to ★ at that point. |
| ☆ | **A Visual Guide to Mamba and State Space Models** — Maarten Grootendorst (newsletter.maartengrootendorst.com) | Pictures-first walkthrough; tames the math. |
| ☆ | **Jamba: A Hybrid Transformer-Mamba Language Model** — AI21 2024 — arxiv.org/abs/2403.19887 | First production-grade hybrid. Shows the engineering trade you'd make in vLLM. |

## 6. Multi-modal LLMs

| | Item | Why |
|---|---|---|
| ☆ | **Visual Instruction Tuning (LLaVA)** — Liu et al. 2023 — arxiv.org/abs/2304.08485 | The "vision encoder + adapter + LLM" recipe in 8 pages. |
| · | **Qwen2-VL Technical Report** — Qwen team 2024 — arxiv.org/abs/2409.12191 | Production-grade VL system. Read when you actually want to serve a VL model. |

## 7. Embedding & retrieval (relevant to your LanceDB stack)

| | Item | Why |
|---|---|---|
| ★ | **Sentence-BERT** — Reimers & Gurevych 2019 — arxiv.org/abs/1908.10084 | The bi-encoder pattern that powers most modern retrieval. Short and clear.<br>**Why ★:** primary source; short; self-contained; the bi-encoder pattern it introduced has been *extended* but not *replaced* — every modern embedding model (E5, BGE, GTE) is a descendant. |
| ☆ | **Text Embeddings by Weakly-Supervised Contrastive Pre-training (E5)** — Wang et al. 2022 — arxiv.org/abs/2212.03533 | One of the best open embedding model recipes. |
| ☆ | **ColBERT: Efficient Passage Search via Contextualized Late Interaction over BERT** — Khattab & Zaharia 2020 — arxiv.org/abs/2004.12832 | The other paradigm — token-level late interaction. Important to know it exists. |
| · | **BGE M3-Embedding** — Chen et al. 2024 — arxiv.org/abs/2402.03216 | Modern multi-vector / multi-functionality embedder. |

---

## 8. vLLM — the serving systems half (coming next in our walkthrough)

| | Item | Why |
|---|---|---|
| ★ | **Efficient Memory Management for LLM Serving with PagedAttention (vLLM)** — Kwon et al. 2023 — arxiv.org/abs/2309.06180 | The vLLM paper. Read this once and the whole "why is vLLM fast" page makes sense.<br>**Why ★:** primary source for the system you actually run; short (~12 pages); self-contained; the entire vLLM serving model — KV blocks, copy-on-write, scheduler — is described here and is still what the codebase does. |
| ★ | **FlashAttention** — Dao et al. 2022 — arxiv.org/abs/2205.14135 | IO-aware attention. The single most-cited inference optimization of the last 3 years.<br>**Why ★:** primary source; short; self-contained (re-derives attention before the optimization); the IO-awareness insight underlies every fast-attention kernel since (FA2, FA3, FlashInfer, FlashMLA). |
| ☆ | **FlashAttention-2** — Dao 2023 — arxiv.org/abs/2307.08691 | The version actually deployed in production. Read after v1. |
| ☆ | **Orca: A Distributed Serving System for Transformer-Based Generative Models** — Yu et al., OSDI 2022 | Where "continuous batching" comes from. Foundational for high-throughput serving. |
| ☆ | **vLLM docs — Architecture page** — docs.vllm.ai (latest) | Read after the PagedAttention paper. The engineering glue. |
| ☆ | **Large Transformer Model Inference Optimization** — Lilian Weng — lilianweng.github.io/posts/2023-01-10-inference-optimization/ | Single-post survey of serving-side optimizations: quantization, distillation, attention variants, MoE serving, speculative decoding — all in one place. The bridge between the PagedAttention paper and "why is my vLLM flag doing what it's doing." |

## 9. Quantization (FP8 / INT4 / GPTQ / AWQ)

| | Item | Why |
|---|---|---|
| ★ | **GPTQ: Accurate Post-Training Quantization for Generative Pre-trained Transformers** — Frantar et al. 2022 — arxiv.org/abs/2210.17323 | The classic 4-bit weight quant scheme. Still relevant.<br>**Why ★:** primary source; short; self-contained; still in production use; the GPTQ format is natively supported by vLLM and HF — you'll encounter it any time you load a 4-bit model. |
| ★ | **AWQ: Activation-aware Weight Quantization** — Lin et al. 2023 — arxiv.org/abs/2306.00978 | The other dominant 4-bit scheme; often beats GPTQ at the same bitwidth.<br>**Why ★:** primary source; short; self-contained; AWQ is now the default release format for many modern open models (Qwen, Llama variants) — knowing both schemes is mandatory to read model cards. |
| ☆ | **A Visual Guide to Quantization** — Maarten Grootendorst (newsletter.maartengrootendorst.com) | The clearest mental-model intro. Read first if quant feels like magic. |
| ☆ | **FP8 Formats for Deep Learning** — Micikevicius et al. 2022 — arxiv.org/abs/2209.05433 | What FP8 actually is. Hopper/H100/H200/B200 era. |
| · | **SmoothQuant** — Xiao et al. 2022 — arxiv.org/abs/2211.10438 | Activation outliers and how W8A8 quant became viable. |

## 10. Speculative decoding (vLLM's `speculative_*` flags)

| | Item | Why |
|---|---|---|
| ★ | **Fast Inference from Transformers via Speculative Decoding** — Leviathan et al. 2022 — arxiv.org/abs/2211.17192 | The original idea. Crystal clear.<br>**Why ★:** primary source; short; self-contained; conceptually clean; every later spec-dec paper (Medusa, EAGLE, DFlash) cites and extends it — read this first or the others won't make sense. |
| ☆ | **EAGLE: Speculative Sampling Requires Rethinking Feature Uncertainty** — Li et al. 2024 — arxiv.org/abs/2401.15077 | What vLLM/SGLang ship today. |

## 11. Parallelism for distributed inference

| | Item | Why |
|---|---|---|
| ★ | **Megatron-LM** — Shoeybi et al. 2019 — arxiv.org/abs/1909.08053 | Tensor parallelism explained. Origin of the splits you see in vLLM.<br>**Why ★:** primary source for tensor parallelism; short; self-contained; the row/column splits described here are literally what vLLM's `--tensor-parallel-size` flag implements — not superseded. |
| ☆ | **GPipe** — Huang et al. 2018 — arxiv.org/abs/1811.06965 | Pipeline parallelism. Less relevant for inference but useful framing. |
| · | **DeepSpeed Inference / Megatron-Turing reports** | Background reading on serving giant models across many GPUs. |

## 12. Fine-tuning & adaptation

| | Item | Why |
|---|---|---|
| ★ | **LoRA: Low-Rank Adaptation of Large Language Models** — Hu et al. 2021 — arxiv.org/abs/2106.09685 | Every "multi-LoRA serving" feature traces back to this 8-page paper.<br>**Why ★:** primary source; 8 pages; self-contained; still the dominant parameter-efficient fine-tuning method; cited by every multi-LoRA serving feature in vLLM/SGLang/TGI. |
| ☆ | **QLoRA** — Dettmers et al. 2023 — arxiv.org/abs/2305.14314 | LoRA over a quantized base. The recipe most people actually use to fine-tune. |
| ☆ | **InstructGPT** — Ouyang et al. 2022 — arxiv.org/abs/2203.02155 | RLHF, explained by the team that made ChatGPT work. |
| ☆ | **Direct Preference Optimization (DPO)** — Rafailov et al. 2023 — arxiv.org/abs/2305.18290 | The simpler alignment recipe that displaced RLHF for most open models. |

---

## Video / lecture series (cross-cutting)

| | Item | Why |
|---|---|---|
| ★ | **Andrej Karpathy — "Neural Networks: Zero to Hero"** (YouTube playlist) | Builds backprop → MLPs → transformers → GPT from scratch. The single best video resource in the field.<br>**Why ★:** foundational; finite (~10 episodes, build-along); zero prereqs (starts from `dy/dx`); nothing supersedes it; near-universal recommendation in the field. |
| ★ | **Andrej Karpathy — "Let's reproduce GPT-2 (124M)"** (YouTube) | 4 hours of training a real GPT-2. Watch after the "Let's build GPT" video.<br>**Why ★:** primary instructor; finite (one video, follow-along repo); self-contained continuation of the Zero-to-Hero arc; still current — modern training tricks (FlashAttention, mixed precision, DDP) are all in it. |
| ☆ | **Andrej Karpathy — "State of GPT"** (Microsoft Build 2023, YouTube ~40 min) | Pretraining → SFT → RLHF as a pipeline, narrated by the field's clearest teacher. Pairs with "Intro to LLMs": Intro covers *what* an LLM is; State of GPT covers *how the modern stack actually trains one*. Some specific tooling references (RLHF as the alignment recipe) have aged into the more diverse DPO/IPO/KTO landscape, but the pipeline framing is durable. |
| ★ | **3Blue1Brown — "But what is a GPT?" / "Attention in transformers" / "How LLMs store facts"** (YouTube, "Deep Learning" series Ch. 5–7) | Best visual intuition for attention and FFN in the field. ~25 min each.<br>**Why ★:** *the* answer to "transformers feel too abstract." Every matrix multiplication is animated frame-by-frame; you watch Q × Kᵀ form, softmax distribute weights, and V vectors get pulled together. Self-contained, finite (3 videos), not superseded — nothing else is this visually concrete. |
| ☆ | **Stanford CS25 — Transformers United** (YouTube) | Guest lectures from authors of major papers. Cherry-pick episodes by topic. |
| ☆ | **Umar Jamil — "Coding Llama 2 from scratch" / "Mistral / Mixtral from scratch"** (YouTube) | Long-form code walkthroughs. Heavier than Karpathy but covers GQA, RoPE, MoE in code. |

## Interactive visualizations (when papers/videos feel too abstract)

| | Item | Why |
|---|---|---|
| ★ | **LLM Visualization** — Brendan Bycroft (bbycroft.net/llm) | Interactive 3D walk-through of nano-GPT and GPT-2 doing inference on a real input. Every weight matrix, every activation, every attention score is a 3D grid of numbers you can hover over.<br>**Why ★:** no abstraction left to hide behind — you see the actual tensor shapes, the actual dot products, the actual softmax outputs. ~30 min. After this, "Attention Is All You Need" reads like documentation. |
| ★ | **Transformer Explainer** — Georgia Tech (poloclub.github.io/transformer-explainer) | Type your own text; watch GPT-2 process it in real-time. Attention heads light up; temperature dial shows distribution shifts.<br>**Why ★:** the visualization is driven by *your* input, so the patterns are about something you care about. ~15 min. Self-contained, browser-only, no install. |
| ☆ | **Tensor Puzzles** — Sasha Rush (github.com/srush/Tensor-Puzzles) | 21 tiny PyTorch puzzles. Builds tensor intuition by hand. Optional follow-up: GPU Puzzles, Triton Puzzles, Transformer Puzzles. |
| ☆ | **nn.labml.ai** — annotated PyTorch implementations | Side-by-side paper formulas + runnable code for ~50 architectures (transformer variants, MoE, Mamba, LoRA). |

## Blogs / newsletters worth subscribing to

| | Source | Why |
|---|---|---|
| ★ | **Lilian Weng** — lilianweng.github.io | Long-form survey posts (attention, RLHF, agents, prompt engineering). Citation-dense, accurate, free.<br>**Why ★:** maintained primary-author surveys; each post is finite and self-contained; nothing in the long-form survey niche matches the quality + accuracy; cited by papers and courses alike. |
| ★ | **Jay Alammar** — jalammar.github.io | "Illustrated X" series. Visual-first.<br>**Why ★:** foundational visual explainers; finite posts; zero prereqs; the visual mental models have not been superseded and are referenced everywhere in the field. |
| ☆ | **Sebastian Raschka — Ahead of AI** — magazine.sebastianraschka.com | Monthly digest of important papers with clear commentary. |
| ☆ | **Maarten Grootendorst** — newsletter.maartengrootendorst.com | Best visual guides to MoE, quantization, embeddings. |
| ☆ | **Simon Willison's Weblog** — simonwillison.net | Practitioner-oriented, fast updates on what's actually shipping. |
| ☆ | **Eugene Yan** — eugeneyan.com | Applied LLM patterns, evaluation, RAG, production. |
| · | **Anthropic Transformer Circuits** — transformer-circuits.pub | Deep interpretability. Read when you want to know what's happening *inside* the model. |
| · | **HuggingFace blog** — huggingface.co/blog | Hands-on engineering posts; quant, training, serving. |

---

## Reading order if you have a single afternoon

1. ★ Karpathy "Intro to LLMs" (1 hr video) — orientation
2. ★ Jay Alammar "Illustrated Transformer" — visual intuition
3. ★ Karpathy "Let's build GPT" (2 hr video) — mechanical understanding
4. ★ Vaswani 2017 "Attention Is All You Need" — the source

After that, branch by topic.

---

## Reading order if you have a week

Day 1: items 1–4 above.
Day 2: Llama 3 paper + Illustrated GPT-2.
Day 3: Mixtral + DeepSeek-V3 (MoE).
Day 4: PagedAttention + FlashAttention-1 (vLLM serving).
Day 5: GPTQ + AWQ + a quant visual guide (quantization).
Day 6: LoRA + InstructGPT + DPO (fine-tuning / alignment).
Day 7: Mamba + Jamba (post-transformer horizon).

---

## Topics still to add as we cover them

- [ ] Tokenization (BPE, tiktoken, SentencePiece, the modern landscape)
- [ ] Sampling (temperature, top-k, top-p, min-p, repetition penalties)
- [ ] Structured output / constrained decoding (xgrammar, outlines, guidance)
- [ ] RAG patterns and evaluation
- [ ] Long-context techniques (RoPE scaling, YaRN, ring attention)
- [ ] Reasoning / chain-of-thought / R1-style RL
- [ ] Tool use & function calling internals
- [ ] Ollama internals (llama.cpp, GGUF, K-quants) — separate from vLLM's CUDA path
