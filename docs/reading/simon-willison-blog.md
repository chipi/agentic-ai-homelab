# Simon Willison — practitioner stream

> **Source:** [simonwillison.net](https://simonwillison.net/) and
> particularly the [LLM tag](https://simonwillison.net/tags/llms/)
> (1,806+ posts and counting).
> **Format:** Tag-organized personal weblog with high cadence (often
> multiple posts per week).
>
> This page is a **homelab topical guide** to navigating Simon's
> LLM stream — *not* a post-by-post enumeration. With 1,800+ LLM-tagged
> entries across 60+ pages of chronological archive, the value is
> knowing **which tag** or **which named series** to dig into for a
> given question, not having every post indexed here.

## Why this page exists in our Reading section

Simon Willison is **the field's best practitioner news source**.
While Lilian Weng writes monthly long-form surveys and Karpathy
publishes occasional foundational essays, Simon publishes **almost
daily** — short, focused, primary-source-citing notes on whatever
just shipped, broke, or became newly understood.

His value to the homelab is two-shaped:

1. **Topical canon** — for a handful of LLM-engineering topics, his
   posts ARE the canonical reference (prompt injection especially).
2. **Real-time field tracking** — when something new ships (a model
   release, a security disclosure, a new technique), Simon will have
   a thoughtful take within 24 hours, usually with hands-on
   experiments and primary-source links.

His weblog is also the home of the open-source **`llm` CLI tool**, a
practical tool used widely in the LLM-engineering community.

## Site structure & navigation

Simon's weblog is tag-organized rather than category-organized. The
LLM tag aggregates 1,806+ posts; adjacent tags cross-link to specific
sub-areas:

| Tag | Topic | URL |
|---|---|---|
| [`llms`](https://simonwillison.net/tags/llms/) | The umbrella tag | 1,806+ posts |
| [`generative-ai`](https://simonwillison.net/tags/generative-ai/) | Adjacent — broader than LLMs | |
| [`prompt-injection`](https://simonwillison.net/tags/prompt-injection/) | His most canonical sub-area (he coined the term in 2022) | |
| [`ai-ethics`](https://simonwillison.net/tags/ai-ethics/) | Governance and policy commentary | |
| [`coding-agents`](https://simonwillison.net/tags/coding-agents/) | AI-assisted programming | |
| [`openai`](https://simonwillison.net/tags/openai/) | OpenAI-specific releases | |
| [`anthropic`](https://simonwillison.net/tags/anthropic/) | Anthropic-specific releases | |
| [`gemini`](https://simonwillison.net/tags/gemini/) | Google releases | |
| [`mcp`](https://simonwillison.net/tags/mcp/) | Model Context Protocol | |

Each tag page has chronological browsing with pagination + an Atom
feed for following via RSS.

## Major topical sub-areas

These are the recurring "Simon canon" areas — sub-areas where his
posts function as canonical reference, not just news:

### Security & safety

- **Prompt injection attacks and defenses** — Simon coined the term
  and has tracked the entire space since 2022. His [prompt-injection
  tag](https://simonwillison.net/tags/prompt-injection/) is the most
  comprehensive single source on the topic. His "What's the worst
  that can happen?" post (in the [a16z AI Canon](a16z-ai-canon.md))
  is the canonical entry point.
- **Jailbreaking and model alignment** — ongoing coverage of
  jailbreak techniques, model alignment failures, defensive measures.
- **The "Lethal Trifecta"** — his framing of the three conditions
  (untrusted content + ability to read private data + ability to
  externally exfiltrate) that together enable serious LLM-app data
  exfiltration.
- **Export controls and AI governance** — primary-source coverage of
  US/EU regulatory developments.

### Model development & releases

- **Frontier model launches** — same-day coverage of new model
  releases (Claude versions, GPT series, Gemini, Qwen, DeepSeek,
  open-weights releases).
- **Open-weights benchmarking** — practitioner reactions to new
  open releases (testing on real tasks, not synthetic benchmarks).
- **Model architecture comparisons** — when papers drop, his
  next-day analysis is usually the best practitioner-oriented
  summary.

### Tool use & agents

- **Agent frameworks** — coverage of LangChain / LlamaIndex /
  AutoGen / Anthropic Agent SDK as they ship features.
- **Model Context Protocol (MCP)** — extensive coverage of MCP
  since its launch; one of the better sources for understanding the
  cross-vendor tool-server protocol.
- **Code execution sandboxing** — security considerations for
  letting LLMs run code.

### Applied AI engineering

- **AI-assisted programming** — coverage of GitHub Copilot, Claude
  Code, Cursor, Aider, etc. as they evolve.
- **RAG patterns** — practitioner takes on what works for
  retrieval-augmented systems.
- **LLM-powered applications and plugins** — his Datasette /
  llm CLI tool ecosystem demonstrates many production patterns.
- **Cost management at scale** — when token costs become a real
  business question.

### Governance & ethics

- **AI safety research findings** — same-day coverage when major
  safety papers drop.
- **Employment and economic disruption** — opinions and links on
  the labor-market angle.
- **Regulatory policy** — US executive orders, EU AI Act,
  state-level developments.
- **Vendor practices and transparency** — particularly when vendors
  silently degrade outputs or change pricing without warning.

## The `llm` CLI tool

Simon develops and maintains the open-source [`llm`](https://llm.datasette.io/)
command-line tool. Recent releases (0.32a3 as of the index date) added
features written by AI coding assistants (Claude), demonstrating the
self-referential workflow Simon documents heavily.

Why this matters as a reading resource: the `llm` tool's release
notes and Simon's accompanying blog posts are themselves a
practitioner curriculum on how production LLM CLIs are built and what
features matter.

## Notable posts visible on the LLM tag

A few representative recent posts (the archive moves fast — these
are illustrative, not a definitive top-N):

- **"If Claude Fable Stops Helping You, You'll Never Know"** —
  explores hidden safeguards silently degrading model outputs; a
  policy Anthropic reversed following backlash. Example of his
  vendor-transparency criticism.
- **"Why AI Hasn't Replaced Software Engineers, and Won't"** —
  cites research showing real bottlenecks remain in "deciding what
  to build" and "verifying delivery," not code generation.
- **"Claude Fable is Relentlessly Proactive"** — extended real-world
  testing of frontier-model behavior.

## What makes this stream distinctive

A few patterns worth understanding:

1. **High cadence, high signal** — multiple posts per week, each
   short (~200–800 words), each with primary-source links. Rare
   ratio.
2. **Hands-on testing** — most posts include "I tried this, here's
   what happened." Not vibes-based commentary.
3. **Long-running tag organization** — when you have a specific
   question (say, prompt injection), the tag page IS the curated
   reading list on that topic. You don't need a separate index.
4. **Personal voice, no corporate alignment** — runs the site
   himself, no PR review, no employer-sensitivity. The takes are
   his.
5. **RSS-friendly** — full content in feed, no paywall, no
   newsletter dark patterns. Subscribe to the LLM tag's Atom feed
   if you want a stream of practitioner-level field updates.

## Reading-list shape note

Unlike the other author-archive pages in this section, Simon's
weblog **doesn't really port** as a finite reading list. The right
shape is "subscribe to the relevant tag's RSS feed" rather than
"index N posts here." This page exists as a **topical map** for
navigating his stream — pointing you to the tag pages where the real
indexes live.

For one-shot reading list candidates, his most often-cited posts in
other curated lists are:

| Topic | Likely entry post |
|---|---|
| Prompt injection | [What's the worst that can happen?](https://simonwillison.net/2023/Apr/14/worst-that-can-happen/) (in a16z canon) |
| llm CLI tool | [llm CLI tool docs](https://llm.datasette.io/) |
| Lethal Trifecta | Search the [prompt-injection tag](https://simonwillison.net/tags/prompt-injection/) for "lethal trifecta" |

## Cross-references

- [`llm-end-to-end.md`](llm-end-to-end.md) cites him as ☆ in §
  Blogs (Simon Willison's Weblog — "Practitioner-oriented, fast
  updates on what's actually shipping").
- [`a16z-ai-canon.md`](a16z-ai-canon.md) includes his "What's the
  worst that can happen?" prompt-injection post in their Practical
  Guides § Reference section.
- [`README.md`](README.md) — author-archive index pages don't apply
  ★/☆/·. This page is the most "guide rather than index" of the
  author pages, because Simon's stream resists enumeration.
