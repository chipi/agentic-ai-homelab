# ADR-0002 — Root + per-folder AGENTS.md split

**Status:** Accepted
**Date:** 2026-07-01
**ctx src:** see `docs/history/0004-agent-config-and-skills.md`

## ctx

The repo's agent rules lived in a single root `AGENTS.md` (~92 lines) plus two
scoped files (`infra/dgx/`, `provider-bakeoff/`). The root mixed truly repo-wide
rules (`.env` hygiene, the override hierarchy) with folder-specific ones (the
mkdocs strict gate → docs; run-composes-in-place → infra). The same monolith
pattern is far worse in sibling repos (orrery 871 lines, podcast_scraper 802) and
needs a proven shape here before replicating.

## Decision

Root `AGENTS.md` carries **only repo-wide** rules + the scoped-file table + the
override hierarchy. Folder-specific rules move into per-folder `AGENTS.md` next to
the code they govern (`docs/`, `infra/`, `infra/vllm/`, plus the pre-existing
`infra/dgx/`, `provider-bakeoff/`). `CLAUDE.md` stays a thin `@AGENTS.md` import.
More-specific folder wins. A scoped `AGENTS.md` living under `docs/` is excluded
from the published site (`exclude_docs`) so internal rules don't leak onto the
public pages.

## Consequences

- **Positive:** root shrank 92 → 55 lines; each rule lives once, next to its
  code; the pattern is now a worked example (codified in the `scoped-agents`
  skill) ready to replicate to the monolith repos.
- **Negative:** more files to open to see "all rules"; the scoped table must be
  kept in sync as folders gain or lose rules.
- **Neutral:** the load-bearing principle is unchanged — `AGENTS.md` is the source
  of truth, `CLAUDE.md` a thin layer.

## Alternatives considered

- **Codify the pattern as a template only, minimal edits here** — rejected: the
  repo is the reference; a fuller worked example beats prose.
- **Skip this repo, split the monoliths directly** — rejected: prove the shape on
  the small, clean repo first, then replicate to orrery / podcast_scraper.
- **Leave the 92-line monolith** — rejected: it already mixed altitudes, and the
  split had to be modeled somewhere before touching the big repos.
