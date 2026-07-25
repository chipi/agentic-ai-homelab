# Reporter-oracle facts files — authoring protocol

One file per bug family (`orrery-<bug>.md`), written from the golden fix's
knowledge, in the reporter's voice. Injected only by `reporter_answer.sh`
(eval-side); production has a human here.

## Coverage checklist (v3 k=3 lesson, session 3h)

A facts file is complete only if it can answer, **in substance**, every
question a triager plausibly asks. 6/15 chains died on "reporter rounds
exhausted" and one fixable bug was *rejected* because the facts couldn't
answer definition-of-done questions. Before a facts file is used, check it
answers:

1. **What is wrong** — the symptom, in behavior terms.
2. **What correct looks like** — the expected behavior, stated BOTH as
   prose AND as an explicit "**if asked 'definition of done', my answer
   is:**" block (triagers phrase this many ways; the answerer matches on
   substance but the substance must exist).
3. **Domain facts the repo can't supply** — mappings, constants, design
   decisions (the maintainer's call among coherent alternatives).
4. **Scope boundary / catch-all** — what is explicitly NOT part of the fix
   ("everything I didn't name stays as-is"). Without this, the triager's
   enumeration questions ("what about X? and Y?") all come back
   I-don't-know and the ticket dies or gets rejected.
5. **What the reporter legitimately does NOT know** — exact observed
   values, repro timestamps, code locations. "I don't know" on these is
   realistic and correct — never backfill them from the golden fix's
   *implementation*.

## Hard rules

- **No localization.** Never name files, functions, or code structure —
  reporters don't know them, and leaking them flattens the measurement
  (BAKEOFF §6.1: L1 boundary).
- Data-level identifiers ARE allowed (section ids, WGS84 constants,
  physical values) — they're acceptance criteria, same rule as L1
  authoring.
- Facts come from the golden fix's *intent*, never its *diff*.
