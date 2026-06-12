# History — session continuity log

Append-only log of working sessions on this repo, plus a parallel decision
log.

## Files

- `0001-genesis.md` — the founding session that produced v0.1. The most
  important doc here; future sessions should read it first.
- `0002-decisions.md` — append-only decision log (D-NNNN entries). Newer
  decisions at the top.

## Convention

- One file per session named `NNNN-<short-slug>.md`.
- Sessions append a section to `0002-decisions.md` for each non-trivial
  decision made (anything you'd want to find later via grep).
- Decisions get IDs (`D-NNNN`) so they can be referenced from code, ADRs,
  or other sessions.
- Never edit a past session doc — write a new one referencing it.
- Don't conflate this with `docs/adr/`. ADRs are *architectural* decisions
  that govern the repo's design. The decision log here captures
  *operational* decisions (port choices, image picks, defer-vs-do calls).
  When a decision is structural enough to need an ADR, write the ADR and
  link to it from the decision-log entry.

## When to write a new session entry

If your session:
- Adds a new pillar or restructures the repo
- Makes 3+ decisions worth logging
- Changes scope or direction
- Resolves an open thread from a prior session

then write a new `NNNN-<slug>.md` summarizing the session and append
relevant decisions to `0002-decisions.md`.

If your session is just "small fix" / "typo" / "rename one file" — no
history entry needed, the commit message is enough.
