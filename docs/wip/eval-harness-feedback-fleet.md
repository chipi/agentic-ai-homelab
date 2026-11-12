# eval-harness feedback from the fleet session

**What this is:** a running log, kept by the fleet session while it improves the triage fleet with eval-harness:
where the tool made a step harder than it should be, what was missing, what could be simpler, and what helped.
Each entry says what was run, what happened, what would help, and whether it was sent to the eval harness session
(which folds it into the next release). **Started** 2026-11-05, seeded with the findings of 2026-11-04.

Status: **fixed** (in a release, named), **recorded** (accepted, not yet in a release), **open** (not sent, or no
answer yet).

## 2026-11-04: round r4 on the triage fleet (harness 0.6.2 → 0.7.0)

| # | Where it hurt | What would help | Status |
|---|---|---|---|
| 1 | Counting how many dismiss-gate downgrades saved a miss and how many made a false alarm needed a hand script; no command crosstabs one per-item score against another | `inspect --crosstab` | fixed (0.7.0) |
| 2 | Per-item rows carry no output text or reference, so reading why an item moved meant joining files by hand | items with outputs and reference side by side | fixed (0.7.0) |
| 3 | `goals` printed 80+ rows, the baseline far below | `goals --arms/--top`, baseline always kept | fixed (0.7.0) |
| 4 | v1's rebuilt evidence stated outcomes ("issue no longer exists"), a browser clock gave lastSeen 2023-11-14, a release postdated the decision | the dataset's v2, and "read the items before you trust a difference" in the skills | fixed (v2 published; skill text 0.7.0) |
| 5 | `fetch.py` could not restore v1 in a fresh clone: an importer field added after the capture changed every record's hash | new importer fields behind a query key; `evh capture-restore` | fixed (0.7.0) |
| 6 | `dataset-from-capture --from` kept the old version's items and reported "0 changed"; `--fieldset` alone kept no fields | both fixed | fixed (0.7.0) |
| 7 | A relative `--importer` path resolved against the working directory, the query paths against the data root | one rule | fixed (0.7.0) |
| 8 | A failed `label-import` left a half-written set that blocked its name | validate first, write atomically | fixed (0.7.0) |
| 9 | `--dry-run` called its estimate an upper bound and was 3x low for a multi-turn adapter | say it counts one call per item; show arm-smoke's measured cost | fixed (0.7.0) |
| 10 | `evh run` printed nothing until the end when not on a terminal | a line per finished item | fixed (0.7.0) |
| 11 | No way to compare one arm across two versions of a dataset (`run-compare` refused) | `pair-test --b-dataset` | fixed (0.7.0) |
| 12 | `pair-test --b-dataset` refused the goal's own measure ("0 items scored") and did not say which runs stood for each side | refuse by name, name the runs | fixed (0.7.0) |
| 13 | Nothing said a round must be open before an arm runs; the baseline had to be carried in with `--keep` | the skill and AGENTS.md say so | fixed (0.7.0) |
| 14 | The skills started from nothing; "measure one change against an existing baseline" had no entry | a skill entry for it | fixed (0.7.0) |
| 15 | A prediction made before a run had nowhere to live (commit messages instead) | `hypothesis:` block in an arm config | fixed (0.7.0) |
| 16 | A dataset version made after a run cites its predecessor cannot gain a lineage link | a command that adds lineage without touching items | recorded (owner) |
| 17 | Taking new harness code mid-round splits a round's instrument; the fix was a worktree at the old commit | a round pins its harness code, or says how to run an arm on it | open |
| 18 | The goal's `decision:` named only models; r4's arms were fleet changes | the goal text | fixed (0.7.0) |

## 2026-11-05 onwards: Track A, the fleet's code as black boxes (harness 0.7.2)

The plan: [triage fleet improvement plan](triage-fleet-improvement-plan.md). Questions asked before starting (sent
2026-11-05): how an item carries a system's external state at decision time; how a goal treats a deterministic
system (k=1, no variance); pair-level scoring (an item per signal, per pair, or per fingerprint history); gold from
links between items (`duplicateOf`); where a new code example lives.

