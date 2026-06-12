# WIP — work in progress

This directory holds work-in-progress notes: plans, drafts, analyses,
prioritized task lists. Promotion targets:

| Promote to | When |
|---|---|
| `docs/adr/` | The decision is structural and final |
| `docs/rfc/` | The decision needs a proposal-and-review process before adoption |
| A reference doc | The content is stable enough to be a reference |
| `docs/history/0NNN-...md` | The session that produced it has wrapped |
| *delete* | Turned out not to matter |

WIP notes that haven't been touched in a quarter should be either promoted
or deleted. Stale plans rot, and stale plans that look "official" rot worst.

## Convention

- Files here are tracked in git (so they're findable + diffable).
- Names are descriptive (`NEXT_STEPS.md`, `MIGRATION_PLAN_X.md`) —
  not dated (dates change; intent doesn't).
- One promotion target stated at the top of each doc ("→ becomes
  `docs/adr/ADR-NNNN` once decided", "→ becomes a section of
  `docs/architecture.md` when stable").
