# Triage fleet: opportunities to make it better

**What this is:** every idea for improving the triage fleet (signal-fleet, Fleet 2) that came up in the evaluation
work of 2026-11-04 and -05, in one list: the eval-harness findings handed over, the plan discussions, and the side
questions. Each says what it is, what is known about it, its status, and where it sits in the
[improvement plan](triage-fleet-improvement-plan.md) (its steps 1–7). The plan decides the order; this page keeps the
options, so none is lost.

**Status words:** **shipped** (deployed), **measured** (an eval ran; the result is given), **ruled out** (data says
no, for now), **candidate** (worth measuring; not yet), **open** (known, not yet worked on).

## 1. What the model is told (the brief)

| Idea | What is known | Status | Plan |
|---|---|---|---|
| The app failing to load its own code (dynamic import, service worker) is a real problem, not a transient | `triage_cost` 0.872 → 0.446 (p 0.0011), real problems missed 0.206 → 0.059; escalations 0.292 → 0.118 but filings 0.456 → 0.667, so slightly more reaches the operator (0.749 → 0.785) with less of it noise (0.445 → 0.373) (round r4, v2, Orrery only) | **shipped** 2026-11-04 (`a7dfcd2`) | done; step 2 watches it live |
| Name the client noise the operator closes (injected extension code, a browser too old for the bundle, a mirrored bundle) | moves the model (its false alarms 0.376 → 0.226, p 0.049), not the fleet: the dismiss gate escalates the new dismissals | **measured**, parked (`13856f9`) | step 7, with the gate change below |
| Show the model the release's age (EVAL-LESSONS F3) | does not separate the cases: a real error and a noise one carry the same build age; what differs is whether a fix had shipped | **ruled out** as designed | — |
| `event_detail` as the default first look (F4) | it is already the usual first probe (144 of 192 first probes on v2) | candidate, small | step 7 |
| Tell the model the trade-off it is scored on (a miss costs five false alarms) instead of "escalate at most 1 in 20" (EVAL-LESSONS suggestion 6) | not measured | candidate | step 7 |
| Recheck the "1 in 20" escalation target against what the gates produce (suggestion 5) | the dismiss gate alone produces about 17% escalations | candidate (wording) | step 7 |
| ORRERY-U: the one decision the shipped change made worse (noise now filed) | 3 of 3 passes filed | open | step 7 |
| The wording of "not available" probe answers may move the model (ORRERY-S dismissed 3/3 on v2, 1/3 on v1) | not separated from the model's pass-to-pass noise at k=3 | open | step 6 (exact data has no such answers) |

## 2. How the model works (structure)

| Idea | What is known | Status | Plan |
|---|---|---|---|
| Context up front: code gathers the event, logs and trace before the model decides, instead of the model asking | the model asks 1–2 of 3 probes; logs and traces are rarely asked for (6 and 19 of 195 decisions); only the exact captures since 2026-10-29 can measure it | candidate | step 7, on step 6's held-out set |
| Raise the probe cap from 3 to 4 or 5 | the cap binds on 17% of decisions; those decided right as often as the rest (0.67), the weakest are those that stopped at 2 (0.47): judgment, not budget | **ruled out** for now | — |
| A chain of steps: gather (code) → classify (LLM, short prompt) → gates (code) → write the issue (LLM, only when filing) | each step becomes its own black box with its own eval; costs more calls and compounding errors; no library needed (plain functions in `triage.py`) | candidate | step 7 first measures "gather + classify" against today's single step |
| A cheaper model for a classify-only step | no model beat production's on today's prompt; a split prompt is a different question | candidate, after the chain | step 7 |

## 3. The fleet's code (gates, filing, the rest)

