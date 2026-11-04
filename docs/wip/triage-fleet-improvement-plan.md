# Triage fleet: a plan for making it better, by measurement

**Status:** proposal, 2026-11-04 (fleet session), to decide with the operator. **Goal:** fewer missed problems and
fewer escalations on the operator's desk from the triage fleet (signal-fleet, Fleet 2), with every change measured
on real decisions before it ships, using eval-harness and improving it where it falls short.

## Where it stands

- **Shipped 2026-11-04** (`8213775`, deployed 16:30 UTC): the fleet files the app's failures to load its own code
  instead of dismissing them, and a decision with no answer no longer re-triages silently (F7). On the 65
  owner-labelled Orrery decisions (dataset v2) the combined cost fell from 0.872 to 0.446 (p 0.0011) and escalations
  from 0.292 to 0.118; no live decision has used it yet.
- **The details:** [`signal-fleet/EVAL-LESSONS-0.6.0.md`](https://github.com/chipi/agentic-ai-homelab/blob/main/signal-fleet/EVAL-LESSONS-0.6.0.md)
  section 7; the open items: [NEXT_STEPS](NEXT_STEPS.md), Fleets, "(fleet session)".

## What the first round taught, and how it shapes this plan

1. **The brief and the gates are the lever, not the model.** 80+ model arms found none better than production's.
2. **The data decides the answer.** v1 of the dataset leaked hindsight that steered the model; every set this plan
   adds is built from what the fleet could see at decision time, and checked for it before use.
3. **65 decisions separate only large effects.** One change (−0.43) was clear; two smaller ones were not. Most
   prompt edits will be smaller.
4. **Every change so far was designed and measured on the same 65 decisions.** Nothing has been confirmed on
   decisions it was not designed from.
5. **Measured before shipped works, and so does writing the prediction down first:** it showed the third arm
   failing in a way its numbers alone hid (four real problems turning into cleanup).
6. **Two stages are not measured at all:** the filing stage (dedup, reopen, regression) and anything outside Orrery
   browser errors (server-side errors, LiteLLM, Grafana alerts).

## The work, in order

| # | Work | Spend | Operator time | Answers |
|---|---|---|---|---|
| W1 | See the shipped change live | $0 | none | did it help in production? |
| W2 | A held-out set across projects | $0 model | labels on the disagreements only | does a change hold on decisions it was not designed from, and outside Orrery? |
| W3 | Dedup as a correctness eval | $0 | none (your duplicate links are the labels) | does the filing stage merge what you merge, and keep apart what you keep apart? |
| W4 | A tuning loop for the brief and the gates | about $1 an arm, a budget per round | a go per round | which next change is worth shipping? |
| W5 | The quality of filed issues | judge spend, later | rubric | does a filed issue lead to a fix? |

### W1. See the shipped change live

- From the first decisions carrying prompt `219b34bf`: the escalation share and the dismiss/file mix for the week
  after the deploy against the week before, per project. Read each escalation and each own-code-load filing.
- In eval-harness: `evh capture --since-capture` over the fleet's decisions makes the before and the after two
  captures, comparable as datasets.
- **Done when:** a week of decisions after the deploy is read and the numbers are in EVAL-LESSONS section 7.

### W2. A held-out set across projects

- **Source:** the per-decision probe captures on the mini since 2026-10-29 (`~/signal-fleet/results/probes/`,
  75 on 2026-11-04, about 15 Orrery, the rest LiteLLM, the podcast pipeline, Grafana alerts). These are exact: the
  answers the model read, no rebuild, no hindsight.
- **Labels:** eval-harness's outcome rules first (fixed / noise / duplicate from the operator's close comments, seen
  again or not); the operator decides only where the rules and production disagree.
- **Use:** split once (`evh dataset-split`) into a tuning part and a test part. Tune on the 65 Orrery decisions plus
  the tuning part; confirm a candidate once on the test part, never tune on it.
- **What it adds:** the first measurement of the gates on server-side signals, and a fair test of the parked
  client-noise gate (`01226ca`).
- **Done when:** a labelled dataset of at least about 100 exact decisions exists, with its split recorded.

### W3. Dedup as a correctness eval

- **Today** eval-harness's `signal-fleet-dedup` (100 signals) is a regression guard: it checks that four per-signal
  functions answer as they did at `f07efa9`. On 2026-11-04 it passed on the shipped `8213775` (key_match 1.0,
  class_match 1.0, run `dedup_guard_8213775_v1_20261104T211540Z`). It cannot say whether a merge is right, and its
  data never reaches parts of the code: no LiteLLM signal (so `assistant-failover` changed unnoticed), 0 test
  signals, no Grafana alert, 89 of 100 from the podcast pipeline.
- **Gold labels already exist:** every issue the operator closed as a duplicate (GitHub's `duplicateOf`) says "these
  merge"; every pair kept apart says "these do not". The fleet's filed ledger maps each issue to its signals.
- **Make it:** score pairs, not signals: missed merges (one bug, several issues: fan-out) and false merges (a
  fuzzy match that buries a different bug), against those links. Replay the whole lookup (`filing.ledger_lookup`
  over fingerprint, group key, normalized key, alert key), not only `normalized_key`. Add the classes the data
  lacks.
- **Done when:** the dedup example reports missed and false merges against gold, and runs in the fleet's deploy
  gates as well as in eval-harness.

### W4. A tuning loop for the brief and the gates

- **The loop:** one round per question, a budget fixed before it starts; each arm one change, with its prediction in
  the config's `hypothesis:` block (eval-harness 0.7.0) before its run; k=3; paired tests against the baseline and
  against what ships; tune on the tuning data, confirm the winner once on W2's test part; ship only what passes
  both, through the fleet's deploy gates.
- **Candidates already found, for the first round:**
  - the client-noise gate, smaller: the gate and the extension and old-browser classes, without the
    mirrored-bundle sentence that turned CSS-preload decisions into cleanup;
  - telling the model the trade-off it is scored on (a missed problem costs five false alarms; EVAL-LESSONS
    suggestion 6), instead of "escalate at most 1 in 20";
  - `event_detail` as the first look for a GlitchTip signal (F4: the model reads 1 or 2 of its 3 probes);
  - ORRERY-U, the one decision the shipped change made worse.
- **Spend:** about $1 an arm at k=3 on 65 items (more with W2's items); a round of four arms about $4–6.

### W5. Later: the quality of filed issues

EVAL.md's own bar: a filed issue is good when the bug-fix fleet can ship from it. It needs seeded defects (a real
bug replayed at its fix's parent commit) and a judge; more setup than W1–W4, and the bug-fix fleet is paused.

## Parked, with why

- **A stale-client rule in filing:** 3 of the fleet's 63 real reopens and regressions; GlitchTip cannot tell which
  build was live, so it needs deploy history. Not worth it at that size.
- **The client-noise gate as measured:** not better than what ships; its smaller form is W4's first candidate.

## Decisions for the operator

1. The order: W1 and W3 now (no spend), W2 next (your labelling time on disagreements), W4 after W2.
2. W2's size and labelling: how many disagreements you are willing to label per batch.
3. W4's budget per round.
4. Whether W3's dedup eval joins the fleet's deploy gates once it scores against gold.

## Not covered by this plan

- Models: the plan keeps production's model; a model change would be its own round once W2 exists.
- The bug-fix fleet (Fleet 1) and the remediation fleet: out of scope here.
- Warnings: the fleet does not see them by design (guide, Known gaps); no eval can measure what it never receives.
- The three X3 assistant items marked "(fleet session)" in NEXT_STEPS: tracked there, not part of this plan.
