# ADR-0003 — Custom subagent roster: model tiering + advisor/executor escalation

**Status:** Accepted
**Date:** 2026-07-01
**ctx src:** `docs/history/0004-agent-config-and-skills.md`; Claude Code subagent
mechanics verified via the `claude-code-guide` agent (subagents.md).

## ctx

The operator had zero custom Claude Code subagents — role-based delegation existed
only in opencode (the `oh-my-openagent` fleet). Two goals: (1) bring that fleet
mental model to Claude Code, and (2) **lock in cost** — do the *volume* of work on
the cheapest capable model, reserving `opus` for the hardest reasoning only. A
side benefit: the whole fleet can be developed and tested on cheap models.

## Decision

Six subagents in `~/.claude/agents/` (global; mirrored into
`workstation/claude/agents/` for restore). Each pins the cheapest model tier that
does its job. The `sonnet` tier escalates hard sub-decisions to a single `opus`
**advisor** via direct nested `Agent(advisor)` calls — Claude Code supports
subagent nesting (depth ≤ 5), and only the executor's summary returns to the main
conversation, so the advisor's long reasoning never enters the main context.

| Subagent | model | role | key tools | skills | consults advisor |
|---|---|---|---|---|---|
| **advisor** | `opus` | deep reasoning — architecture, hard bugs, ambiguous specs | Read, Grep, Bash | — | *is* the advisor |
| **planner** | `sonnet` | decompose, freeze contracts | `Agent(advisor)`, Read, Grep | — | yes |
| **implementer** | `sonnet` | autonomous impl (backend + ui) | `Agent(advisor)`, Read, Edit, Write, Bash | `ship`, `secrets-scan` | yes |
| **reviewer** | `sonnet` | ruthless review, structured findings | `Agent(advisor)`, Read, Grep, Bash | `secrets-scan` | yes |
| **tester** | `haiku` | write/run tests, bounded | Read, Edit, Write, Bash | `repro-first` | no |
| **docs-writer** | `haiku` | docstrings, comments, README | Read, Edit, Write | `docs-preflight`, `new-doc` | no |

**Tiering:** `haiku` = bounded/mechanical; `sonnet` = workhorse (plan/impl/review);
`opus` = advisor only, reached via escalation. Each subagent's system prompt
encodes the operator's relevant non-negotiables and preloads the matching
rule-enforcing skills.

## Consequences

- **Positive:** `opus` cost is bounded to escalated hard questions; the fleet is
  developed and tested on cheap models; role-based delegation lands in Claude
  Code; the advisor's reasoning stays out of the main context window.
- **Negative:** more config to maintain (6 agent files + the escalation contract);
  a nesting-depth budget (≤ 5) to respect if agents chain.
- **Neutral:** mirrors the opencode fleet mental model, but is a separate,
  Claude-Code-native implementation — not shared config.

## Alternatives considered

- **All-`opus` single tier** — rejected: expensive; most work doesn't need `opus`.
- **Orchestrator-mediated escalation** (executor returns "blocked" → the
  orchestrator spawns the advisor) — rejected: direct `Agent(advisor)` nesting is
  supported and keeps the advisor's output out of the main context.
- **Leaner 4-agent roster** (advisor + implementer + reviewer + tester) —
  deferred: start with the full 6; prune any that go unused.
