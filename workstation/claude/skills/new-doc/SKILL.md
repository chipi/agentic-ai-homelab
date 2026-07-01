---
name: new-doc
description: Scaffold a new documentation file — ADR, RFC, recipe, or wip note — from the repo's conventions, assign the next number/slug, wire it into the mkdocs nav, update the section index, and keep the strict build green. Use when starting an ADR/RFC/recipe/design note, or when asked to write up a decision or a runbook.
---

# new-doc

Create a new doc in the right place, numbered and wired, so it's discoverable and
the strict build stays green. Never leave an orphan page.

## Pick the type

| Type | Dir | Filename | For |
|---|---|---|---|
| ADR | `docs/adr/` | `ADR-NNNN-slug.md` | architectural decisions that govern the repo's design |
| RFC | `docs/rfc/` | `RFC-NNNN-slug.md` | proposals under discussion, before a decision |
| Recipe | `docs/recipes/` | `slug.md` | a runbook / how-to for a repeatable operation |
| WIP note | `docs/wip/` | `slug.md` | plans, analyses, in-progress work |

ADR vs decision-log: if a future contributor needs it to make a *consistent
change* → ADR. A one-shot operational choice (port, image, defer-vs-do) → append
a `D-NNNN` entry to `docs/history/0002-decisions.md` instead.

## Steps

1. **Next id.** For numbered types, find the highest existing `NNNN` in the dir
   and add 1 (never renumber). Slug = short kebab-case.
2. **Scaffold** by matching an existing sibling. Required frames:
   - **ADR:** `# ADR-NNNN — <title>` · `**Status:** Proposed` · `**Date:**` ·
     then **ctx** (the problem) / **Decision** / **Consequences**
     (positive / negative / neutral) / **Alternatives considered**. Keep under
     ~200 lines; split if it grows past that.
   - **Recipe:** title · **Why this exists** · **Quick reference** · steps ·
     **Verification** · **Troubleshooting**.
3. **Wire the mkdocs nav.** Add the page under its section in `mkdocs.yml` `nav:`
   (the nav is explicit — an unlisted page under `docs/` is an orphan). Preserve
   sibling ordering.
4. **Update the section index** (`README.md`) if it enumerates entries.
5. **Validate.** Run the `docs-preflight` skill — the strict build must stay green.
