# Andrej Karpathy — selected writing

> **Source:** [karpathy.medium.com](https://karpathy.medium.com/) plus
> his older blog at [karpathy.github.io](https://karpathy.github.io/)
> and his YouTube channel **Andrej Karpathy** for the "Neural Networks:
> Zero to Hero" series.
> **Bio (his):** *"I like to train deep neural nets on large datasets."*
>
> This page is a **homelab index of his foundational essays + video
> curriculum**. Karpathy's writing is split across several venues (old
> blog, Medium, YouTube, X/Twitter); this page collects the
> reading-list-worthy long form across them.

## Why this page exists in our Reading section

Andrej Karpathy is **the field's clearest and most respected
teacher**. His foundational essays (Software 2.0, Yes you should
understand backprop, A recipe for training neural networks) shaped
how a generation of ML engineers think; his YouTube series ("Neural
Networks: Zero to Hero", "Let's build GPT", "Let's reproduce GPT-2",
"Let's build the GPT Tokenizer") is the universal "how do I actually
learn this stuff" recommendation.

The homelab's `llm-end-to-end.md` cites him heavily — every video in
the foundations section, plus his Intro to LLMs talk. This page
indexes the **written corpus** to complement the video material.

## What this page covers vs. doesn't

- ✓ His **long-form essays** on Medium and his older blog
  (`karpathy.github.io`)
- ✓ His **video curriculum** as a structured learning path (cross-link
  to YouTube)
- ✗ His **X/Twitter posts** — high-signal but stream-shaped, not
  indexable as reading list
- ✗ His **code repositories** (nanoGPT, llm.c, etc.) — different
  kind of artifact; pointers below but not the focus

## The foundational essays (chronological, most cited first)

### 1. Software 2.0 (2017-11-11)

[karpathy.medium.com/software-2-0-...](https://karpathy.medium.com/software-2-0-a64152b37c35)

The essay that named the shift. Frames neural networks as "a new and
powerful way to program computers" — programs you train rather than
write. **The single most cited essay in modern ML engineering
culture**; if a colleague says "this is a Software 2.0 problem," this
is the reference.

Already in [`a16z-ai-canon.md`](a16z-ai-canon.md) § Gentle
Introduction as the canon's opening item.

### 2. Yes You Should Understand Backprop (2016-12-19)

[karpathy.medium.com/yes-you-should...](https://karpathy.medium.com/yes-you-should-understand-backprop-e2f06eab496b)

Educational essay from his CS231n days. Argues against treating
backprop as a black box: even practitioners using auto-diff frameworks
benefit from knowing what the derivatives are doing. **The case for
fundamentals over abstraction layers**, before "vibe coding" was a
thing.

Already in [`a16z-ai-canon.md`](a16z-ai-canon.md) § Foundational
Learning.

### 3. A Recipe for Training Neural Networks (2019-04, on his older blog)

[karpathy.github.io/2019/04/25/recipe/](https://karpathy.github.io/2019/04/25/recipe/)

The hands-on companion to Software 2.0. A step-by-step pragmatic
checklist for training neural networks reliably, with anti-patterns
called out. "Become one with the data" → "set up the end-to-end
training/eval skeleton + get dumb baselines" → ... The single best
piece of practical training-loop advice in the field, even years
later.

### 4. AlphaGo, in Context (2017-05-31)

[karpathy.medium.com/alphago-in-context...](https://karpathy.medium.com/alphago-in-context-c47718cb95a5)

Now historical (post-DeepSeek-R1 reasoning paradigm makes this read
like prehistory), but the framing of why AlphaGo mattered is durable.
Updated October 2017 to address AlphaGo Zero.

### 5. Other Medium posts (less individually load-bearing but
worth knowing about)

| Date | Title | Note |
|---|---|---|
| 2017-05-24 | [ICML Accepted Papers Institution Stats](https://karpathy.medium.com/icml-accepted-papers-institution-stats-bad8d2943f5d) | Conference-research demographics. Vintage. |
| 2017-04-07 | [A Peek at Trends in Machine Learning](https://karpathy.medium.com/a-peek-at-trends-in-machine-learning-ab8a1085a106) | Google Trends analysis. Vintage. |
| 2017-03-14 | [ICLR 2017 vs arxiv-sanity](https://karpathy.medium.com/iclr-2017-vs-arxiv-sanity-d1488ac5c131) | Cross-references conference decisions with community feedback. |
| 2017-01-17 | [Virtual Reality: Still Not Quite There, Again](https://karpathy.medium.com/virtual-reality-still-not-quite-there-again-5f51f2b43867) | Off-topic for AI reading; included for archive completeness. |

### Older essays on his original blog (`karpathy.github.io`)

Pre-Medium, his older blog at [`karpathy.github.io`](https://karpathy.github.io/)
hosts the foundational essays that pre-date his Medium years:

- **The Unreasonable Effectiveness of Recurrent Neural Networks**
  (2015-05-21) — pre-transformer-era classic on RNN text generation.
  Vintage but the framing of "the model is learning representations
  of language structure" carries forward to modern LLMs.
- **A Recipe for Training Neural Networks** (2019-04-25, link
  above) — the practical training-loop guide.
- **Hacker's Guide to Neural Networks** (2014) — older walkthrough.

## The video curriculum — "Neural Networks: Zero to Hero"

His video work is the single most-recommended self-study path into
modern ML. Treated as reading material because each video has a
follow-along repo and structured learning outcomes:

| Video | Length | What you build |
|---|---|---|
| **The spelled-out intro to neural networks and backpropagation: building micrograd** | ~2.5h | A from-scratch auto-diff engine + tiny neural net |
| **The spelled-out intro to language modeling: building makemore (Part 1–5)** | ~5h total | Bigram → MLP → batchnorm → WaveNet — a tour of architecture choices |
| **Let's build GPT: from scratch, in code, spelled out** | ~2h | A working tiny GPT from a character dataset |
| **State of GPT** (Microsoft Build 2023) | ~40 min | Pretraining → SFT → RLHF as a pipeline |
| **Intro to Large Language Models** (1-hour talk) | ~1h | The single best "what's an LLM" explainer |
| **Let's reproduce GPT-2 (124M)** | ~4h | A real GPT-2 reproduction with modern training tricks |
| **Let's build the GPT Tokenizer** | ~2h | A from-scratch tiktoken |

All cited in [`llm-end-to-end.md`](llm-end-to-end.md) — the homelab
treats this video curriculum as ★ background for everything.

## Code repositories (pointers, not the focus)

| Repo | What it is |
|---|---|
| [`nanoGPT`](https://github.com/karpathy/nanoGPT) | Reference GPT-2 implementation; the codebase for "Let's reproduce GPT-2". |
| [`minGPT`](https://github.com/karpathy/minGPT) | Earlier minimal GPT implementation. |
| [`llm.c`](https://github.com/karpathy/llm.c) | LLM training in raw C/CUDA. Recent, advanced. |
| [`micrograd`](https://github.com/karpathy/micrograd) | The auto-diff engine from the "spelled-out intro" video. |
| [`makemore`](https://github.com/karpathy/makemore) | The character-level language model from the makemore video series. |
| [`arxiv-sanity-lite`](https://github.com/karpathy/arxiv-sanity-lite) | Personalized arXiv filter. |

## Why his writing landed as canon

A few patterns worth understanding, useful for deciding when to
deep-read:

1. **Naming things that didn't have names** — "Software 2.0,"
   "data engine," "stages 1/2/3 of the training pipeline"
   (pretraining/SFT/RLHF). His essays often crystallized a concept
   the field was circling.
2. **Hands-on examples over abstract argument** — backprop essay
   uses a real chain of derivatives; recipe essay gives concrete
   anti-patterns ("you're training on dirty data and don't know it").
3. **No content marketing** — he doesn't write to drive engagement.
   When he publishes, it's because he's worked through something he
   wants to share. The signal-to-noise is exceptional as a result.
4. **Cross-references his own previous work** — reading one essay
   sends you to the next; the corpus is self-reinforcing in a way
   that benefits anyone learning the field through his eyes.

## Cross-references

- [`llm-end-to-end.md`](llm-end-to-end.md) cites his videos as ★
  throughout the videos section, and his "Intro to LLMs" + "Let's
  build the GPT Tokenizer" as ★ in the starter pack + tokenization
  sections.
- [`a16z-ai-canon.md`](a16z-ai-canon.md) includes Software 2.0,
  Yes you should understand backprop, and State of GPT in their
  respective sections.
- [`README.md`](README.md) — author-archive index pages like this
  one don't apply the homelab's ★/☆/· tagging scheme.
