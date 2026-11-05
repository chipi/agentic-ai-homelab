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

| # | Where it hurt | What would help | Status |
|---|---|---|---|
