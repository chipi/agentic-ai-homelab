# WIP — work in progress

Notes for work that is still open: plans, runbooks not yet run, investigations. Everything
here is tracked in git, so it's findable and diffable.

## Files

- `NEXT_STEPS.md` — the live punch list. Read it when picking what to work on next.
- `DGX-SPARK-KNOWN-HARDWARE-ISSUE.md` — the DGX hard power-off: evidence, remediation, RMA
  path. Promote to `docs/recipes/` once its open items close.
- `colima-vcpu-8-to-4-runbook.md` — resize the mini's VM and turn Spotlight off. Not run yet.
- `tailscale-exit-node-mini.md` — the mini as an NL exit node. Not run yet.
- `otel-pipeline-end-to-end.md` — telemetry map, gaps and the remaining plan (issue #99).

## Closing a note

A note is closed when its work ships or is dropped (decision D-0016). In the same change:

1. Fold anything someone will need again into the living doc where they'd look for it:
   a recipe, an ADR, a README, the signal-fleet guide.
2. Move any item still open into `NEXT_STEPS.md`.
3. Repoint every link to the note (`git grep <name>`).
4. Delete the note, and record it in a `docs/history/` entry (what it was, how it ended,
   where its lasting parts went). Its full text stays in git history.

Handovers between sessions count: when the receiving session has acted on one, close it.
A note untouched for a quarter is either still open (say so in `NEXT_STEPS.md`) or closed.

| Lasting content goes to | When |
|---|---|
| `docs/adr/` | the decision is structural and final |
| `docs/rfc/` | it needs a proposal-and-review process first |
| `docs/recipes/` | it is an operational how-to or runbook |
| `docs/reading/` | it is a curated external reading list |
| `docs/history/` | it is the record of how something happened |
| a component's README | it is about that component |

## Convention

- Name notes for their intent, not their date (`colima-vcpu-8-to-4-runbook.md`).
- State the promotion target at the top of each note.
