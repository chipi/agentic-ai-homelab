# Module README guide — small tactical docs next to code

For agents (and humans) writing module-map READMEs: short, local docs that
sit next to the code they describe and carry the knowledge the code alone
cannot state. They serve everyone equally — feature work, maintenance,
humans, agents.

Evidence this pays: in the bug-fix bake-off (2026-07-23), an agent given a
vague ticket fixed the wrong look-alike function every time; adding a
15-line module map flipped the same ticket to a correct fix. Attempts
without the local context cost 2–4.5× the tokens *and* failed.

## When to write one

Any of these triggers is enough:

- The area has **two or more look-alike implementations** (same concept,
  different consumers) and nothing states which serves what.
- A **convention** exists that code doesn't declare: units, coordinate
  frames, Earth/physics model, taxonomy or folding rules, precision policy.
- A fix or review **went to the wrong file/layer** in this area — that miss
  is the signal the local knowledge is undocumented.
- A folder has grown enough files that "what lives where" needs answering.

## Where it lives

`README.md` inside the module's folder. For a single top-level file,
`<name>.README.md` next to it. Always adjacent to the code — it must move,
version, and get reviewed with the code it describes.

## What goes in (10–25 lines, all of these that apply)

1. **One line: what this area is** and which route/feature consumes it.
2. **Ownership map** — file/function → responsibility → consumer.
   "`heliocentricSpeed()` is the speed shown on the fly HUD."
3. **Disambiguation** — name the look-alikes and when to use which.
   "`visViva()` in orbital.ts is the generic helper used by rendering; HUD
   physics lives here."
4. **Local conventions & invariants** — units, frames, models, taxonomy
   rules. "Earth model is the WGS84 ellipsoid, not a sphere."
   "Hosting is not sourcing — Commons-hosted images credit their agency."
5. **Contracts callers rely on** — "endpoints stay pinned to the transfer
   points; the shape derives from the mission parameters."
6. **Pointers up** — one line each to the ADR/RFC/architecture doc that
   holds the *why*. Link, never summarize: local README = the *what/which/
   who-owns*; big docs = the *why*. If the why isn't written anywhere,
   flag that gap instead of inventing it here.

## What stays out

- **No bug/ticket/PR references, no history** — "added for #123" rots.
- **No API reference** — signatures and types live in the code.
- **No roadmap or strategy** — belongs in the bigger docs you link to.
- **Nothing the code already says clearly** — document the non-obvious only.
- Hard cap ~25 lines. If you need more, the area likely needs splitting —
  or the content is really an ADR.

Voice: a maintainer leaving notes for the next person. Present tense.
The README states the module's *intended* conventions — if code is found
contradicting the doc, that divergence is a bug to raise, not silently
paper over (doc-vs-code divergence rule).

## Validating a module README

Tier 1 — **review checklist** (any repo, 2 minutes). A reviewer who has
never seen the area must be able to answer, from the README alone:

- Given a symptom in this area, which file/function do I touch?
- If there are look-alikes, which one — and why not the other?
- What convention/invariant must my change respect?

Plus mechanics: ≤25 lines · zero bug references · links to big docs rather
than copies of them. Any miss → rewrite.

Tier 2 — **localization quiz** (cheap, empirical). Give an agent a vague but
honest bug description for this area, the repo, and the question "which
file/function would you change, and what must the fix respect?" — once
WITHOUT the README, once WITH it. The README is load-bearing iff the
with-doc answer names the right target and constraints when the without-doc
answer did not. No test harness or oracle needed.

Tier 3 — **flip test** (gold standard, needs a replay harness). Replay a
real past bug in the area from a **normalized** ticket (symptom + expected
behavior stated), with and without the README injected. Load-bearing iff the
doc flips FAIL→PASS or measurably cuts turns/cost. Do NOT run this with a
garbage ticket and expect a verdict flip — measured 2026-07-23: docs flip
*localization* (right file found, 3/4) but never the *verdict* (0/4) when
the ticket omits what "fixed" means. Acceptance criteria are the ticket's
job; the doc's job is topology. Judge docs on the localization signal.

Written-with-hindsight caveat: a README authored by someone who knows a
specific bug can smuggle the answer. Keep to module-intent facts (ownership,
conventions, contracts) a maintainer would write regardless; never describe
any bug's symptom or fix.
