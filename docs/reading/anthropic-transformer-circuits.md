# Anthropic Transformer Circuits

> **Source:** [transformer-circuits.pub](https://transformer-circuits.pub/),
> Anthropic's interpretability research thread.
> **Curators:** Anthropic's Interpretability team (Chris Olah, Adam Jermyn,
> Neel Nanda, Catherine Olsson, Trenton Bricken, Adam Templeton, Sam Marks,
> Jack Lindsey, Tom Henighan, Nelson Elhage, Tom Conerly, and many others
> across years).
> **Mission (theirs):** *"Can we reverse engineer transformer language
> models into human-understandable computer programs?"*
>
> This page is a **homelab index of the publication archive**, organized
> chronologically and by theme. All curation, structure, and item
> descriptions trace to the Transformer Circuits team — this rendering
> only makes the archive browsable offline.

## Why this page exists in our Reading section

The Transformer Circuits thread is the **single most cohesive
interpretability research curriculum** in the field. Unlike a blog
or a paper series, it's a *cumulative thread*: each post builds on
the previous, and the team explicitly treats it as a chain of
investigations rather than discrete publications.

This makes it different in shape from the homelab's other reading
materials:

| | [llm-end-to-end](llm-end-to-end.md) | [a16z canon](a16z-ai-canon.md) | [State of AI](state-of-ai-report.md) | **Transformer Circuits** |
|---|---|---|---|---|
| Shape | Curated breadth | Curated breadth | Annual snapshot | **Cumulative depth** |
| Style | Practitioner-keyed | Field-canonical | Industry zeitgeist | **Research thread** |
| Read order | Topic branches | Star-rated | Latest year | **Chronological** |
| Updates | Operator-curated | Static | Annual | **Multiple per year** |

The thread is mandatory reading if you want to *understand what's
happening inside* the models you're running. The homelab's other
reading lists focus on what to do; this is about what's actually
going on under the hood.

## Reading order recommendation

The team doesn't publish a "start here" guide, but the canonical
entry path through the archive is:

1. **A Mathematical Framework for Transformer Circuits** (2021,
   Elhage et al.) — the foundational paper that established the
   thread's framing. **Read first.**
2. **In-Context Learning and Induction Heads** (2022, Olsson et al.)
   — the first big empirical result: induction heads as the primary
   in-context learning mechanism, with a documented phase change.
3. **Toy Models of Superposition** (Elhage et al., 2022) — explains
   why neurons are polysemantic and what to do about it.
4. **Towards Monosemanticity** (Bricken et al., 2023) — sparse
   autoencoders extract interpretable features from one-layer
   transformers.
5. **Scaling Monosemanticity** (Templeton et al., 2024) — same
   technique applied at production scale (Claude 3 Sonnet).
6. **Circuit Tracing + On the Biology of a Large Language Model**
   (Ameisen / Lindsey et al., March 2025) — attribution graphs and
   the deepest "what's actually computed" investigation to date.
7. **Emergent Introspective Awareness** (Lindsey, 2025) — recent
   frontier: can models introspect on their own internal states?

After those seven, the archive's monthly "Circuits Updates" posts
become useful as ongoing surface-level scans of the team's
in-progress work.

## Publication archive (chronological, most recent first)

### 2026

