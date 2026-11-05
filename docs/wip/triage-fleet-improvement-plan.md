# Triage fleet: a plan for making it better, by measurement

**Status:** proposal, 2026-11-04, revised 2026-11-05 (fleet session), to decide with the operator. **Goal:** fewer
missed problems and fewer escalations on the operator's desk from the triage fleet (signal-fleet, Fleet 2), with
every change measured on real decisions before it ships; and, at the same time, a real test of eval-harness
(v0.7.2) on a kind of system it has not been used for: plain code.

## Where it stands

- **Shipped 2026-11-04** (`8213775`, deployed 16:30 UTC): the fleet files the app's failures to load its own code
  instead of dismissing them, and a decision with no answer no longer re-triages silently (F7). On the 65
  owner-labelled Orrery decisions (dataset v2) the combined cost fell from 0.872 to 0.446 (p 0.0011) and escalations
  from 0.292 to 0.118; no live decision has used it yet.
- **The details:** [`signal-fleet/EVAL-LESSONS-0.6.0.md`](https://github.com/chipi/agentic-ai-homelab/blob/main/signal-fleet/EVAL-LESSONS-0.6.0.md)
  section 7; the open items: [NEXT_STEPS](NEXT_STEPS.md), Fleets, "(fleet session)".

## What the first round taught, and how it shapes this plan

1. **The brief and the gates are the lever, not the model.** 80+ model arms found none better than production's.
2. **Most of what reaches the operator is decided by code, not by the model.** The dismiss gate alone saved 12
   real problems and cost 8 false alarms on v1; filing decides whether a signal becomes a comment, a reopen, a
   regression or a new issue. None of that code is measured for correctness: its replay gates
   (`signal-fleet/mvp/eval_*_replay.py`) say "nothing regressed", never "how often is it right".
3. **The data decides the answer.** v1 of the dataset leaked hindsight that steered the model; every set this plan
   adds is built from what the fleet could see at decision time, and checked for it before use.
4. **65 decisions separate only large effects in an LLM arm.** Code is deterministic: one pass is exact, and a run
   costs nothing.
5. **Every change so far was designed and measured on the same 65 decisions.** Nothing has been confirmed on
   decisions it was not designed from.
6. **Measured before shipped works, and so does writing the prediction down first.**

## Two tracks

**Track A: the fleet's code, as black boxes.** Each piece of deterministic fleet code becomes a system under test in
eval-harness: an adapter feeds it frozen inputs (the signal, and the state it reads: the filed ledger, GitHub's
issue states, the model's recorded decision), takes its decision as the output, and scores it against what the
operator did. No model, no spend, exact. It is also the harness test the operator asked for: writing code adapters,
freezing a system's external state as part of an item, gold from operator actions, and scoring a deterministic
system, which eval-harness has done only once (the dedup regression guard, against its own past output).

**Track B: the LLM step.** The brief and the model, measured on unseen decisions before the next change.

## The work, in order

| # | Track | Work | Spend | Operator time |
|---|---|---|---|---|
| 0 | both | move to eval-harness v0.7.2 as released | $0 | none |
| 1 | B | start the live check of the shipped change (read it after a week) | $0 | none |
| 2 | A | dedup and filing against gold | $0 | none: the duplicate links are the labels |
| 3 | A | the gates against gold | $0 | none beyond labels that exist |
| 4 | A | the other code: operational classifier, low-signal rollup, recurrence, routing, stale check | $0 | a few labels where no outcome exists |
| 5 | B | a held-out set across projects | $0 model | labels on the disagreements only |
| 6 | B | a tuning round for the brief | about $1 an arm, a budget per round | a go per round |
| 7 | B | the quality of filed issues | later | rubric |

### 0. Move to eval-harness v0.7.2

- A fresh install from the tag (`evaluation-harness @ git+https://github.com/chipi/eval-harness@v0.7.2#subdirectory=harness`),
  in a clean checkout: `fetch.py` restores both dataset revisions, round r4's runs validate, `skills-install` and
  the project `AGENTS.md` are what an agent starts from.
- **Done when:** r4's data and runs restore and `evh validate` passes on the released version, not on a local branch.

### 1. Start the live check (read after a week)

- From the first decisions carrying prompt `219b34bf`: the escalation share and the dismiss/file mix for the week
  after the deploy against the week before, per project, each escalation read. `evh capture --since-capture` makes
  the before and the after two captures.
- **Done when:** a week after the deploy is read and its numbers are in EVAL-LESSONS section 7.

### 2. Dedup and filing against gold (Track A, first)

- **The black box:** given a new signal and the state filing reads (the filed ledger rows, each linked issue's
  GitHub state, close reason and `duplicateOf`), what does `filing.file_or_update` do: comment on issue N, reopen N,
  file a regression of N, follow a duplicate to N, fold into the rollup, file new, stay muted. The adapter replays it
  with GitHub stubbed from the frozen state; no write leaves the replay.
- **Gold, already recorded by the operator:** an issue closed as a duplicate of N means its signals belonged on N;
  issues kept apart mean their signals did not; a reopen the operator closed again without a fix is a reopen that
  should not have happened.
- **Scores:** missed merges (one bug, several issues: fan-out), false merges (a fuzzy match that buries a different
  bug), and the reopen/regression mix against what the operator did next.
- **Today's guard stays:** `signal-fleet-dedup` passed on `8213775` (key_match 1.0, class_match 1.0, run
  `dedup_guard_8213775_v1_20261104T211540Z`). Its data has gaps this step fills: no LiteLLM signal (so
  `assistant-failover` changed unnoticed), 0 test signals, no Grafana alert, 89 of 100 from the podcast pipeline.
- **Done when:** the filing stage reports missed and false merges against gold in eval-harness, and the same check
  runs in the fleet's deploy gates.

### 3. The gates against gold (Track A)

- **The black box:** given the model's recorded decision and the probe answers it had, what do the gates make of
  it (intent, cleanup, dismiss, edge-5xx)? Production records both the model's choice and the gate's verdict
  (`gates`, and a reason that starts "dismiss gate: …" when the gate overruled it).
- **Gold:** the owner's labels on the 65 decisions now, the held-out set's labels later (step 5).
- **Scores:** per gate, how often it saved a real problem and how often it made a false alarm; this is EVAL-LESSONS
  F1 measured directly, without a model in the loop.
- **Done when:** each gate's saves and costs are a number per dataset, and a gate change can be measured here before
  any LLM arm is spent on it.

### 4. The rest of the fleet's code (Track A)

The operational classifier (states never filed: cost cap, rate limits, failover), the low-signal rollup, recurrence
and the 24-hour re-triage, reopen against regression, routing to the right repository, the stale check. Each has a
pass/fail replay gate today; each becomes a black box with outcome labels (an operational state the operator later
filed by hand, a rolled-up signal later promoted, a stale nudge followed by a fix).

### 5. A held-out set across projects (Track B)

- **Source:** the per-decision probe captures on the mini since 2026-10-29 (`~/signal-fleet/results/probes/`, 75 on
  2026-11-04, about 15 Orrery, the rest LiteLLM, the podcast pipeline, Grafana alerts): the answers the model read,
  no rebuild, no hindsight.
- **Labels:** eval-harness's outcome rules first; the operator decides only where the rules and production disagree.
- **Use:** split once into a tuning part and a test part; confirm a candidate once on the test part, never tune on
  it. It also gives step 3 its first server-side signals.

### 6. A tuning round for the brief (Track B)

- One round per question, its budget fixed first; each arm one change with its `hypothesis:` block committed before
  its run; `arm-smoke` before each paid run; k=3; paired tests against the baseline and against what ships; the
  winner confirmed once on step 5's test part; shipped only through the fleet's deploy gates.
- **Candidates already found:** the client-noise gate in a smaller form (gate and two classes, no mirrored-bundle
  sentence; measurable first in step 3), telling the model the trade-off it is scored on (EVAL-LESSONS suggestion
  6), `event_detail` as the first look (F4), ORRERY-U.

### 7. Later: the quality of filed issues

A filed issue is good when the bug-fix fleet can ship from it (EVAL.md). It needs seeded defects and a judge, and the
bug-fix fleet is paused.

## What to record about eval-harness on the way

For each Track A step, what it took to write the adapter (the interface, what the harness assumes about a system),
how external state is frozen into an item and replayed, how gold is made from operator actions (`label-from-capture`
rules), and what the scoring and comparison commands do with a deterministic system (one pass, no noise). Every
friction and question goes to the eval harness session with a reproduction, for 0.8.0.

## Parked, with why

- **A stale-client rule in filing:** 3 of the fleet's 63 real reopens and regressions; GlitchTip cannot tell which
  build was live, so it needs deploy history. Step 2's reopen scores will show whether it is worth more than that.
- **The client-noise gate as measured:** not better than what ships; its smaller form is step 6's first candidate,
  with its gate part measured in step 3 first.

## Decisions for the operator

1. The order: steps 0 to 4 now (no spend, no operator time beyond a few labels), 5 and 6 after.
2. Step 5's labelling: how many disagreements you are willing to label per batch.
3. Step 6's budget per round.
4. Whether each Track A eval joins the fleet's deploy gates once it scores against gold.

## Not covered by this plan

- Models: the plan keeps production's model; a model change would be its own round once step 5 exists.
- The bug-fix fleet (Fleet 1) and the remediation fleet: out of scope here.
- Warnings: the fleet does not see them by design (guide, Known gaps).
- The three X3 assistant items marked "(fleet session)" in NEXT_STEPS: tracked there, not part of this plan.
