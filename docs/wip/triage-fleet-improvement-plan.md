# Triage fleet: a plan for making it better, by measurement

**Status:** proposal, 2026-11-04; revised 2026-11-05 twice: code evals first, then after an independent review of the
plan (its findings are folded in below and listed at the end). To decide with the operator. **Goal:** fewer missed
problems and less noise reaching the operator from the triage fleet (signal-fleet, Fleet 2), with every change
measured on real decisions before it ships; and, at the same time, a real test of eval-harness (v0.7.2) on a kind of
system it has not been used for: plain code.

## Where it stands

- **Shipped 2026-11-04** (`8213775`, deployed 16:30 UTC): the fleet files the app's failures to load its own code
  instead of dismissing them, and a decision with no answer no longer re-triages silently (F7). On the 65
  owner-labelled Orrery decisions (dataset v2) the combined cost fell from 0.872 to 0.446 (p 0.0011) and missed real
  problems from 0.206 to 0.059. It moved work from escalations to filings: slightly more decisions reach the
  operator (0.749 → 0.785), fewer of them noise (0.445 → 0.373). Measured on Orrery only; the brief serves every
  project.
- **The details:** [`signal-fleet/EVAL-LESSONS-0.6.0.md`](https://github.com/chipi/agentic-ai-homelab/blob/main/signal-fleet/EVAL-LESSONS-0.6.0.md)
  section 7; every idea and its status: [triage fleet opportunities](triage-fleet-opportunities.md).

## What the first round taught, and how it shapes this plan

1. **The brief and the gates are the lever, not the model.** 80+ model arms found none better than production's.
2. **Most of what reaches the operator is decided by code.** The dismiss gate alone, on one pass over v2, stopped 8
   dismissals of real problems and made 7 false alarms; filing decides whether a signal becomes a comment, a
   reopen, a regression or a new issue. None of that code is measured for correctness: its replay gates say
   "nothing regressed", never "how often is it right".
3. **The data decides the answer.** v1 of the dataset leaked hindsight that steered the model; every set this plan
   adds is built from what the fleet could see at decision time, and checked for it before use.
4. **65 decisions separate only large effects in an LLM arm.** Code is deterministic, so one pass has no run-to-run
   noise; the items are still a sample (38 multi-issue clusters for filing), so results carry sampling error.
5. **Every change so far was designed and measured on the same 65 decisions.** Nothing has been confirmed on
   decisions it was not designed from.
6. **Measured before shipped works, and so does writing the prediction down first.**
7. **The operator's actions are gold only where the operator looked.** A dismissal was never looked at; a wrong
   merge became a comment the operator never saw as a separate issue. Each step below says which errors its gold
   can and cannot see.

## Two tracks

**Track A: the fleet's code, as black boxes.** Each piece of deterministic fleet code becomes a system under test in
eval-harness: an adapter feeds it frozen inputs (the signal, and the state it reads: the filed ledger, GitHub's
issue states, the model's recorded decision), takes its decision as the output, and scores it against what the
operator did. No model, no spend. It is also the harness test the operator asked for: code adapters, a system's
external state frozen as part of an item, gold from operator actions, a deterministic system scored.

**Track B: the LLM step.** The brief and the model, measured on unseen decisions before the next change.

## The work, in order

| # | Track | Work | Spend | Operator time |
|---|---|---|---|---|
| 0 | both | move to eval-harness v0.7.2 as released | $0 | done 2026-11-05 |
| 1 | A, B | capture the model's own decision, before the gates | $0 | a push |
| 2 | B | watch the shipped change live, by class and path | $0 | none |
| 3 | A | filing and dedup against gold | $0 | labels on a sample of fuzzy matches |
| 4 | A | the gates against gold | about $0.40 once (one recorded pass), then $0 | none |
| 5 | A | the rest of the fleet's code | $0 | a few labels where no outcome exists |
| 6 | B | a held-out set, split by time | $0 model | labels on disagreements and a calibration sample |
| 7 | B | a tuning round for the brief | about $1 an arm, a budget per round | a go per round |
| 8 | B | the quality of filed issues | later | rubric |

### 0. Move to eval-harness v0.7.2 (done 2026-11-05)

A fresh clone at the tag: both dataset revisions and the dedup set restore and materialize with every hash
verified, `evh validate` passes, the skills install, round r4 reads closed. One harness bug found (a round opened
with `--keep` records no baseline; feedback entry 22).

### 1. Capture the model's own decision, before the gates (prerequisite for 4)

The gates rewrite a decision in place (the intent gate drops the acceptance criteria), so no record held what the
model decided. `b16c220` keeps a copy before the gates (`_pre_gate`) and the capture stores it (`model_decision`);
nothing that decides reads it. **Done when** it is deployed, so every decision from then on carries it.

### 2. Watch the shipped change live, by class and path

- **Not a before/after share.** Three behaviour changes shipped on 11-03/04 (the `assistant-failover` rule, F7, the
  brief), and the week before holds the 11-03 failover-test flood (#133–#137): an overall share attributes to
  nothing.
- **Instead:** every GlitchTip browser error of the class the brief names (failed dynamic import, module script,
  service worker), each with the path it took (filed, dismissed, which gate). Also count the operator's desk:
  issues filed plus escalations, and how many of them the operator closes as noise. **Watch PLAYER:** a browser app
  too, never measured.
- **Scale:** about 3 signals a day, so a week shows that it runs safely, not the size of the effect (that is 6).

### 3. Filing and dedup against gold

- **The black box:** given a signal and the state filing reads (the filed ledger, each linked issue's GitHub state,
  close reason and `duplicateOf`), what `filing.file_or_update` does: comment on issue N, reopen N, file a regression
  of N, follow a duplicate to N, fold into the rollup, file new, stay muted. GitHub is answered from the frozen
  timelines; no write leaves the replay.
- **The data** (`signal-fleet/datasets/freeze_filing.py`, run 2026-11-05): 1,095 filing decisions 2026-07-29 to
  11-05, 506 fleet issues, 145 duplicate links (77 found only in close comments), multi-issue clusters
  podcast_scraper 24, homelab 10, orrery 4. Its second run also fetches every duplicate target and every issue a
  ledger names, fleet-labelled or not.
- **Faithfulness first:** replay from the real ledger snapshot of 2026-10-17 (`reference-filing/filed-2026-10-17.tsv`)
  through 11-05, with the code of that period (the only filing change since is routing, `20d4a92`), and compare each
  action with what GitHub shows happened (the fleet's "Recurred" comments, reopens, new issues). Only once that
  agrees do scores for other code count.
- **Score the grouping, not issue numbers.** A replay that diverges creates issues production never had. Per item,
  pairwise precision and recall: two signals in one gold cluster should land on one issue in the replay, two in
  different gold clusters on different issues.
- **What the gold can see, and what it cannot:**
  - **Missed merges** (one bug, several issues): the operator's duplicate links. One item per cluster: the issue
    the operator kept, everything closed into it, replayed in order.
  - **False merges** (a fuzzy match that buried a different bug): the operator never sees these as a second issue,
    so duplicate links cannot show them. A separate audit: every fleet comment "matched on norm_key / alert_key" in
    the frozen timelines, a sample labelled by the operator (same bug or not).
  - **Look-alike negatives** are chosen by a rule independent of the code under test (same project, overlapping
    window, different gold cluster), never by the code's own keys.
  - **Reopens and regressions** are scored only where the earlier close was a fix; a reopen of an issue closed as
    noise is a triage error, not a filing one.
- **Not scored:** Grafana decisions (the ledger keeps an alert's name, not its labels, so their keys cannot be
  rebuilt; 125 of 1,095), and GlitchTip decisions whose issue no longer exists (reported as a share).
- **One dataset per repo** (podcast_scraper, agentic-ai-homelab, orrery), from one replay: the ledger is shared
  across repos, and the code's keys do not include the repo, so cross-repo matches are checked too.
- **Done when** each repo reports missed merges, false merges (from the audit) and the reopen mix against gold, the
  faithfulness check agrees, and the same check runs in the fleet's deploy gates.

### 4. The gates against gold

- **The black box:** given the model's own decision and the probe answers it had, what the gates (intent, cleanup,
  dismiss, edge-5xx) make of it. Gold: the owner's labels.
- **Inputs:** step 1's `model_decision` for decisions from its deploy on; for the 65 labelled decisions, one recorded
  pass of production's model on the fleet at `b16c220` (the eval-harness output then carries `_pre_gate`), about
  $0.40. After that every gate change is measured offline, at no cost and with no model noise.
- **Scores:** per gate, saves (a real problem stopped from being dismissed) and costs (a right dismissal made a false
  alarm). This is EVAL-LESSONS F1 measured directly, and where the client-noise gate's smaller form is measured first.

### 5. The rest of the fleet's code

The operational classifier, the low-signal rollup, recurrence and the 24-hour re-triage, routing, the stale check.
Each has a pass/fail replay gate; each becomes a black box with outcome labels (an operational state the operator
later filed by hand, a rolled-up signal later promoted, a stale nudge followed by a fix).

### 6. A held-out set, split by time

- **Split now, by time:** decisions after a fixed date D go to the test part, not opened until a candidate is ready;
  everything before D is tuning data. Steps 3–5 and every tuning round read the tuning side only.
- **Source:** the per-decision captures since 2026-10-29 (exact: the answers the model read, no rebuild).
- **Labels:** outcome rules first. A dismissal has no outcome (nobody looked): it stays unlabelled, never "noise".
  The operator decides where the rules and production disagree, plus a random calibration sample of agreements, so
  the gold does not lean toward production.
- **Power:** at about 3 decisions a day the test part grows by about 45 a month, mixed projects. State the smallest
  effect it can detect before opening it; it will detect r4-sized effects, not small ones.

### 7. A tuning round for the brief

- One round per question, its budget fixed first; each arm one change with its `hypothesis:` block committed before
  its run; `arm-smoke` first; k=3; paired tests against the baseline and against what ships; the winner confirmed
  once on step 6's test part; shipped only through the fleet's deploy gates.
- **Candidates:** see [opportunities](triage-fleet-opportunities.md) §1–2 (context up front, the smaller
  client-noise gate, the scored trade-off in the brief, ORRERY-U).

### 8. Later: the quality of filed issues

A filed issue is good when the bug-fix fleet can ship from it (EVAL.md). It needs seeded defects and a judge, and the
bug-fix fleet is paused.

## What to record about eval-harness on the way

For each Track A step: what writing the adapter took, how external state is frozen into an item and replayed, how
gold is made from operator actions, and what the comparison commands do with a deterministic system. Every friction
goes to the eval harness session with a reproduction: [feedback log](eval-harness-feedback-fleet.md).

## Decisions for the operator

1. ~~Deploy step 1~~ — *done 2026-11-05 12:06 UTC: `b23561e`, DEPLOY PASS, all 18 gates.*
2. ~~Step 3's false-merge audit size~~ — *decided 2026-11-05: all of them, not a sample (49 fleet comments matched
   on a fuzzy key across 21 issues, plus any fuzzy merge the replay finds that no comment names), as a yes/no
   sheet with the signal and the issue side by side.*
3. ~~Step 6's split date D~~ — *decided 2026-11-05: D = 2026-11-05 12:06 UTC, step 1's deploy, so every test
   decision also carries the model's own decision; opened once, after about two months (~90 decisions) or earlier
   only to confirm an r4-sized effect.* Still open: how many disagreements plus calibration items per batch.
4. Step 7's budget per round.
5. Whether each Track A eval joins the fleet's deploy gates once it scores against gold.

## What the review of 2026-11-05 changed

An independent review (Fable-class advisor, read-only) of this plan and the fleet docs. Folded in above:
- step 4 could not run on existing records (no pre-gate decision): step 1 added, `b16c220`;
- false merges have no gold in duplicate links: a separate audit, and negatives chosen independently of the code;
- score the grouping (pairwise), not issue numbers;
- faithfulness from the 10-17 ledger snapshot, and the snapshot fetches every issue filing can read;
- reopens scored only after a fix;
- the live check by class and path, with the operator's desk and PLAYER, not a before/after share;
- the shipped change's "escalations fell" restated: work moved from escalations to filings;
- the held-out set split by time now, dismissals unlabelled, a calibration sample, power stated first;
- Grafana decisions excluded from filing scores.
Checked and not confirmed: the concern that r4's labels were correlated (one verdict carried to many decisions);
the 12 decisions the shipped change moved rest on 12 distinct owner verdicts.

## Not covered by this plan

- Models: the plan keeps production's model; a model change would be its own round once step 6 exists.
- The bug-fix fleet (Fleet 1) and the remediation fleet: out of scope here.
- Warnings: the fleet does not see them by design (guide, Known gaps).
- The three X3 assistant items marked "(fleet session)" in NEXT_STEPS: tracked there, not part of this plan.