| Date | Title | Authors | URL |
|---|---|---|---|
| 2026 | Circuits Updates — May 2026 | (team) | [link](https://transformer-circuits.pub/2026/may-update/index.html) |
| 2026 | Natural Language Autoencoders Produce Unsupervised Explanations of LLM Activations | Fraser-Taliente, Kantamneni, Ong, et al. | [link](https://transformer-circuits.pub/2026/nla/index.html) |
| 2026 | HeadVis | (team) | [link](https://transformer-circuits.pub/2026/headvis/index.html) |
| 2026 | Emotion Concepts and their Function in a Large Language Model | Sofroniew et al. | [link](https://transformer-circuits.pub/2026/emotions/index.html) |

### 2025

| Date | Title | Authors | URL |
|---|---|---|---|
| Dec 2025 | Activation Oracles (cross-post) | (team) | [link](https://alignment.anthropic.com/2025/activation-oracles/) |
| Nov 2025 | Circuits Updates — November 2025 | (team) | [link](https://transformer-circuits.pub/2025/november-update/index.html) |
| 2025 | Emergent Introspective Awareness in Large Language Models | Lindsey | [link](https://transformer-circuits.pub/2025/introspection/index.html) |
| Oct 2025 | Circuits Updates — October 2025 | (team) | [link](https://transformer-circuits.pub/2025/october-update/index.html) |
| 2025 | When Models Manipulate Manifolds: The Geometry of a Counting Task | Gurnee et al. | [link](https://transformer-circuits.pub/2025/linebreaks/index.html) |
| Sep 2025 | Circuits Updates — September 2025 | (team) | [link](https://transformer-circuits.pub/2025/september-update/index.html) |
| Aug 2025 | Circuits Updates — August 2025 | (team) | [link](https://transformer-circuits.pub/2025/august-update/index.html) |
| Jul 2025 | A Toy Model of Mechanistic (Un)Faithfulness | (team) | [link](https://transformer-circuits.pub/2025/faithfulness-toy-model/index.html) |
| 2025 | Tracing Attention Computation Through Feature Interactions | Kamath et al. | [link](https://transformer-circuits.pub/2025/attention-qk/index.html) |
| Jul 2025 | A Toy Model of Interference Weights | (team) | [link](https://transformer-circuits.pub/2025/interference-weights/index.html) |
| Jul 2025 | Sparse Mixtures of Linear Transforms | (team) | [link](https://transformer-circuits.pub/2025/bulk-update/index.html) |
| Jul 2025 | Circuits Updates — July 2025 | (team) | [link](https://transformer-circuits.pub/2025/july-update/index.html) |
| Jul 2025 | Automated Auditing | (team) | [link](https://alignment.anthropic.com/2025/automated-auditing/) |
| Apr 2025 | Circuits Updates — April 2025 | (team) | [link](https://transformer-circuits.pub/2025/april-update/index.html) |
| Apr 2025 | Progress on Attention | (team) | [link](https://transformer-circuits.pub/2025/attention-update/index.html) |
| Mar 2025 | **On the Biology of a Large Language Model** | Lindsey et al. | [link](https://transformer-circuits.pub/2025/attribution-graphs/biology.html) |
| Mar 2025 | **Circuit Tracing: Revealing Computational Graphs in Language Models** | Ameisen et al. | [link](https://transformer-circuits.pub/2025/attribution-graphs/methods.html) |
| Feb 2025 | Insights on Crosscoder Model Diffing | (team) | [link](https://transformer-circuits.pub/2025/crosscoder-diffing-update/index.html) |
| Jan 2025 | Circuits Updates — January 2025 | (team) | [link](https://transformer-circuits.pub/2025/january-update/index.html) |

### 2024

| Date | Title | Authors | URL |
|---|---|---|---|
| Dec 2024 | Stage-Wise Model Diffing | (team) | [link](https://transformer-circuits.pub/2024/model-diffing/index.html) |
| Oct 2024 | Sparse Crosscoders for Cross-Layer Features and Model Diffing | (team) | [link](https://transformer-circuits.pub/2024/crosscoders/index.html) |
| Oct 2024 | Using Dictionary Learning Features as Classifiers | (team) | [link](https://transformer-circuits.pub/2024/features-as-classifiers/index.html) |
| Sep 2024 | Circuits Updates — September 2024 | (team) | [link](https://transformer-circuits.pub/2024/september-update/index.html) |
| Aug 2024 | Circuits Updates — August 2024 | (team) | [link](https://transformer-circuits.pub/2024/august-update/index.html) |
| Jul 2024 | Circuits Updates — July 2024 | (team) | [link](https://transformer-circuits.pub/2024/july-update/index.html) |
| Jun 2024 | Circuits Updates — June 2024 | (team) | [link](https://transformer-circuits.pub/2024/june-update/index.html) |
| May 2024 | **Scaling Monosemanticity: Extracting Interpretable Features from Claude 3 Sonnet** | Templeton et al. | [link](https://transformer-circuits.pub/2024/scaling-monosemanticity/index.html) |
| Apr 2024 | Circuits Updates — April 2024 | (team) | [link](https://transformer-circuits.pub/2024/april-update/index.html) |
| Mar 2024 | Circuits Updates — March 2024 | (team) | [link](https://transformer-circuits.pub/2024/march-update/index.html) |
| Mar 2024 | Reflections on Qualitative Research | (team) | [link](https://transformer-circuits.pub/2024/qualitative-essay/index.html) |
| Feb 2024 | Circuits Updates — February 2024 | (team) | [link](https://transformer-circuits.pub/2024/feb-update/index.html) |
| Jan 2024 | Circuits Updates — January 2024 | (team) | [link](https://transformer-circuits.pub/2024/jan-update/index.html) |

### 2023

| Date | Title | Authors | URL |
|---|---|---|---|
| Oct 2023 | **Towards Monosemanticity: Decomposing Language Models With Dictionary Learning** | Bricken et al. | [link](https://transformer-circuits.pub/2023/monosemantic-features/index.html) |
| Jul 2023 | Circuits Updates — July 2023 | (team) | [link](https://transformer-circuits.pub/2023/july-update/index.html) |
| May 2023 | Circuits Updates — May 2023 | (team) | [link](https://transformer-circuits.pub/2023/may-update/index.html) |
| May 2023 | Interpretability Dreams | (team) | [link](https://transformer-circuits.pub/2023/interpretability-dreams/index.html) |
| May 2023 | Distributed Representations: Composition & Superposition | (team) | [link](https://transformer-circuits.pub/2023/superposition-composition/index.html) |
| Mar 2023 | Privileged Bases in the Transformer Residual Stream | (team) | [link](https://transformer-circuits.pub/2023/privileged-basis/index.html) |
| Jan 2023 | Superposition, Memorization, and Double Descent | Henighan et al. | [link](https://transformer-circuits.pub/2023/toy-double-descent/index.html) |

### 2022

| Date | Title | Authors | URL |
|---|---|---|---|
| Sep 2022 | **Toy Models of Superposition** | Elhage et al. | [link](https://transformer-circuits.pub/2022/toy_model/index.html) |
| Jun 2022 | Softmax Linear Units | (team) | [link](https://transformer-circuits.pub/2022/solu/index.html) |
| Jun 2022 | Mechanistic Interpretability, Variables, and the Importance of Interpretable Bases | (team) | [link](https://transformer-circuits.pub/2022/mech-interp-essay/index.html) |
| Mar 2022 | **In-Context Learning and Induction Heads** | Olsson et al. | [link](https://transformer-circuits.pub/2022/in-context-learning-and-induction-heads/index.html) |

### 2021

| Date | Title | Authors | URL |
|---|---|---|---|
| Dec 2021 | **A Mathematical Framework for Transformer Circuits** | Elhage et al. | [link](https://transformer-circuits.pub/2021/framework/index.html) |
| Dec 2021 | Exercises (parameter-level neural-network mechanics drills) | (team) | [link](https://transformer-circuits.pub/2021/exercises/index.html) |
| Dec 2021 | Videos (informal talks on reverse engineering transformers) | (team) | [link](https://transformer-circuits.pub/2021/videos/index.html) |
| Dec 2021 | Garcon (tooling for large-model interpretability) | (team) | [link](https://transformer-circuits.pub/2021/garcon/index.html) |
| — | PySvelte (Python ↔ web bridge for interactive diagrams) | (team) | [link](https://github.com/anthropics/PySvelte) |

### Lineage — pre-2021

The Transformer Circuits thread is the direct successor to the
original [**Distill Circuits Thread**](https://distill.pub/2020/circuits/)
(March 2020 – April 2021), which focused on convolutional networks
before the team moved to transformers. The Distill thread is itself
worth reading for the methodological foundations.

## Thematic groupings (across years)

The archive crosses several long-running research arcs. Useful for
non-chronological reading:

### Sparse Autoencoders & Monosemanticity

| Year | Paper |
|---|---|
| 2023 | Towards Monosemanticity (Bricken et al.) — one-layer transformers |
| 2024 | Scaling Monosemanticity (Templeton et al.) — Claude 3 Sonnet |
| 2024 | Dictionary Learning Features as Classifiers |

### Toy Models

| Year | Paper |
|---|---|
| 2022 | Toy Models of Superposition (Elhage et al.) — foundational |
| 2023 | Superposition, Memorization, and Double Descent (Henighan et al.) |
| 2025 | A Toy Model of Mechanistic (Un)Faithfulness |
| 2025 | A Toy Model of Interference Weights |

### Attention Mechanisms

| Year | Paper |
|---|---|
| 2022 | In-Context Learning and Induction Heads (Olsson et al.) |
| 2025 | Progress on Attention |
| 2025 | Tracing Attention Computation Through Feature Interactions (Kamath et al.) |

### Model Diffing & Cross-Model Analysis

| Year | Paper |
|---|---|
| 2024 | Sparse Crosscoders for Cross-Layer Features and Model Diffing |
| 2024 | Stage-Wise Model Diffing |
| 2025 | Insights on Crosscoder Model Diffing |

### Attribution & Circuit Tracing

| Year | Paper |
|---|---|
| 2025 | Circuit Tracing: Revealing Computational Graphs (Ameisen et al.) — **methods paper** |
| 2025 | On the Biology of a Large Language Model (Lindsey et al.) — **application to Claude 3.5 Haiku** |

### Model Introspection & Self-Explanation

| Year | Paper |
|---|---|
| 2025 | Emergent Introspective Awareness (Lindsey) |
| 2025 | Activation Oracles (cross-posted with Alignment) |
| 2026 | Natural Language Autoencoders (Fraser-Taliente et al.) |

## Supporting resources (beyond the papers)

The thread also publishes:

- **Interactive visualization tools** — HeadVis (2026), inline
  attention-head visualizations in many papers
- **Exercises** for learning neural-network mechanics at the
  parameter level (2021)
- **Video talks** — informal walkthroughs of the team's research
  (2021)
- **Infrastructure tools** — PySvelte (Python ↔ web), Garcon
  (model-introspection tooling)

## Cross-references

- [`llm-end-to-end.md`](llm-end-to-end.md) § 1–4 cover the same
  transformer mechanics the Circuits thread investigates — read those
  first if "what's a residual stream" needs context. The thread
  references Anthropic Transformer Circuits as ☆ background already.
- [`a16z-ai-canon.md`](a16z-ai-canon.md) doesn't include this thread
  (it post-dates the canon's foundational layer); the gap is exactly
  why this page exists.
- [`README.md`](README.md) — section overview. Note that the ★/☆/·
  tagging is NOT applied to this page (preserves the thread's
  cumulative-curriculum framing).
