# 0010 — the fleet session's wip notes reviewed: 3 closed, 1 kept

**Date:** 2026-11-17
**Operator:** Marko (chipi)
**Agent:** Claude Opus 5.5, via Claude Code (fleet session)
**Outcome:** of the four `docs/wip/` notes the fleet session owns (the operator's decision, relayed by the homelab
session on 2026-11-17; the split of the fleet items and notes between flotilla and the fleet session is
[history 0009](0009-fleet-notes-handed-over.md)), three are closed and one stays open. Each was read in full and checked against the fleets as
they run now: their code moved to [flotilla](https://github.com/chipi/flotilla) on 2026-11-08 and left this repo on
2026-11-16, and the evaluation moved to the private repo chipi/fleet-eval-data on 2026-11-05. The full text of each
closed note stays in git history (`git log --all -- docs/wip/<name>`).

## What happened to each note

| Note | Date | What it was | How it ended | Lasting parts now in |
|---|---|---|---|---|
| `fleet-evals-handover` | 11-04 | the homelab session's handover of the triage fleet's evaluation to the fleet session | acted on: F7 fixed and the brief change shipped the same day, rounds r4 and the Track A evals since; the X3 assistant items and the fleet items it listed are in [fleet items](../wip/fleet-items.md) | fleet items; its two lessons from the assistant evals (code selects, the model writes; check a scorer with hand-made answers before trusting it) stay in [x3-assistant-evals](../wip/x3-assistant-evals.md), where they came from |
| `triage-fleet-improvement-plan` | 11-04/05 | the plan: two tracks (the fleet's code as black boxes, the LLM step), steps 0–8 | superseded by the plan of record, fleet-eval-data `ROADMAP.md` (the operator, 2026-11-16). Steps 0, 1, 3, 4 and 5 done (filing replay and datafix 11-06, the gates measured at $0 11-06, the operational, routing, rollup, stale and re-triage replays 11-11/12); step 2 became ROADMAP T0.4's decision-mix report; step 6's split is fixed (D = 2026-11-07T00:00Z) and its confirmation is M4; step 7 is M3; step 8 is T0.7 | fleet-eval-data `ROADMAP.md` and `projects/` |
| `triage-fleet-opportunities` | 11-05 | every idea for improving the triage fleet, with its status | moved, not finished: the ideas are still options | fleet-eval-data `projects/triage-ops/OPPORTUNITIES.md` (1bd5bed), each status brought to 2026-11-17 |
| `eval-harness-feedback-fleet` | 11-05 onwards | the fleet session's running log of eval-harness friction, entries 1–55 | **kept open**: entries are still open with the eval harness session, and 0.8 is in beta | stays in `docs/wip/` |

## Links repointed

`docs/fleet-architecture.md` and `docs/signal-fleet-guide.md` pointed at the improvement plan; they now name the
roadmap. `docs/wip/fleet-items.md`'s plan item is struck (superseded), and `docs/wip/README.md` and the nav drop the
three closed notes.