**Answers (eval harness, 2026-11-05, checked against 0.7.2's code):** a system's world at decision time is part of
the item's body (canonical JSON, hashed; the adapter interprets it), filter/split keys go in item fields; k=1 is
fine for deterministic code, and a regression guard is the same dataset against a silver reference from the
current code's own run, read with `inspect --disagree`; `score()` sees one item and a run's metric is the mean of
its items, so the item is the unit judged (a fingerprint's whole history, replayed in order, keeps filing's order
effects); `label-from-capture` labels an item from its own record, so links between items go into that item's
outcome; a new example, `examples/signal-fleet-filing/`, nothing fleet-specific in `harness/`.

| # | Where it hurt | What would help | Status |
|---|---|---|---|
| 19 | None of these six design questions is answered in the docs or skills: what an item should carry for a system that reads external state, how to treat a deterministic system, how a goal splits "correctness" from "regression guard", what unit `score()` judges, how gold comes from links between items. They needed a round trip to the harness's maintainer | a "your system is plain code" page: the item holds its world at decision time, k=1, the two goals, the item as the judged unit, links into the outcome | open (sent with this log) |
| 20 | A run-level metric is impossible: a run's score is the mean of its items', so precision and recall over pairs across a run cannot be expressed | a run-level metric hook in the adapter | recorded (0.8.0 candidate) |
| 21 | Labels cannot span items: `label-from-capture` labels one item from its own record, so "A is a duplicate of B" has to be folded into one item's outcome | labels across items | recorded (0.8.0 candidate, if hit) |

## 2026-11-05: step 0, moving to v0.7.2

A fresh clone at the tag (`18062e3f`) with its own venv: `fetch.py` restored both triage revisions (233 records,
items 233/65/2 and 65) and the dedup set (100), all 5 datasets materialized with every hash verified, `evh validate`
"VALIDATION PASSED", `skills-install` wrote the three skills, r4 reads as closed with its conclusion. Smooth: no step
needed a workaround except the one below.

| # | Where it hurt | What would help | Status |
|---|---|---|---|
| 22 | `evh pair-test --dataset-id orrery_triage_v1_labelled_v2 --round r4 --goal triage_orrery` → `ERROR: round r4 records no other baseline run: name --b`. r4.yaml has `baseline: null`: a round opened with `--keep <baseline config>` carries the arm in but records no baseline, and `round-open` has no flag to set one. With `--b triage_baseline_pro_v2data_v1` it works (the leader picked, p 0.0014, Bonferroni/3 applied) | `round-open --baseline <config_id>`, or `--keep` of the dataset's baseline arm recording it as the round's baseline | open (sent 2026-11-05) |

## 2026-11-05: step 3, is the filing replay faithful?

Before an adapter can score filing against gold, the replay has to do what production did. Getting there took six
fixes, none of them visible from the harness side; each would have shown up as a wrong score on a gold item.

| # | Where it hurt | What would help | Status |
|---|---|---|---|
| 23 | A code adapter has no faithfulness step: nothing in the harness asks "does the adapter, run on the production code of the time, reproduce production's recorded outputs?" before scoring against gold. Here it was 86/92 at first, and every one of the 6 misses was an adapter or data bug, not a fleet bug | a `faithfulness` stage for code adapters: replay the recorded period with the recorded code, require full agreement (or name each exception) before a run against gold counts | open |
| 24 | The code under test changed 10 times in the 19-day window (the mini pulled 10 versions of `signal-fleet/mvp`); replaying it all with one commit misattributed 4 decisions. The versions came from the host's `git reflog`, the switch times from its pull times | an item (or the dataset) records the code version the recorded output came from, and a code adapter runs each item at that version | open |
| 25 | The host clock ran ~1.6 s behind GitHub's for an hour on 2026-10-30, so 4 writes landed after the decision stamp that follows them in code. Attribution needed a measured clock slack | nothing harness-side; noted as a trap for timestamp-joined outcomes | noted |
| 26 | Production's writes were first matched to decisions by the fingerprints an issue names; one reopen never named its fingerprint, so a faithful replay read as a miss. Matching by time window (between the previous decision of the cycle and this one) is exact | a note in the "your system is plain code" page: join outcomes by time and order, not by a key the outcome may not carry | open |
| 27 | Code under test has no record of its own: models get `data/models/` records (kind llm/ml, deployments, onboarding) and a catalog page, but a code version (the fleet at a commit) appears only as `build.ref` and config params. Nothing lists which versions were tested, which ran in production when, or their faithfulness result | a `kind: code` record beside models (commit, deployed periods, faithfulness), shown in the catalog like models; extends 0.8.0 item (a) | open (sent 2026-11-05) |
| 28 | A regression-guard arm (the same code at two commits) must give identical output, and V5 fails it as an inert knob; v0.7.2 cannot say "expected identical" | `expect_identical_to: <config_id>` on an arm (the eval harness session put it on the 0.8.0 list) | recorded (0.8.0) |
| 29 | No held-out split: the triage captures were split by time by hand (D = 2026-11-07T00:00Z, a sha256 manifest of the tuning side, the test side not opened until one candidate is ready; fleet-eval-data `projects/triage-heldout/SPLIT.md`). Nothing stops a run or a label import on the test side | a dataset split by a time boundary with a sealed side the harness refuses to run, score or label until an unseal names the candidate config and its committed hypothesis; a check that the open side still matches its manifest | open (sent 2026-11-09) |
| 30 | No counterfactual arm from recorded outputs: the gates were measured at $0 by re-running other gate code on r4's recorded outputs (`projects/orrery-triage/gate_replay.py`), after a `--verify` step that reproduces all 390 recorded decisions with the original code | an arm kind "derived": a base run plus transform code, with a required verify step before the derived run counts (entry 23's faithfulness, for post-processing) | open (sent 2026-11-09) |
| 31 | No label coverage report: how many items an outcome rule set labels now, skips, or cannot label yet (outcome not matured). On 98 tuning items: 3 labelled, 31 left out by design, 44 waiting for an issue verdict, 17 waiting to mature, 3 for the operator (`projects/triage-heldout/outcome_count.py`) | `evh label-coverage --rules RULESET`, by rule, with "not yet mature" as its own class and each item's maturing date | open (sent 2026-11-09) |
| 32 | For R: a recorded-lookups format that works. `exact_filing_replay.py` replays filing decisions from per-decision records: every external call in order (method, path, payload, response or error), the clock readings in order, the keys, the matched state row, the result; it compares the state file afterwards (comparing what the code passed to its writer let a mutant survive). Schema: agentic-ai-homelab `signal-fleet/mvp/callrec.py` (b4f4019) | input to 0.8.0's replay package | sent 2026-11-09 |
| 33 | k runs of a temperature-0 model are not k independent samples: in r4's gate measurement 3 runs gave 23 gate firings on 9 distinct items | pair-test and the run summary report the item as the unit when an arm's runs are near-duplicates, or show distinct items beside item-runs | open (sent 2026-11-09) |

