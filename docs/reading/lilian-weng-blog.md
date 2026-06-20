# Lilian Weng — Lil'Log

> **Source:** [lilianweng.github.io](https://lilianweng.github.io/) —
> Lilian Weng's personal blog ("Lil'Log").
> **Mission (hers):** *"Documenting my learning notes in this blog
> since 2017."*
>
> This page is a **homelab index of selected highlights** from her
> archive — the long-form survey posts most directly relevant to the
> homelab's LLM stack. Lilian has been blogging since 2017; the full
> archive (40+ posts) covers RL, attention, RLHF, prompt engineering,
> hallucination, inference optimization, agents, diffusion, and more.
> Visit the [original](https://lilianweng.github.io/) for the
> complete archive.

## Why this page exists in our Reading section

Lilian Weng is **the single best long-form survey author writing in
ML today**. Each of her posts is a self-contained, citation-dense
reading list on its own topic — the equivalent of what a textbook
chapter would do, but free and current. Her body of work functions
as a curated curriculum even though she doesn't pitch it that way.

The homelab's `llm-end-to-end.md` cites her as a ★ blog in the
cross-cutting section. This page indexes the *specific posts* that
back specific homelab topics, so you can jump directly to the survey
you need.

## Reading order recommendation

There's no single "start here" entry; her posts are independent. But
for the homelab's stack specifically:

1. **Large Transformer Model Inference Optimization** (2023-01) —
   directly underlies `llm-end-to-end.md` § 11 (vLLM section). Read
   first if you care about serving.
2. **The Transformer Family v2** (2023-01) — comprehensive
   architecture survey across attention variants. Backs `llm-end-to-end`
   § 1–5.
3. **LLM Powered Autonomous Agents** (2023-06) — the canonical
   "what's an agent" survey. Backs § 20 (Tool use).
4. **Prompt Engineering** (2023-03) — practitioner reference for
   in-context prompting techniques.
5. **Why We Think** (2025-05) — the most recent post on test-time
   compute and chain-of-thought. Backs § 19 (Reasoning).

The remaining posts are best consumed by topic when you have a
specific question.

## Selected posts (chronological, most recent first)

> **Important note on completeness.** The list below captures her
> most recent ~10 posts. The full Lil'Log archive contains
> significantly more (older posts on RL, attention pre-transformer,
> meta-learning, GANs, diffusion fundamentals, contrastive
> representation learning, etc.). For the complete archive use the
> site's [Archive page](https://lilianweng.github.io/archives/) or
> the [Tags page](https://lilianweng.github.io/tags/).

| Date | Title | Reading time | Topic | Why it matters here |
|---|---|---|---|---|
| 2025-05-01 | [Why We Think](https://lilianweng.github.io/posts/2025-05-01-thinking/) | 40 min | Test-Time Compute & CoT | Survey of how test-time compute and chain-of-thought improve performance. Direct background for the R1 / o-series reasoning paradigm. |
| 2024-11-28 | [Reward Hacking in Reinforcement Learning](https://lilianweng.github.io/posts/2024-11-28-reward-hacking/) | 37 min | RL/Alignment | How RL agents exploit reward-function flaws. Critical for understanding RLHF training failures. |
| 2024-07-07 | [Extrinsic Hallucinations in LLMs](https://lilianweng.github.io/posts/2024-07-07-hallucination/) | 29 min | LLM Safety | Distinguishes in-context from extrinsic hallucination; argues LLMs must be "(1) factual and (2) acknowledge not knowing." |
| 2024-04-12 | [Diffusion Models for Video Generation](https://lilianweng.github.io/posts/2024-04-12-diffusion-video/) | 20 min | Generative Models | Temporal consistency challenges extending diffusion from images to video. |
| 2024-02-05 | [Thinking about High-Quality Human Data](https://lilianweng.github.io/posts/2024-02-05-human-data-quality/) | 20 min | Data/ML Infra | Human annotation quality for training data, particularly classification and RLHF labels. |
| 2023-10-25 | [Adversarial Attacks on LLMs](https://lilianweng.github.io/posts/2023-10-25-adv-attack-llm/) | 33 min | LLM Safety | Jailbreak prompts and adversarial attacks post-alignment training. |
| 2023-06-23 | [LLM Powered Autonomous Agents](https://lilianweng.github.io/posts/2023-06-23-agent/) | 31 min | LLM Applications | The canonical "what's an agent" survey: planning, memory, tool use. Backs `llm-end-to-end` § 20. |
| 2023-03-15 | [Prompt Engineering](https://lilianweng.github.io/posts/2023-03-15-prompt-engineering/) | 21 min | LLM Techniques | In-context prompting methods for steering LLM behavior without weight updates. |
| 2023-01-27 | [The Transformer Family Version 2.0](https://lilianweng.github.io/posts/2023-01-27-the-transformer-family-v2/) | 45 min | Architecture | Comprehensive refactoring of transformer architecture improvements since 2020. |
| 2023-01-10 | [Large Transformer Model Inference Optimization](https://lilianweng.github.io/posts/2023-01-10-inference-optimization/) | 9 min | ML Systems | Time and memory bottlenecks in deploying large transformers. Cited as ★ in `llm-end-to-end` § 11. |

## Earlier archive — partial list of recurring topics she's covered

Pre-2023 posts (not exhaustively indexed here — use her Archive page)
include long-form surveys on:

- Attention mechanisms (pre-transformer era variants)
- Meta-learning
- Generative adversarial networks (GANs)
- Reinforcement learning policy gradients
- Contrastive representation learning
- Diffusion model fundamentals
- Self-supervised learning
- Neural architecture search
- Object detection architectures
- BERT and the transfer-learning revolution

The earlier posts are dated technologically (the field has moved) but
methodologically still useful as primary-author surveys of their
respective areas.

## What makes her writing distinctive

A few patterns worth knowing about, useful when deciding whether to
deep-read or skim:

1. **Reading-time estimates** at the top of each post — honest, not
   marketing. A 40-minute post really is 40 minutes.
2. **Citation density** — most posts have 50+ citations linked in
   context. Following the link graph from one post is itself a
   reading list.
3. **Equation-fluent but not formula-heavy** — she includes the math
   that load-bears the explanation, skips notation when prose works.
4. **No promotional content** — no books to buy, no courses to take,
   no consulting pitches. Posts are written to clarify her own
   thinking. The blog's framing line is "documenting my learning
   notes" and it shows.
5. **Updates in-place** — some older posts have notes at the top
   like "Updated 2023 with new section on X." Worth re-reading a post
   if you read an older version.

## Affiliation note

Lilian has worked at OpenAI (where she co-led the Applied Research
team and then Safety Systems) and now at Thinking Machines Lab (a
new AI safety org). Her blog is personal — independent of employer
affiliation — but reflects the depth of context that comes from
working inside frontier-lab safety teams.

## Cross-references

- [`llm-end-to-end.md`](llm-end-to-end.md) cites her as ★ in § Blogs;
  this page indexes the *specific posts* behind topical sections.
  Particularly: her inference-optimization post backs § 11 (vLLM),
  her transformer family post backs § 1–5, her agents post backs
  § 20.
- [`a16z-ai-canon.md`](a16z-ai-canon.md) doesn't include her by name,
  though some of her cited references (Chip Huyen's RLHF post) appear.
- [`README.md`](README.md) — note that ★/☆/· tagging is not applied
  to author-archive index pages like this one.
