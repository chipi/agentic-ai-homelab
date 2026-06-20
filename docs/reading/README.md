# Reading — curated external references

This section holds **curated reading lists** for topics the homelab
actively touches. Each page is a living doc, built up alongside the
work it backs and tagged with how each entry connects to the
operator's actual stack.

These are not generic "everything about X" indexes. The bar is high
on purpose: an item earns a slot only if it's something the operator
(or a collaborator) would genuinely benefit from reading, with the
homelab's specific deployments in mind.

## Pages

### Homelab-curated

| Page | Topic | Status |
|---|---|---|
| [LLM stack — end-to-end](llm-end-to-end.md) | Tokenization · transformer fundamentals · architectural variants (MoE, state-space, multi-modal) · embedding & retrieval · RAG · serving (vLLM, Ollama) · sampling · constrained decoding · quantization · spec-dec · parallelism · fine-tuning · reasoning · tool use. Keyed to the homelab's actual stack. | Living, actively built |
| [Self-hosting LLMs — end-to-end](self-hosting-llms.md) | The decisions behind self-hosting: TCO break-even, hardware tiers (consumer GPU vs Apple Silicon vs datacenter), quantization picks, serving framework choice (vLLM vs Ollama vs SGLang vs llama.cpp), production patterns. Reading list shaped around the homelab's working vLLM + Ollama stack. | Living, actively built |
| [Running your own coding models — end-to-end](coding-models-local.md) | The coding-specific cousin: model landscape (Qwen3-Coder, Codestral, DeepSeek-Coder), FIM autocomplete vs agentic coding, IDE integration layer (Continue, Aider, opencode, Cline), end-to-end recipes mapping to the homelab's coder-next stack. | Living, actively built |
| [Agentic coding — autonomous code agents](agentic-coding.md) | The agent harness layer for coding: plan-execute-reflect loops, Agent-Computer Interface (ACI), SWE-agent / OpenHands / Claude Code / Cursor agent mode, multi-agent coding (Claude Code Agent Teams), sandboxing (Modal, E2B, Blaxel, Northflank), Terminal-Bench. Deeper than coding-models-local on the agent layer. | Living, actively built |
| [Orchestrating agents in autonomous mode](agent-orchestration.md) | Multi-agent systems broadly: supervisor / hierarchical / swarm architectures, framework choice (LangGraph, CrewAI, AutoGen → Semantic Kernel, LlamaIndex Workflows, OpenAI Agents SDK, Mastra), MCP standardization, autonomous loops, eval + observability + recovery (the "what actually matters" angle). Domain-agnostic. | Living, actively built |

### Ports of external curated lists