## 2026-11-11/12: the held-out set exposed, and plan step 5 (the fleet's deterministic code against outcomes)

Seven gaps found while doing this by hand in fleet-eval-data. Sent to the eval harness session 2026-11-12 (via
homelab, then answered in detail on its questions); the operator approved them for implementation. The full
answers, with what "done" means for each, are in fleet-eval-data `BOUNDARY-PROPOSAL.md` and the reply of
2026-11-12.

| # | Where it hurt | What would help | Status |
|---|---|---|---|
| 34 | 78 of 91 sealed items were read by sessions doing operations work before anyone noticed (one summary reached a public repo); the register (`triage-heldout/exposed.tsv`) and a public-repo check (`exposure_check.py`) were built by hand | an exposure register on a sealed dataset (record a read; every later score leaves exposed items out and says how many); a check of listed public repos for sealed ids | recorded (approved) |
| 35 | a live safety watch over the sealed period had to be a hand-written counts-only script (`triage-heldout/safety_watch.py`) | counts-only reports over a sealed dataset, grouped by fields the split's config allows, refusing ids and text | recorded (approved) |
| 36 | labels that need 14 days to be knowable were counted "not mature" by hand and the reruns were remembered in notes | labels with an outcome date and a knowable date, a window per rule, append-only relabel runs, "changed after maturing" counted, scores with an as-of date | recorded (approved) |
| 37 | GitHub close reasons and GlitchTip counts were read live at label time and never frozen, so a rerun can give other labels | outside-system labels read at a stated time and frozen, with provenance (source, endpoint, time, response hash) | recorded (approved) |
| 38 | the stale-check variants nudged nothing at 10 and 14 days, because the replayed history carried production's own labels; hiding them first re-nudged 5 issues from before the window | variant replays that hide the system's own in-window writes, with the default variant required to reproduce production first, and a history-confound count per result | recorded (approved) |
| 39 | replaying a period on the code that ran then needed code periods from the deploy log and git reflog (21 versions in one window) | a past-period baseline: recorded output, the period's code replayed (must equal it), and the candidate, on the same items | recorded (approved) |
| 40 | per-decision outcome labels exist only for the action production took (the operator closed the issue production filed) | per-decision scoring that marks each label action-independent or observed only under the recorded action, scores a variant only where it can, and groups decisions by their unit (the fingerprint) | recorded (approved) |
| 41 | three labeller mistakes (re-polls counted as recurrences, a duplicate close as noise, the event's culprit instead of the issue's) were caught only by reading results | named mutants of a labeller's rules and joins, each required to change labels; a mutant that changes none is reported | recorded (RFC-031, confirmed 2026-11-12) |
| 42 | the rollup labels had to be checked by hand against the rule as deployed at each decision (74 of 76 reproduced, 62 of them dated only by commit time) | a label counts only where the recorded decision is reproduced by the rule version deployed then; the rest left out and counted, approximate versions counted apart | recorded (RFC-031, confirmed 2026-11-12) |
| 43 | 17 rollup items and 498 re-triage fingerprints were gone from GlitchTip and labelled "gone" by hand | a label-coverage class "gone from the source, or its id reused" (first-seen checked against the record found), with last seen; never "no outcome", never negative | recorded (RFC-031, confirmed 2026-11-12) |
