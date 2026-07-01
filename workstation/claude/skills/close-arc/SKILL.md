---
name: close-arc
description: Close a work arc — write the next docs/history/NNNN-<arc>.md continuity entry, update the history index and mkdocs nav, strike completed items in docs/wip/NEXT_STEPS.md, append any D-NNNN operational decisions to 0002-decisions.md, and suggest the version tag. Use when wrapping up a multi-step session or a milestone. Keeps the strict docs build green.
---

# close-arc

Write the paper trail that lets the next session pick up cold. History is
**append-only** — never edit a past session doc; write a new one that references it.

## Steps

1. **Next number.** Highest `NNNN` in `docs/history/` + 1. Filename
   `NNNN-<short-slug>.md`.
2. **Write the entry**, matching the convention:
   - `# NNNN — <arc name>` · `**Date:**` · `**Operator:**` · `**Agent:**` ·
     `**Outcome:**` (one line) · a sibling pointer to the prior history doc.
   - Body: what the operator pointed you at → what landed → decisions →
     **Open threads** (so the next session knows exactly where to resume).
3. **Nav + index.** Add a nav entry under History in `mkdocs.yml` (the nav is
   the exhaustive index). Add a `docs/history/README.md` bullet only if that
   file enumerates every session — some repos keep it curated to the founding
   docs, in which case leave it.
4. **Decisions.** For each non-trivial *operational* decision this arc, append a
   `D-NNNN` entry to `docs/history/0002-decisions.md` (grep-able, referenced by
   id). Structural decisions get an ADR instead (use `new-doc`).
5. **Strike NEXT_STEPS.** In `docs/wip/NEXT_STEPS.md`, mark completed items
   `- [x] ~~text~~ — *done note (date)*`. Strike, never delete — the strikethrough
   is the paper trail.
6. **Version tag.** If the repo's tagging gate is met, suggest
   `git tag v<X>-<arc-slug>` at the closing commit — don't tag unprompted.
7. **Validate.** Run the `docs-preflight` skill.