| Page | Source | What it is |
|---|---|---|
| [a16z AI Canon](a16z-ai-canon.md) | [a16z.com/ai-canon](https://a16z.com/ai-canon/) — Derrick Harris, Matt Bornstein, Guido Appenzeller (2023-05-25) | Foundational reading layer. The "what the field built" companion to our end-to-end list. Static snapshot. |
| [State of AI Report](state-of-ai-report.md) | [stateof.ai](https://www.stateof.ai/) — Nathan Benaich / Air Street Capital (annual since 2018) | Annual zeitgeist. ~200-slide deck + practitioner survey + compute index per year. Six recurring dimensions: research, industry, politics, safety, survey, predictions. |
| [Anthropic Transformer Circuits](anthropic-transformer-circuits.md) | [transformer-circuits.pub](https://transformer-circuits.pub/) — Anthropic Interpretability team | Cumulative interpretability research thread. ~53 entries, organized as a chronological curriculum. Mandatory if you want to understand what's happening *inside* the models you run. |

### Author archives — indexes of single-author bodies of work

| Page | Source | What you get |
|---|---|---|
| [Lilian Weng — Lil'Log](lilian-weng-blog.md) | [lilianweng.github.io](https://lilianweng.github.io/) | Long-form research surveys: attention, RLHF, agents, hallucination, inference optimization, prompt engineering. 40+ posts since 2017. |
| [Andrej Karpathy — selected writing](karpathy-blog.md) | [karpathy.medium.com](https://karpathy.medium.com/) + YouTube + older blog | Foundational essays (Software 2.0, backprop, training recipes) + the "Neural Networks: Zero to Hero" video curriculum. The field's clearest teacher. |
| [Jay Alammar — visual explainers](jay-alammar-blog.md) | [jalammar.github.io](https://jalammar.github.io/) | The "Illustrated X" series: Transformer, GPT-2, BERT, Stable Diffusion, Word2vec, Retrieval. Visual mental models cited everywhere. |
| [Chip Huyen — production-AI writing](chip-huyen-blog.md) | [huyenchip.com](https://huyenchip.com/blog/) | Practitioner-perspective: building LLM applications, MLOps, sampling, RLHF, system architecture. Companion to her books. |
| [Simon Willison — practitioner stream](simon-willison-blog.md) | [simonwillison.net](https://simonwillison.net/) — particularly the [LLM tag](https://simonwillison.net/tags/llms/) | High-cadence practitioner news: prompt injection (he coined the term), model releases, agents, MCP, security. 1,800+ posts; this page is a topical map, not an enumeration. |

## Conventions

Most pages in this section use the **★ / ☆ / ·** tagging scheme
documented in the LLM stack end-to-end page header:

- **★** — mandatory, read first
- **☆** — strongly recommended, second pass
- **·** — reference / deep dive, read when you need it

A ★ is earned by satisfying five criteria simultaneously: primary
source or foundational explainer, short enough to finish,
self-contained, still correct, self-evidently load-bearing. Every ★
carries a `**Why ★:**` line spelling out which criteria the item
satisfies; downgrades from ★ → ☆ carry a `**Why ☆ not ★**` line.
The criteria framework keeps the lists honest as the field evolves —
when a ★ item ceases to satisfy criterion 4 (superseded), it drops
to ☆ or · with a note.

**Exception — tribute / port pages** (currently:
[`a16z-ai-canon.md`](a16z-ai-canon.md)) **do not** apply the ★/☆/·
scheme. These are offline-friendly renderings of external curated
lists; overlaying the homelab's tagging scheme on someone else's
curation would distort it. Tribute pages preserve the source's
original structure and ordering verbatim, with attribution and a
prominent link to the original.

## Adding a new page

A new reading list lands here when the homelab starts working in a
topic deeply enough that the operator wants a curated reference for
it. Suggested triggers:

- A new pillar gets a dedicated reading list (e.g. a future
  "Embedding & retrieval — practitioner reading" if the LanceDB
  stack becomes a focus area)
- A vendor / framework gets enough operational depth in the homelab
  that the operator wants the foundational papers (e.g. a future
  "vLLM internals — beyond the paper" once #1016-style sweeps drive
  enough hands-on serving work)
- A teaching arc with a collaborator produces curated material that
  belongs alongside the homelab, not in the collaborator's project
  repo (the LLM fundamentals page landed here for exactly this
  reason — moved from `podcast_scraper-FUTURE/docs/wip/`)

Page filenames are kebab-case lowercase (`llm-fundamentals.md`,
`embedding-retrieval-practitioner.md`, …). Add the page to:

1. The table above (one row, three columns: page, topic, status)
2. The `mkdocs.yml` nav under the "Reading" section

## What this section is NOT

- **Not a survey of every paper.** Items get cut when they fail one
  of the five ★ criteria — even canonical ones drop to · if they're
  no longer load-bearing for the homelab.
- **Not a substitute for primary sources.** Every entry points at the
  primary source (paper, official video, primary-author blog). This
  section is the curated index, not the content.
- **Not an academic bibliography.** No completeness requirement; the
  bar is "would the operator actually benefit from this," not
  "is this paper important to the field."
- **Not vendor-pinned.** When a paper or post is from a vendor (e.g.
  the DeepSeek-V3 technical report), it's included because it's a
  primary source for an open release the homelab might run — not for
  promotional reasons. Vendor blogs without primary-source value get
  cut.

## Pages this section does NOT hold

- ADRs / RFCs — those live in [`adr/`](../adr/README.md) and [`rfc/`](../rfc/README.md).
- Recipes (how-to / operational) — those live in `recipes/` (see
  individual recipe pages in the site nav).
- WIP notes that aren't yet curated material — those start in
  [`wip/`](../wip/README.md) and may eventually graduate here if they
  mature into curated references.