| Idea | What is known | Status | Plan |
|---|---|---|---|
| Let the dismiss gate take a deterministic client-noise marker as corroboration (F1) | the targeted noise became right dismissals 3/3; on top of what ships not better (p 0.48), escalations worse; 4 real problems turned cleanup/dismiss in 1 of 3 passes | **measured**, parked (`01226ca`, branch `fleet/noise-gate`) | step 4 measures the gate part alone; step 7 a smaller form |
| Never loosen the dismiss gate wholesale | on v2 it stopped 8 dismissals of real problems and made 7 false alarms in one pass; at five false alarms a miss it pays for itself | **measured** | a rule, recorded in the guide |
| Capture the model's own decision before the gates (the gates rewrite it in place) | without it, a gate change needs the model re-run (paid, noisy) | **built** (`b16c220`), to deploy | step 1 |
| Audit false merges: every fleet comment "matched on norm_key / alert_key", a sample labelled by the operator | duplicate links cannot show a wrong merge: the operator never sees a second issue | open | step 3 |
| Measure each gate (intent, cleanup, dismiss, edge-5xx) against the labels | not done; production records the model's choice and the gate's verdict | open | step 4 |
| Measure filing and dedup against the operator's duplicate links, in all three repos | 1,095 filing decisions, 506 issues, 145 duplicate links (77 only in close comments); multi-issue clusters: podcast_scraper 24, homelab 10, orrery 4 | open, in progress | step 3 |
| A stale-client rule in filing (an event from a build older than its fix's close is not a reopen) | 3 of the fleet's 63 real reopens/regressions; GlitchTip cannot tell which build was live, so it needs deploy history | **measured**, parked | step 3's reopen scores show whether it matters more |
| A trace or deploy link as an extra dedup key | errors that look different but share a trace or a deploy may be one incident | candidate | step 3 can measure it against the duplicate links |
| `normalized_key` and the ledger lookup ignore the repo: two projects with the same message could match each other's issue | not seen; the code allows it | open | step 3 will show whether it ever happened |
| A `muted-class` label for a bug whose fingerprint keeps changing | designed 2026-08-28, never built | open | NEXT_STEPS |
| Cleanup autonomy (track A3) | cleanup still waits for the operator | open | NEXT_STEPS |
| The operational classifier, the low-signal rollup, recurrence, routing, the stale check as measured black boxes | each has a pass/fail replay gate, none a correctness measure | open | step 5 |

## 4. Data and evaluation

| Idea | What is known | Status | Plan |
|---|---|---|---|
| v2 of the Orrery dataset, without v1's rebuilt hindsight | the hindsight steered the model (its false dismissals on 15 items 0.94 → 0.21, p 0.002) | **shipped** (HF revision `v2`, eval-harness 0.7.0) | done |
| A held-out set across projects, from the exact captures since 2026-10-29 | 75 captures on 2026-11-04, about 15 Orrery; labels by outcome rules, the operator only on disagreements | open | step 6 |
| See the shipped change live, by error class and decision path (not a before/after share: three changes shipped on 11-03/04, and the week before holds the failover-test flood), with the operator's desk (filed + escalated, closed as noise) | about 3 signals a day; a week shows it runs safely, not the size of the effect | open, reading from 2026-11-11 | step 2 |
| Split the held-out set by time now; leave dismissals unlabelled; a calibration sample of agreements; state the smallest detectable effect first | from the plan's review: "operator only on disagreements" leans gold toward production, and a dismissal has no outcome | open | step 6 |
| Watch PLAYER under the shipped brief | the brief serves every project; it was measured on Orrery only, and PLAYER is a browser app too | open | step 2 |
| Grafana alerts in the evals | the ledger keeps an alert's name, not its labels, so an instance-keyed alert cannot be rebuilt | open | step 3 notes it; a source for the labels is needed |
| The dedup regression guard's coverage | its 100 signals hold no LiteLLM signal (so `assistant-failover` changed unnoticed), 0 test signals, no Grafana alert, 89 from one project | open | step 3 replaces it with real history |
| Seeded defects (a real bug replayed at its fix's parent) for the "file" class | EVAL.md's "thin spot" | open | step 8 |
| The quality of filed issues (does the bug-fix fleet ship from it) | needs seeded defects and a judge; the bug-fix fleet is paused | open | step 8 |
| A client-side corroboration probe from Umami | the hub computes site-level Umami totals every 5 minutes, not per-error user spread | candidate | after step 4 shows how much the dismiss gate's client-side cases cost |
| Labels still missing: STAGING-2/3/4 (`reference/`), and one to check, ORRERY-PROD-S (real fix or umbrella close?) | | open (operator) | NEXT_STEPS |

## 5. Models

| Idea | What is known | Status |
|---|---|---|
| Swap the model | 80+ arms, none significantly better than production's on today's prompt and gates | **measured**: not the lever |
| Local or cheaper models | in round r3, 50 arms were not significantly different from the leader on `triage_cost`, several local and free (eval-harness `rounds --goal triage_orrery`) | candidate once a split prompt exists (§2) |
| Providers | JSON mode is required; hosted Llama 4 Scout has no endpoint that offers it | a constraint to keep |

## 6. Operations around the fleet

| Idea | What is known | Status |
|---|---|---|
| No CI covers `signal-fleet/`; its only gates run in `deploy.sh` on the mini | 6a59983 got 0 checks | open (NEXT_STEPS) |
| `deploy.sh` runs the gate list it read before its own `git pull` | the deploy that adds a gate skips it; fix: re-exec after the pull | open (NEXT_STEPS) |
| A plain `git pull` on the mini deploys the fleet without its gates | pull with `deploy.sh`, even for hub-only commits | open (NEXT_STEPS) |
| Escalations with no issue filed (3 of 9 in one week) | cause not known | open (NEXT_STEPS) |
| `.deferred.json` entries never expire | harmless; pruning needs a last-deferred time | open (guide, Known gaps) |

## 7. The tool used to measure all this

Everything found in eval-harness on the way, with its status: [eval-harness feedback (fleet)](eval-harness-feedback-fleet.md).
