---
name: ux-baseline-review
description: Establish a UX baseline for an app (a clickable mockup of every screen, painted by the app's own styles, with real data and guards), review it with independent reviewers, decide with the operator one decision record at a time, and prototype the decisions as before/after variants in a guided review the operator approves round by round. Use when asked to "do a UX review", "inventory every screen", "build a mockup of the app", "prototype this UX change", "walk me through the new UI", or to repeat the UX baseline process in another project.
---

# ux-baseline-review

A playbook for one agent session (with background agents where noted) to take an app from "we
think the UX has problems" to approved, recorded, prototyped changes. It was first run end to end
on a Vue + Tailwind + Capacitor app over 2026-10-31 … 2026-11-03: a baseline, two reviews, 14
decisions and four prototype rounds. Hand it the project's repo path and one line on what the
operator wants reviewed.

## What it produces

1. A **UX baseline**: a clickable mockup of every screen with real data, painted by the app's own
   styles, plus the documents and guards that keep it true.
2. A **review** by independent reviewers, verified and merged into one set of findings, and a
   **plan of action**.
3. **Decisions**, recorded one per decision, and **prototypes** of the structural ones as
   before/after variants, in a guided review the operator approves change by change, round by round.
4. A **record** of each step, and a **change inventory** from which PRDs, specs, RFCs and ADRs are
   written later.

Work with the operator, not for them: decisions are theirs, recorded with their go, and they review.
Ask before anything that installs, publishes, pushes or touches production.

## Phase 0 — orient (bounded: do it, then report)

- Read the repo's AGENTS/CLAUDE files, the UX specs (whatever the project calls them), the PRD or
  product docs (personas, success metrics), and how the app is run and tested.
- Get the app running locally against fixture data. Run the tests once so the starting state is known.
- Report the layout and ask for the target before building anything.

## Phase 1 — see the real app

- **Screenshot inventory** (one background agent): every route and state, phone (e.g. Pixel 7,
  412×915) and desktop (1440×900), signed in with realistic seeded state; an index of what rendered,
  what was empty and why. This is the reference the mockup is compared against.
- **Real data** (one background agent): a compact snapshot from production through read-only tools,
  never invented. Write where every section came from and every gap. **Ask before committing
  production data**, even to a private repo, and record the answer.

## Phase 2 — the living mockup

Rebuild the app as static HTML that is the same app, not a drawing of it:
- Use the app's styling at the source: for Tailwind over CSS tokens, load Tailwind's Play CDN with
  the app's config restated, and a **sync script** that copies the token file, the shared
  stylesheet, the copy file (i18n) and brand assets into the mockup. Port class strings from the
  real templates.
- A small **core** (hash router, state, shell, shared components, `t()` over the real copy), then
  **one agent per area** (home, discovery, player/detail, entities, library, account), each owning
  its own file, porting from the real views and checking itself against the reference screenshots.
- A **review page** (`index.html`): the screen inventory beside a phone frame and a desktop frame.
- **Guards** from day one:
  - a unit test that fails when the mockup's copies of tokens, styles or copy are stale, and when the
    router gains a route with no mockup screen (mutation-test it: it must fail when broken);
  - a render check that opens every inventoried screen at both sizes and fails on a console error,
    horizontal overflow or an empty screen; run it in CI.
- Publish the review page as a private artifact; commit the mockup.

## Phase 3 — the UX documents

- **Journeys**: the 8–12 journeys the app is evaluated against, each with persona, trigger, the path
  through screens and routes, what "good" means (from the product's success metrics), and what to
  look at; plus cross-journey lenses (navigation, layering, vocabulary, density, colour rules, empty
  states, phone vs desktop).
- **UX architecture** (e.g. `UXS-000`): the artefacts and their ids, which one is right where (code =
  what ships, spec = what should; a mismatch is logged and decided, never silently resolved; the
  mockup must match the code), the change flow (input → journey → tried in the mockup → decided →
  built → guarded), and the guards.
- **Feedback log**: every input (operator, customer, design review, spec↔code, mobile) tied to
  journeys and screens, with a status that points at its decision.
- **UX decision records (UXD)**: the UX counterpart of ADRs; one per decision: status, decider,
  answers, rules changed, context, options, decision, consequences, prototype, and a "Review, round
  N" section per prototype round. A decision that changes in substance is **superseded by a new
  record**, not edited. Backfill the dated decisions already buried in the specs into one ledger.
- **UX records (UXR)**: dated, written once: the baseline, each review's findings, each plan, each
  decision session, each prototype round.
- **Change inventory**: one row per change in flight: the decisions behind it, status, surfaces, and
  which PRD / spec / RFC / ADR it will need. This is what the build is planned from.

## Phase 4 — the review

Six independent reviewers in parallel (background agents), each writing its own report:
three on journey groups, one on information architecture (with a sitemap), one on accessibility and
touch (contrast measured on real backgrounds, target sizes with hit areas, semantics from source),
one auditing the design system (foundations, components, patterns, content, spec↔code
contradictions, and a verdict).

Rules that make the findings trustworthy:
- **Reviewers do not read the specs' rationale or the operator's feedback**, so agreement with the
  operator is independent evidence.
- **Every number is measured in CSS px on the rendered page** (getBoundingClientRect, computed
  style), never estimated from a screenshot.
- **Mockup artefacts are not app findings**: when unsure, check the real source.
- **One consolidation agent** verifies every finding against source, specs and data, merges
  duplicates (counting independent sources), classifies by theme / journey / severity / type, lists
  discarded claims with reasons, and writes the "not covered" section.
- **Re-measure on the real app** what was measured only on the mockup.

Optional: a **mobile platform** review (iOS HIG, Android behaviour, the market's apps), from source,
then confirmed on a device or emulator; record what was confirmed, dropped or untestable.

## Phase 5 — plan and decide

- **Plan of action** by track: fix (defects; each bug repro-first), decide (questions with options
  and a recommendation), prototype, design system, platform.
- **Decision session**: ask each question with its options (a multiple-choice prompt,
  recommendation first), record each answer as a UXD, mark the feedback rows decided.
- **Before writing a decision's options, list what the app already has that could do the job.** An
  option set that only offers new surfaces makes the operator choose between wrong answers. (First
  run: "a new full-screen Now Playing beside the episode page" was offered and approved, while the
  episode page already was the app's full player; the prototype built a second player and was
  rejected a round later.)

## Phase 6 — prototypes, guided review, rounds

- First make the mockup match the app again (port what drifted), and re-run the checks.
- A **variant switch**: every proposed change renders behind `proposed()` (decided by the frame's
  name, so one page shows current and proposed side by side), so the current app keeps rendering
  exactly as it is. Keep **state separate per frame**.
- One agent per decision group, each owning its files, each writing a **walkthrough entry** (steps
  with a before hash, an after hash, what changed and why with measured numbers, what to look at,
  open questions). Extend the render check to both variants.
- The review page's **Review mode**: per decision, step by step, current beside proposed at phone or
  desktop size, then a verdict (approve / approve with changes / reject), an answer box per open
  question and a comment, saved to the artifact's database.
- A **Tour mode**: the proposed app alone, screen by screen in the order a listener meets it,
  starting with a new user's onboarding (review hooks in the URL can open each step of a guide),
  each stop listing what is new there and the decisions behind it.
- **Rounds**: each round's entries carry `round: N`; the page shows only the current round and saves
  to its own collection (`verdicts-rN`). After a round: read the verdicts, save the raw JSON in the
  repo, write a UXR and a "Review, round N" section on each decision, update the change inventory,
  then build the next round from the answers. Concepts first; cross-cutting changes (a compact
  scale, density) after the concepts are settled.

**Open questions are in the operator's words.** No internal terms, ids or data-model words ("group",
"snapshot", wire ids); a question the operator cannot answer as asked wastes a round. Re-read every
question before publishing. Where the operator answers "not sure, decide", give a recommendation
with its reason and record it as theirs once accepted.

## Pitfalls met the first time

- Phone frames sized `width: min(432px, 100%)` inside a column that sizes to its content resolve to
  the iframe's default **300 px**: give the frame a definite width and measure it
  (`clientWidth === 412`) at several window widths.
- `file://` pages give every frame its own origin: test a page that reaches into its frames over a
  local HTTP server, and stop it after (the server's own PID, not the wrapper shell's).
- Changing only the hash does not reload a page: a test that moves between modes by hash must reload.
- Give agents **absolute output paths** for screenshots, or they land in the repo.
- One owner per file when agents run in parallel; shared code (the core) is changed by one agent
  only. Agents that share action names across files break each other silently on a rename.
- An artifact belongs to the account that published it: publish from the account the operator
  reviews with, or share it to that account before they review.
- A hand-ported mockup drifts from the app's markup even while token and copy guards pass:
  re-check fidelity before prototyping on it.
- `gh run list --commit <short sha>` matches nothing: use the full SHA. With `cancel-in-progress`
  CI, a second push cancels the first run's long jobs.

## What to hand back

The artifact link (inventory, guided review, tour), the records (baseline, findings, plan,
decisions, rounds), the feedback log and change inventory, what is verified and what is not (with
the command and its output for each "passes"), and the next step waiting on the operator.
