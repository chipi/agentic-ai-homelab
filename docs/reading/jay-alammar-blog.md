# Jay Alammar — visual explainers

> **Source:** [jalammar.github.io](https://jalammar.github.io/) — Jay
> Alammar's blog ("Visualizing machine learning one concept at a time").
> Plus his Substack (newer posts) and his book *Hands-On Large
> Language Models* at [llm-book.com](https://llm-book.com).
>
> **Site status note:** As of mid-2024, Jay is freezing the GitHub blog
> and migrating new content to his Substack. The archive remains live;
> this page indexes the existing posts.
>
> **License (his):** Creative Commons Attribution-NonCommercial-ShareAlike
> 4.0 International.

## Why this page exists in our Reading section

Jay Alammar wrote **the canonical visual explainers of the
transformer era**. His "Illustrated X" series taught a generation of
practitioners what attention actually does, what GPT-2 actually
predicts, what Stable Diffusion actually denoises. The visual mental
models from his posts are **referenced in university courses at
Stanford, Harvard, MIT, Princeton, and CMU** — and cited in nearly
every other AI reading list as the foundational visual intuition.

The homelab's `llm-end-to-end.md` cites him as ★ in the cross-cutting
Blogs section. This page indexes the **specific posts** that make up
his corpus.

## Reading order recommendation

For the homelab's specific stack, in order:

1. [**The Illustrated Transformer**](https://jalammar.github.io/illustrated-transformer/)
   — start here. The canonical visual model of attention. If you read
   nothing else of his, read this.
2. [**The Illustrated GPT-2**](https://jalammar.github.io/illustrated-gpt2/)
   — decoder-only architecture specifically. Read after the transformer
   post.
3. [**The Illustrated BERT, ELMo, and co.**](https://jalammar.github.io/illustrated-bert/)
   — transfer learning era; pre-BERT/post-BERT framing. Worth reading
   even though we run decoder-only models, because the cross-references
   shape modern multi-task fine-tuning.
4. [**The Illustrated Stable Diffusion**](https://jalammar.github.io/illustrated-stable-diffusion/)
   — when image generation comes up. Latent diffusion concepts apply
   broadly.
5. [**How GPT3 Works**](https://jalammar.github.io/how-gpt3-works-visualizations-animations/)
   — companion to Illustrated GPT-2, more focused on inference-time
   behavior.

The remaining posts are best consumed by topic when a specific
question comes up.

## The "Illustrated X" series — the canonical posts

These are the headline-makers, ordered by foundational importance:

| Title | URL | Why it's canon |
|---|---|---|
| **The Illustrated Transformer** | [link](https://jalammar.github.io/illustrated-transformer/) | THE visual model of attention. Translated to Arabic, Chinese, French, Italian, Japanese, Korean, Russian, Spanish, Vietnamese. Now expanded into his book ([llm-book.com](https://llm-book.com)). |
| **The Illustrated GPT-2 (Visualizing Transformer Language Models)** | [link](https://jalammar.github.io/illustrated-gpt2/) | Deep dive into GPT-2 + self-attention specifically. Translated to Simplified Chinese, French, Korean, Russian, Turkish. |
| **The Illustrated BERT, ELMo, and co. (How NLP Cracked Transfer Learning)** | [link](https://jalammar.github.io/illustrated-bert/) | The transfer-learning revolution in NLP. Translations: Chinese, French, Japanese, Korean, Russian, Spanish. Featured in courses at Stanford, Harvard, MIT, Princeton, CMU. |
| **The Illustrated Word2vec** | [link](https://jalammar.github.io/illustrated-word2vec/) | Word embeddings, with real-world applications at Airbnb, Alibaba, Spotify. Multiple translations. |
| **The Illustrated Stable Diffusion** | [link](https://jalammar.github.io/illustrated-stable-diffusion/) | Latent diffusion for text-to-image. Chinese and Vietnamese translations. |
| **The Illustrated Retrieval Transformer** | [link](https://jalammar.github.io/illustrated-retrieval-transformer/) | DeepMind's RETRO; how smaller models match GPT-3 via retrieval. Korean and Russian translations. |

## Adjacent visualization posts

Same author, same visual approach, applied to topics outside the
"Illustrated X" series:

| Title | URL | What it covers |
|---|---|---|
| **How GPT3 Works — Visualizations and Animations** | [link](https://jalammar.github.io/how-gpt3-works-visualizations-animations/) | GPT-3 architecture and inference-time behavior. Translated to German, Korean, Chinese, Russian, Turkish. |
| **A Visual Guide to Using BERT for the First Time** | [link](https://jalammar.github.io/a-visual-guide-to-using-bert-for-the-first-time/) | Sentence classification tutorial with Jupyter notebook. Chinese, Korean, Russian translations. |
| **Visualizing A Neural Machine Translation Model (Seq2seq + Attention)** | [link](https://jalammar.github.io/visualizing-neural-machine-translation-mechanics-of-seq2seq-models-with-attention/) | Pre-transformer attention mechanism. Referenced in MIT Deep Learning lectures. |
| **A Visual and Interactive Look at Basic Neural Network Math** | [link](https://jalammar.github.io/feedforward-neural-networks-visual-interactive/) | Mathematical foundations; Part 2 of the neural-net basics series. |
| **A Visual and Interactive Guide to the Basics of Neural Networks** | [link](https://jalammar.github.io/visual-interactive-guide-basics-neural-networks/) | Part 1; Arabic, French, Spanish translations. |
| **A Visual Intro to NumPy and Data Representation** | [link](https://jalammar.github.io/visual-numpy/) | NumPy fundamentals — tables, images, text. Multiple translations. |

## Interpretability series

Two-part series on visualizing what transformers actually do
internally:

| Part | Title | URL |
|---|---|---|
| 1 | **Interfaces for Explaining Transformer Language Models** | [link](https://jalammar.github.io/explaining-transformers/) — input saliency and neuron activation analysis |
| 2 | **Finding the Words to Say: Hidden State Visualizations for Language Models** | [link](https://jalammar.github.io/hidden-states/) — visualizes hidden states across layers using the Ecco package |
| supporting | **Explainable AI Cheat Sheet** | [link](https://jalammar.github.io/explainable-ai/) — high-level guide to interpretability methods |

## Cohere-era applied content (LLM applications tutorial series)

When he was at Cohere, he wrote a tutorial sequence covering applied
LLM usage:

- Intro to LLMs
- Prompt engineering
- Text summarization
- Semantic search
- Fine-tuning
- Token decoding
- Text classification

These live on the [Cohere blog](https://cohere.com/blog) (some
linked from his site). Less canonical than his Illustrated series
but useful as the practitioner companion.

## Newer / Substack-era content

Jay moved newer posts to his Substack mid-2024. Worth subscribing if
you want fresh content; the archive on `jalammar.github.io` is now
frozen but remains live.

Notable posts from the migration period (still on the GitHub site):

- **Generative AI and AI Product Moats** — observations on the
  field's competitive landscape
- **Remaking Old Computer Graphics With AI Image Generation** —
  case study: updating 1987 game graphics (Nemesis 2) with Stable
  Diffusion / DALL-E / Midjourney
- **Moving To Substack** — the migration announcement

## Pandas + tooling tutorials (off the LLM track but quality)

Older tutorial work on data tooling — included for archive
completeness, less directly relevant to the homelab's LLM stack:

- **A Gentle Visual Intro to Data Analysis in Python Using Pandas**
- **Visualizing Pandas' Pivoting and Reshaping Functions**
- **Supercharging Android Apps With TensorFlow**

## Video and conference content

He also presents at conferences and on YouTube. Notable:

- **YouTube Series — Jay's Intro to AI** — videos for a general audience
- **QCon 2020 — Visual Intro to Machine Learning and Deep Learning** —
  conference talk
- **Video: Intuition & Use-Cases of Embeddings in NLP & beyond** —
  QCon London talk; Word2Vec and recommendation systems
- **Language Models and Skipgram Recommenders @ MIT** — Analytics Lab
  presentation

## The book — *Hands-On Large Language Models*

He's expanded the Illustrated Transformer post + adjacent material
into a book ([llm-book.com](https://llm-book.com)). For the
homelab's purposes, the GitHub posts cover the same ground for free.
The book adds depth and exercises for those who want the bound,
structured form.

## Why his writing landed as canon

A few patterns worth understanding:

1. **Visual-first, then text** — he draws the matrix multiplication
   before he explains it. Most ML educators do the opposite. The
   visual-first approach grounds abstract concepts in concrete shape.
2. **Translation-heavy** — most posts have community translations to
   5–9 languages. This both reflects and reinforces his canonical
   status; the visual mental models translate naturally.
3. **Citation friendly** — every concept that matters is named, every
   external reference linked. Easy to cite into a course syllabus or
   another blog post.
4. **No paywalls, no engagement bait** — the GitHub blog is
   permanently free; the Substack is newer and may have paid tiers
   but the foundational content remains open.

## Cross-references

- [`llm-end-to-end.md`](llm-end-to-end.md) cites him as ★ in §
  Blogs; specific posts back the foundations sections (the
  Illustrated Transformer is implicitly the visual companion to
  every "what's attention" question).
- [`a16z-ai-canon.md`](a16z-ai-canon.md) includes The Illustrated
  Transformer and Illustrated Stable Diffusion in their Tech Deep
  Dive section.
- [`README.md`](README.md) — author-archive index pages don't apply
  ★/☆/·.
