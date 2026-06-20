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

| Page | Topic | Status |
|---|---|---|
| [LLM stack — end-to-end](llm-end-to-end.md) | Tokenization · transformer fundamentals · architectural variants (MoE, state-space, multi-modal) · embedding & retrieval · RAG · serving (vLLM, Ollama) · sampling · constrained decoding · quantization · spec-dec · parallelism · fine-tuning · reasoning · tool use. Keyed to the homelab's actual stack. | Living, actively built |

## Conventions

Every page in this section uses the **★ / ☆ / ·** tagging scheme
documented in the LLM fundamentals page header:

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
