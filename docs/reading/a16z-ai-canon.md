# a16z AI Canon

> **Source:** [a16z AI Canon](https://a16z.com/ai-canon/), published
> **2023-05-25** by **Derrick Harris**, **Matt Bornstein**, and
> **Guido Appenzeller** at Andreessen Horowitz.
>
> This page is an **offline-friendly markdown port** of that list,
> preserved in the homelab's reading section. All curation, structure,
> and item descriptions are a16z's — this rendering only makes the
> canon browsable alongside the homelab's other reading materials.
> **Visit the [original](https://a16z.com/ai-canon/) for the live
> version**, which may have been updated since this snapshot.

## Why this page exists in our Reading section

The a16z AI Canon was an unusually thoughtful curation of the
"if-you-read-nothing-else" foundations of modern AI as of mid-2023.
It pre-dates much of what the homelab actively runs (Llama 3,
DeepSeek-V3, MoE going mainstream, NVFP4, reasoning models,
production constrained decoding) — but the foundational layer it
covers (Software 2.0, the original transformer, BERT/GPT lineage,
Chinchilla scaling, RLHF / InstructGPT, FlashAttention v1, LoRA,
ReAct, Toolformer, RAG, AlphaFold, Stable Diffusion, NeRF) **is
exactly the layer the homelab's `llm-end-to-end.md` builds on top
of**. Reading the Canon first, then the homelab's end-to-end list,
gives a clear arc from "what the field built" → "what the homelab
runs today."

## Notes for reading this in late 2026

A few categories where the field has moved significantly since the
Canon's May-2023 cutoff — these are gaps the canon **doesn't** cover
and the homelab's `llm-end-to-end.md` does:

| Area | What the Canon has | What it doesn't (see `llm-end-to-end.md`) |
|---|---|---|
| Modern open LLMs | Llama 1, Alpaca | Llama 3 herd, Qwen3, Mistral lineage, DeepSeek-V3 |
| MoE | Not covered | Mixtral, DeepSeek-V3, the modern MoE serving stack |
| Long context | Not covered | RoPE PI, YaRN, Ring Attention, Lost in the Middle |
| Reasoning | Not covered | CoT, DeepSeek-R1 / o1 family, process reward modeling |
| Quantization | Not covered | GPTQ, AWQ, FP8, NVFP4 (NVIDIA Model Optimizer) |
| Constrained decoding | Not covered | Outlines, XGrammar, the FSM-over-vocabulary technique |
| Production serving | FlashAttention v1 | vLLM PagedAttention, FlashAttention-2/3, speculative decoding |
| Hybrid models | "Hungry hungry hippos" (preview) | Mamba, Jamba |
| Tool use protocols | ReAct, Toolformer | Model Context Protocol (MCP), modern agent SDKs |

The Canon's specific value today is the **gentle introduction** and
**foundational learning** sections — Karpathy, Wolfram, the Stanford
courses, the explainers. These age well because they're explaining
durable concepts (transformer mechanics, RLHF, RAG, the scaling
hypothesis) that the field still builds on.

> **A note on tagging.** This page intentionally **does not apply** the
> homelab Reading section's ★/☆/· tagging scheme. The Canon's value
> IS its flat, opinionated curation by the a16z team — overlaying our
> scheme would distort that. See [`README.md`](README.md) § Conventions
> for the exception.

---

## 1. A Gentle Introduction

| Title | Author/source | Description (a16z) |
|---|---|---|
| [Software 2.0](https://karpathy.medium.com/software-2-0-a64152b37c35) | Andrej Karpathy | Early explanation of why the new AI wave matters; establishes AI as "a new and powerful way to program computers." |
| [State of GPT](https://build.microsoft.com/en-US/sessions/db3f4859-cd30-4445-a0cd-553c3304f8e2) | Andrej Karpathy | Approachable explanation of ChatGPT/GPT models, usage, and R&D directions. |
| [What is ChatGPT doing … and why does it work?](https://writings.stephenwolfram.com/2023/02/what-is-chatgpt-doing-and-why-does-it-work/) | Stephen Wolfram | Long but "highly readable" first-principles explanation from early neural nets to modern LLMs. |
| [Transformers, explained](https://daleonai.com/transformers-explained) | Dale Markowitz | Direct, intuition-building answer to "what is an LLM, and how does it work?" |
| [How Stable Diffusion works](https://mccormickml.com/2022/12/21/how-stable-diffusion-works/) | Chris McCormick | Layperson's explanation of Stable Diffusion and text-to-image models generally. |

---

## 2. Foundational Learning

### 2.1 Explainers

| Title | Author/source | Description (a16z) |
|---|---|---|
| [Deep learning in a nutshell: core concepts](https://developer.nvidia.com/blog/deep-learning-nutshell-core-concepts/) | Nvidia | Four-part series on fundamentals of deep learning as practiced in 2015. |
| [Practical deep learning for coders](https://course.fast.ai/) | Fast.ai | Comprehensive, free course on AI fundamentals through practical examples and code. |
| [Word2vec explained](https://towardsdatascience.com/word2vec-explained-49c52b4ccb71) | Towards Data Science | Easy introduction to embeddings and tokens as LLM building blocks. |
| [Yes you should understand backprop](https://karpathy.medium.com/yes-you-should-understand-backprop-e2f06eab496b) | Andrej Karpathy | In-depth post on back-propagation mechanics. |

### 2.2 Courses

| Title | Author/source | Description (a16z) |
|---|---|---|
| [Stanford CS229](https://www.youtube.com/playlist?list=PLoROMvodv4rMiGQp3WXShtMGgzqpfVfbU) | Andrew Ng | Introduction to Machine Learning covering fundamentals. |
| [Stanford CS224N](https://www.youtube.com/playlist?list=PLoROMvodv4rOSH4v6133s9LFPRHjEmbmJ) | Chris Manning | NLP with Deep Learning through first-generation LLMs. |

---

## 3. Tech Deep Dive

### 3.1 Explainers

| Title | Author/source | Description (a16z) |
|---|---|---|
| [The illustrated transformer](https://jalammar.github.io/illustrated-transformer/) | Jay Alammar | More technical overview of transformer architecture. |
| [The annotated transformer](http://nlp.seas.harvard.edu/annotated-transformer/) | Harvard NLP | In-depth source code-level understanding; requires PyTorch knowledge. |
| [Let's build GPT: from scratch, in code, spelled out](https://www.youtube.com/watch?v=kCc8FmEb1nY) | Andrej Karpathy | Video walkthrough of building a GPT model from scratch. |
| [The illustrated Stable Diffusion](https://jalammar.github.io/illustrated-stable-diffusion/) | Jay Alammar | Introduction to latent diffusion models for image generation. |
| [RLHF: Reinforcement Learning from Human Feedback](https://huyenchip.com/2023/05/02/rlhf.html) | Chip Huyen | Explanation of RLHF, described as "one of the most important but least well-understood aspects" of ChatGPT. |
| [Reinforcement learning from human feedback](https://www.youtube.com/watch?v=hhiLw5Q_UFg) | John Schulman | Deeper dive on current state and limitations of LLMs with RLHF. |

### 3.2 Courses

| Title | Author/source | Description (a16z) |
|---|---|---|
| [Stanford CS25](https://www.youtube.com/watch?v=P127jhj-8-Y) | Multiple instructors | Transformers United: online seminar on Transformers. |
| [Stanford CS324](https://stanford-cs324.github.io/winter2022/) | Percy Liang, Tatsu Hashimoto, Chris Ré | Large Language Models covering technical and non-technical aspects. |

### 3.3 Reference and commentary

| Title | Author/source | Description (a16z) |
|---|---|---|
| [Predictive learning, NIPS 2016](https://www.youtube.com/watch?v=Ount2Y4qxQo&t=1072s) | Yann LeCun | Early case for unsupervised learning; includes the famous "cake analogy." |
| [AI for full-self driving at Tesla](https://www.youtube.com/watch?v=hx7BXih7zx8) | Andrej Karpathy | Tesla data-collection engine overview; discusses long-tailed problem complexity. |
| [The scaling hypothesis](https://gwern.net/scaling-hypothesis) | Gwern | Explanation of why scaling (more data/compute) increases model accuracy. |
| [Chinchilla's wild implications](https://www.lesswrong.com/posts/6Fpvch8RR29qLEWNH/chinchilla-s-wild-implications) | LessWrong | Analysis of Chinchilla paper; addresses whether LLM scaling will exhaust data. |
| [A survey of large language models](https://arxiv.org/pdf/2303.18223v4.pdf) | ArXiv | Comprehensive breakdown of current LLMs including timelines, size, training data. |
| [Sparks of artificial general intelligence](https://arxiv.org/abs/2303.12712) | Microsoft Research | Early GPT-4 capability analysis relative to human intelligence. |
| [The AI revolution: How Auto-GPT unleashes a new era](https://pub.towardsai.net/the-ai-revolution-how-auto-gpt-unleashes-a-new-era-of-automation-and-creativity-2008aa2ca6ae) | Towards AI | Introduction to Auto-GPT and AI agents generally. |
| [The Waluigi Effect](https://www.lesswrong.com/posts/D7PumeYTDPfBTp3i7/the-waluigi-effect-mega-post) | LessWrong | Deep dive on LLM prompting theory via "Waluigi effect" explanation. |

---

## 4. Practical Guides to Building with LLMs

### 4.1 Reference

| Title | Author/source | Description (a16z) |
|---|---|---|
| [Build a GitHub support bot with GPT3, LangChain, Python](https://dagster.io/blog/chatgpt-langchain) | Dagster | "One of the earliest public explanations" of the modern LLM app stack. |
| [Building LLM applications for production](https://huyenchip.com/2023/04/11/llm-engineering.html) | Chip Huyen | Discussion of key LLM app development challenges and suitable use cases. |
| [Prompt Engineering Guide](https://www.promptingguide.ai/) | PromptingGuide.ai | Most comprehensive guide with examples for popular models. |
| [Prompt injection: What's the worst that can happen?](https://simonwillison.net/2023/Apr/14/worst-that-can-happen/) | Simon Willison | Definitive description of prompt injection security vulnerability. |
| [OpenAI cookbook](https://github.com/openai/openai-cookbook/tree/main) | OpenAI | Definitive collection of guides and code examples for OpenAI API. |
| [Pinecone learning center](https://www.pinecone.io/learn/) | Pinecone | Useful instruction on vector search paradigm for LLM apps. |
| [LangChain docs](https://python.langchain.com/en/latest/index.html) | LangChain | Reference for LLM orchestration layer and full stack integration. |

### 4.2 Courses

| Title | Author/source | Description (a16z) |
|---|---|---|
| [LLM Bootcamp](https://fullstackdeeplearning.com/llm-bootcamp/) | Charles Frye, Sergey Karayev, Josh Tobin | Practical course for building LLM-based applications. |
| [Hugging Face Transformers](https://huggingface.co/learn/nlp-course/chapter1/1) | Hugging Face | Guide to using open-source LLMs in Transformers library. |

### 4.3 LLM benchmarks

| Title | Author/source | Description (a16z) |
|---|---|---|
| [Chatbot Arena](https://lmsys.org/blog/2023-05-03-arena/) | UC Berkeley | Elo-style ranking system for popular LLMs with user participation. |
| [Open LLM Leaderboard](https://huggingface.co/spaces/HuggingFaceH4/open_llm_leaderboard) | Hugging Face | Ranking of open-source LLMs across standard benchmarks. |

---

## 5. Market Analysis

> **Note:** This section is investment-thesis content rather than
> technical foundations. Included for faithfulness to the original
> canon; most useful for "where does the value accrue across the
> stack" framing rather than for the homelab's operational learning.

### 5.1 a16z thinking

| Title | Source | Description (a16z) |
|---|---|---|
| [Who owns the generative AI platform?](https://a16z.com/who-owns-the-generative-ai-platform/) | a16z | "Flagship assessment" of value accrual across infrastructure, model, and application layers. |
| [Navigating the high cost of AI compute](https://a16z.com/2023/04/27/navigating-the-high-cost-of-ai-compute/) | a16z | Breakdown of why generative AI requires extensive computing resources. |
| [Art isn't dead, it's just machine-generated](https://a16z.com/art-isnt-dead-its-just-machine-generated/) | a16z | Analysis of how AI reshaped creative fields faster than software development. |
| [The generative AI revolution in games](https://a16z.com/the-generative-ai-revolution-in-games/) | a16z | In-depth analysis of how AI-generated graphics will change game design and studios. |
| [The generative AI revolution will enable anyone to create games](https://a16z.com/the-generative-ai-revolution-will-enable-anyone-to-create-games/) | a16z | Follow-up on AI-generated versus user-generated content. |
| [For B2B generative AI apps, is less more?](https://a16z.com/for-b2b-generative-ai-apps-is-less-more/) | a16z | Prediction that LLM summarization will prove more valuable than text generation. |
| [Financial services will embrace generative AI faster than you think](https://a16z.com/2023/04/19/financial-services-will-embrace-generative-ai-faster-than-you-think/) | a16z | Argument for rapid AI adoption in financial services for personalization and compliance. |
| [Generative AI: The next consumer platform](https://a16z.com/generative-ai-the-next-consumer-platform/) | a16z | Analysis of generative AI opportunities across consumer sectors. |
| [To make a real difference in health care, AI will need to learn like we do](https://time.com/6274752/ai-health-care/) | a16z (Time) | Argument for developing "specialist" AIs that learn like physicians and developers. |
| [The new industrial revolution: Bio x AI](https://a16z.com/2023/05/17/the-new-industrial-revolution-bio-x-ai/) | a16z | Thesis that the next industrial revolution will be biology powered by AI. |

### 5.2 Other perspectives

| Title | Source | Description (a16z) |
|---|---|---|
| [On the opportunities and risks of foundation models](https://arxiv.org/abs/2108.07258) | Stanford | Overview paper on Foundation Models; shaped terminology in the field. |
| [State of AI Report](https://www.stateof.ai/) | State of AI | Annual roundup of AI technology, industry, policy, economics, safety. |
| [GPTs are GPTs: An early look at the labor market impact](https://arxiv.org/abs/2303.10130) | OpenAI / Penn | Predicts "around 80% of the U.S. workforce" could have 10%+ task exposure. |
| [Deep medicine: How artificial intelligence can make healthcare human again](https://www.amazon.com/Deep-Medicine-Eric-Topol-audiobook/dp/B07PJ21V5N/) | Dr. Eric Topol | Explores how AI can restore physician-patient relationships. |

---

## 6. Landmark Research Results

### 6.1 LLMs — New models

| Year | Title | Author/source | Description (a16z) |
|---|---|---|---|
| 2017 | [Attention is all you need](https://arxiv.org/abs/1706.03762) | Google Brain | Original transformer paper that "started it all"; see also the [blog](https://ai.googleblog.com/2017/08/transformer-novel-neural-network.html). |
| 2018 | [BERT: pre-training of deep bidirectional transformers](https://arxiv.org/abs/1810.04805) | Google | First publicly available LLM with variants still in use; see also the [blog](https://ai.googleblog.com/2018/11/open-sourcing-bert-state-of-art-pre.html). |
| 2018 | [Improving language understanding by generative pre-training](https://cdn.openai.com/research-covers/language-unsupervised/language_understanding_paper.pdf) | OpenAI | First GPT paper; the dominant LLM development path; see also the [blog](https://openai.com/research/language-unsupervised). |
| 2020 | [Language models are few-shot learners](https://arxiv.org/abs/2005.14165) | OpenAI | GPT-3 paper describing the decoder-only modern LLM architecture. |
| 2022 | [Training language models to follow instructions with human feedback](https://arxiv.org/abs/2203.02155) | OpenAI | InstructGPT paper on RLHF; "key unlock" for consumer LLM accessibility. See also the [blog](https://openai.com/research/instruction-following). |
| 2022 | [LaMDA: language models for dialog applications](https://arxiv.org/abs/2201.08239) | Google | Google model for free-flowing dialogue across topics. See also the [blog](https://blog.google/technology/ai/lamda/). |
| 2022 | [PaLM: Scaling language modeling with pathways](https://arxiv.org/abs/2204.02311) | Google | Large-scale cross-chip training with scaling benefits. See the [blog](https://ai.googleblog.com/2022/04/pathways-language-model-palm-scaling-to.html) and the follow-up [PaLM-2 report](https://arxiv.org/abs/2305.10403). |
| 2022 | [OPT: Open Pre-trained Transformer language models](https://arxiv.org/abs/2205.01068) | Meta | Top-performing open-source LLM with code and public datasets. See also the [blog](https://ai.facebook.com/blog/democratizing-access-to-large-scale-language-models-with-opt-175b/). |
| 2022 | [Training compute-optimal large language models](https://arxiv.org/abs/2203.15556) | DeepMind | Chinchilla paper; data-limited vs compute-limited models. See also the [blog](https://www.deepmind.com/blog/an-empirical-analysis-of-compute-optimal-large-language-model-training). |
| 2023 | [GPT-4 technical report](https://arxiv.org/abs/2303.08774) | OpenAI | Latest OpenAI model at canon time. See the [blog](https://openai.com/research/gpt-4) and [system card](https://cdn.openai.com/papers/gpt-4-system-card.pdf). |
| 2023 | [LLaMA: Open and efficient foundation language models](https://arxiv.org/abs/2302.13971) | Meta | Competitive open-source model; restricted license. See also the [blog](https://ai.facebook.com/blog/large-language-model-llama-meta-ai/). |
| 2023 | [Alpaca: A strong, replicable instruction-following model](https://crfm.stanford.edu/2023/03/13/alpaca.html) | Stanford | Demonstrates instruction tuning power in smaller open-source models. |

### 6.2 LLMs — Model improvements

| Year | Title | Author/source | Description (a16z) |
|---|---|---|---|
| 2017 | [Deep reinforcement learning from human preferences](https://proceedings.neurips.cc/paper_files/paper/2017/file/d5e2c0adad503c91f91df240d0cd4e49-Paper.pdf) | Multiple | RLHF research from gaming and robotics applied to LLMs. |
| 2020 | [Retrieval-augmented generation for knowledge-intensive NLP tasks](https://arxiv.org/abs/2005.11401) | Meta | RAG approach for improving LLM accuracy. See also the [blog](https://ai.facebook.com/blog/retrieval-augmented-generation-streamlining-the-creation-of-intelligent-natural-language-processing-models/). |
| 2021 | [Improving language models by retrieving from trillions of tokens](https://arxiv.org/abs/2112.04426) | DeepMind | RETRO approach to access non-training data. See also the [blog](https://www.deepmind.com/blog/improving-language-models-by-retrieving-from-trillions-of-tokens). |
| 2021 | [LoRA: Low-rank adaptation of large language models](https://arxiv.org/abs/2106.09685) | Microsoft | Efficient fine-tuning alternative; standard for community fine-tuning. |
| 2022 | [Constitutional AI](https://arxiv.org/abs/2212.08073) | Anthropic | RLAIF (reinforcement learning from AI feedback) for harmless assistants. |
| 2022 | [FlashAttention: Fast and memory-efficient exact attention](https://arxiv.org/abs/2205.14135) | Stanford | Enables longer sequences and higher-resolution images. See also the [blog](https://ai.stanford.edu/blog/longer-sequences-next-leap-ai/). |
| 2022 | [Hungry hungry hippos: Towards language modeling with state space models](https://arxiv.org/abs/2212.14052) | Stanford | Leading attention alternative; promising scaling path. See also the [blog](https://hazyresearch.stanford.edu/blog/2023-01-20-h3). |

### 6.3 Image generation

| Year | Title | Author/source | Description (a16z) |
|---|---|---|---|
| 2021 | [Learning transferable visual models from natural language supervision](https://arxiv.org/abs/2103.00020) | OpenAI | CLIP model linking text to images; foundation models in computer vision. See also the [blog](https://openai.com/research/clip). |
| 2021 | [Zero-shot text-to-image generation](https://arxiv.org/abs/2102.12092) | OpenAI | DALL-E combining CLIP and GPT-3; kicked off the 2022 image AI boom. See also the [blog](https://openai.com/research/dall-e). |
| 2021 | [High-resolution image synthesis with latent diffusion models](https://arxiv.org/abs/2112.10752) | Multiple | The Stable Diffusion paper (post-launch). |
| 2022 | [Photorealistic text-to-image diffusion models with deep language understanding](https://arxiv.org/abs/2205.11487) | Google | Imagen model; not yet publicly released at canon time. See also the [website](https://imagen.research.google/). |
| 2022 | [DreamBooth: Fine tuning text-to-image diffusion models](https://arxiv.org/abs/2208.12242) | Google | User-submitted subject recognition in prompts. See also the [website](https://dreambooth.github.io/). |
| 2023 | [Adding conditional control to text-to-image diffusion models](https://arxiv.org/abs/2302.05543) | Stanford | ControlNet for fine-grained image generation control. |

### 6.4 Agents

| Year | Title | Author/source | Description (a16z) |
|---|---|---|---|
| 2022 | [A path towards autonomous machine intelligence](https://openreview.net/pdf?id=BZ5a1r-kVsf) | Yann LeCun / Meta AI | Proposal on building autonomous, intelligent agents. |
| 2022 | [ReAct: Synergizing reasoning and acting in language models](https://arxiv.org/abs/2210.03629) | Princeton / Google | Testing LLM reasoning and planning abilities. See also the [blog](https://ai.googleblog.com/2022/11/react-synergizing-reasoning-and-acting.html). |
| 2023 | [Generative agents: Interactive simulacra of human behavior](https://arxiv.org/abs/2304.03442) | Stanford / Google | LLM-powered agents with emergent interactions in simulation. |
| 2023 | [Reflexion: an autonomous agent with dynamic memory and self-reflection](https://arxiv.org/abs/2303.11366) | Northeastern / MIT | Teaching LLMs to learn from mistakes and past experiences. |
| 2023 | [Toolformer: Language models can teach themselves to use tools](https://arxiv.org/abs/2302.04761) | Meta | LLMs using external tool APIs without increasing model size. |
| 2023 | [Auto-GPT: An autonomous GPT-4 experiment](https://github.com/Significant-Gravitas/Auto-GPT) | Open source | Open-source experiment expanding GPT-4 with tools and internet access. |
| 2023 | [BabyAGI](https://github.com/yoheinakajima/babyagi) | Open source | Python script using GPT-4 and vector databases for multi-task planning. |

### 6.5 Other modalities — Code generation

| Year | Title | Author/source | Description (a16z) |
|---|---|---|---|
| 2021 | [Evaluating large language models trained on code](https://arxiv.org/abs/2107.03374) | OpenAI | Codex research paper behind GitHub Copilot. See also the [blog](https://openai.com/blog/openai-codex). |
| 2021 | [Competition-level code generation with AlphaCode](https://www.science.org/stoken/author-tokens/ST-905/full) | DeepMind | Model writing better code than human programmers. See also the [blog](https://www.deepmind.com/blog/competitive-programming-with-alphacode). |
| 2022 | [CodeGen: An open large language model for code](https://arxiv.org/abs/2203.13474) | Salesforce | Underpins Replit Ghostwriter. See also the [blog](https://blog.salesforceairesearch.com/codegen/). |

### 6.6 Other modalities — Video generation

| Year | Title | Author/source | Description (a16z) |
|---|---|---|---|
| 2022 | [Make-A-Video: Text-to-video generation without text-video data](https://arxiv.org/abs/2209.14792) | Meta | Creates videos and adds motion. See also the [blog](https://makeavideo.studio/). |
| 2022 | [Imagen Video: High definition video generation with diffusion models](https://arxiv.org/abs/2210.02303) | Google | Text-to-video from the Imagen model. See also the [website](https://imagen.research.google/video/). |

### 6.7 Other modalities — Human biology and medical

| Year | Title | Author/source | Description (a16z) |
|---|---|---|---|
| 2020 | [Strategies for pre-training graph neural networks](https://arxiv.org/pdf/1905.12265.pdf) | Stanford | Groundwork for drug discovery applications. See also the [blog](https://snap.stanford.edu/gnn-pretrain/). |
| 2020 | [Improved protein structure prediction using potentials from deep learning](https://www.nature.com/articles/s41586-019-1923-7) | DeepMind | AlphaFold breakthrough in protein structure prediction. See the [blog](https://www.deepmind.com/blog/alphafold-a-solution-to-a-50-year-old-grand-challenge-in-biology) and an [explainer](https://www.blopig.com/blog/2021/07/alphafold-2-is-here-whats-behind-the-structure-prediction-miracle/). |
| 2022 | [Large language models encode clinical knowledge](https://arxiv.org/abs/2212.13138) | Google | Med-PaLM on medical licensing exams. See also the [video](https://www.youtube.com/watch?v=saWEFDRuNJc). |

### 6.8 Other modalities — Audio generation

| Year | Title | Author/source | Description (a16z) |
|---|---|---|---|
| 2020 | [Jukebox: A generative model for music](https://arxiv.org/abs/2005.00341) | OpenAI | Transformer-based music generation. See also the [blog](https://openai.com/research/jukebox). |
| 2022 | [AudioLM: a language modeling approach to audio generation](https://arxiv.org/pdf/2209.03143.pdf) | Google | Multi-type audio generation. See also the [blog](https://ai.googleblog.com/2022/10/audiolm-language-modeling-approach-to.html). |
| 2023 | [MusicLM: Generating music from text](https://arxiv.org/abs/2301.11325) | Google | State-of-the-art music generation. See also the [examples page](https://google-research.github.io/seanet/musiclm/examples/). |

### 6.9 Other modalities — Multi-dimensional image generation

| Year | Title | Author/source | Description (a16z) |
|---|---|---|---|
| 2020 | [NeRF: Representing scenes as neural radiance fields](https://arxiv.org/abs/2003.08934) | UC Berkeley | Novel view synthesis using 5D coordinates. See also the [website](https://www.matthewtancik.com/nerf). |
| 2022 | [DreamFusion: Text-to-3D using 2D diffusion](https://arxiv.org/pdf/2209.14988.pdf) | Google / UC Berkeley | Building on NeRF for 3D from text. See also the [website](https://dreamfusion3d.github.io/). |

---

## Credits (from the original a16z canon)

**Curated by:** Derrick Harris, Matt Bornstein, Guido Appenzeller — a16z, 2023-05-25.

**Special thanks to:** Jack Soslow, Jay Rughani, Marco Mascorro, Martin Casado, Rajko Radovanovic, Vijay Pande, Sonal Chokshi, and the entire a16z team.

**Lineage note:** a16z's Sonal Chokshi and the crypto team previously
built similar "canons" at the firm; the AI Canon continues that
tradition for the LLM-era.

---

## Cross-references in this Reading section

- [`llm-end-to-end.md`](llm-end-to-end.md) — the homelab's own
  curated reading list, keyed to the actual stack (vLLM + Ollama +
  NVFP4 + autoresearch). Picks up where the canon's foundations
  layer leaves off; covers the post-2023 evolution (Llama 3,
  DeepSeek-V3, modern MoE, quantization, reasoning models,
  constrained decoding).
- [`README.md`](README.md) — section overview and the criteria the
  homelab applies to other reading lists. Note that the ★/☆/·
  tagging scheme used elsewhere is intentionally NOT applied to this
  page, to preserve the canon's flat curation.
