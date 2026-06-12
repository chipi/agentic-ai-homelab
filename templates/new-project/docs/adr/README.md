# ADRs — architecture decision records

Decisions that shape the *structure* of this project: what's in scope, how
it's organized, what conventions govern it.

Distinct from `docs/history/0NNN-decisions.md` if you keep one (operational
decisions — what tool, what port, what tag). The rule of thumb:

- **ADR**: would a future contributor need to know this to make a
  consistent change? → ADR.
- **Decision log**: was this a one-shot choice with a clear context? →
  log entry.

## Format

`ADR-NNNN-short-slug.md`. Numbered sequentially, never renumbered.

Required sections:
- **Status** (Proposed / Accepted / Superseded by ADR-XXXX)
- **Context** — what problem we're solving
- **Decision** — what we're doing
- **Consequences** — positive / negative / neutral
- **Alternatives considered** — what else we looked at, why each was
  rejected
- **References** — cross-links

Keep it short. ADRs that grow past 200 lines usually need to be split.

## When to write one

- Adopting a new framework / language / runtime.
- Schema changes that affect downstream consumers.
- Breaking API changes.
- Picking a license.
- Adopting a new convention that affects multiple files.
- Reversing a prior ADR (write a new one that supersedes it).

## When NOT to write one

- Bug fixes, typos, dependency bumps.
- Choosing a tool/library for ONE concrete use case (decision log instead).
- Anything that affects only a single file's content.

## Index

No ADRs yet.
