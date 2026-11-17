# 0009 — Fleet items and notes handed over to flotilla and the fleet session

**Date:** 2026-11-17
**Operator:** Marko (chipi)
**Agent:** Claude Opus 5.5, via Claude Code (flotilla session)
**Outcome:** the fleet items that homelab's punch list carried are now split between two owners.
The platform and fleet-code items went to the flotilla session, and the work of running, measuring and tuning
the fleets went to the fleet session. The agent platform evaluation was closed.

## What happened

| Note | What it was | How it ended | Lasting parts now in |
|---|---|---|---|
| `flotilla-items.md` (eb2b80a) | the 27 open fleet items moved out of `NEXT_STEPS.md` for the flotilla session | split (aaf9dff): 13 open stay as the flotilla session's backlog; it stays open | `wip/flotilla-items.md` |
| `fleet-items.md` (aaf9dff) | the 14 open items that are running, measuring and tuning the fleets, and the X3 assistant's gaps | new, owned by the fleet session | `wip/fleet-items.md` |
| `agent-platform-evaluation.md` (f6a18e7) | the 2026-11-08 evaluation of the problem, the constraints and three options that chose flotilla | closed: the decision is flotilla's ADR-0001 and RFC-0001; what they did not cover went into `flotilla-items.md` | flotilla [history 0000](https://chipi.github.io/flotilla/history/0000-origin-evaluation/) (the full text), [ADR-0001](https://chipi.github.io/flotilla/adr/ADR-0001-platform-foundations/), `wip/flotilla-items.md` "From the agent platform evaluation" |

Four more fleet notes in `docs/wip/` are the fleet session's (the operator, 2026-11-17):
`fleet-evals-handover.md`, `triage-fleet-improvement-plan.md`, `triage-fleet-opportunities.md` and
`eval-harness-feedback-fleet.md`.

The evaluation's full text stays in git history (`git log --all -- docs/wip/agent-platform-evaluation.md`).
flotilla keeps the full text as [history 0000](https://chipi.github.io/flotilla/history/0000-origin-evaluation/).
