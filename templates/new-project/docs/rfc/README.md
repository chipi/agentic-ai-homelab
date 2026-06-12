# RFCs — proposals under review

Proposals that need a "should we?" review before becoming decisions.

Distinct from `docs/adr/` (architecture decisions that have been
*accepted*). An RFC moves to:
- An ADR if accepted (structural decision).
- A decision-log entry if accepted at operational level.
- Deletion if rejected (with a brief rationale appended to the closing
  commit).

## Format

`RFC-NNNN-short-slug.md`. Numbered sequentially.

Required sections:
- **Status** (Proposed / Under review / Accepted → ADR-NNNN / Rejected)
- **Motivation** — what problem we're trying to solve
- **Proposal** — what we're suggesting
- **Open questions** — what's not yet resolved
- **Alternatives considered**
- **Discussion** — append-only thread of considerations (date-stamped)

## When to write an RFC vs going straight to ADR

- ADR: the operator has decided. Document the decision and move on.
- RFC: the operator wants to think about it / get input / sleep on it.
  When ready, promote to ADR.

For a single-operator project, most decisions become ADRs directly. RFC is
for the cases where you want to write down the reasoning before you've
landed on an answer.

## Index

No RFCs yet.
