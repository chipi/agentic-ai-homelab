# Pillar 1 — Project setup

How I scaffold a new project so an agent (and future-me) can be productive
in it immediately.

> **Status: v0.1 placeholder.** Content lands in v0.2 per
> `docs/wip/NEXT_STEPS.md`. This page will be expanded then.

## What goes here (target state)

A narrative + reference for using `templates/new-project/`:

1. **`AGENTS.md`** — the project file that layers on top of this repo's
   global one. Explains the delete-the-repeats pattern: project-level
   files keep ONLY what's project-specific (stack tables, project-domain
   rules, named ADR anchors).
2. **`Makefile`** — layered gate skeleton (`test-unit` /
   `test-integration` / `ci-fast` / `ci`) extracted from podcast_scraper's
   3586L Makefile. Distilled to ~100L of structural pattern.
3. **`.github/workflows/ci-fast.yml`** — CI that mirrors `make ci-fast`.
4. **`.github/PULL_REQUEST_TEMPLATE.md`** — borrowed from podcast_scraper,
   sanitized.
5. **`docs/{adr,rfc,wip}/README.md`** — same conventions as this repo.
6. **`.pre-commit-config.yaml`** — minimal baseline (formatters + linters +
   secrets scanner).

## Quick reference (v0.1 — until templates land)

Even before the templates are filled in, the conventions are clear from
this repo:

- Single global `AGENTS.md` at `~/.config/opencode/` covers universal
  rules. Per-project files add project-specifics only.
- ADRs go in `docs/adr/ADR-NNNN-slug.md`. RFCs in `docs/rfc/`. Both
  numbered sequentially, never renumbered.
- WIP notes in `docs/wip/`, never in `/tmp` or `docs/analysis/`.
- Each session writes to `docs/history/NNNN-slug.md` if it does
  substantive work. Decisions append to `docs/history/0002-decisions.md`
  (or the project's equivalent).

## Open in v0.1

- [ ] All the file lists above (see `docs/wip/NEXT_STEPS.md` for full
      v0.2 task list).

## Inspirations

- podcast_scraper `Makefile` — layered targets, exit-code reporting.
- orrery `AGENTS.md` — "stack table" pattern locking decisions to ADRs.
- chemigram `AGENTS.md` — three foundational disciplines pattern.
- oceancanvas `AGENTS.md` — constraint-honoring doctrine.
