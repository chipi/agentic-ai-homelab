---
name: fleet-stats
description: Show per-subagent invocation counts and token/cost spread by model tier from the current Claude Code transcript — proves whether the model-tiered fleet (haiku/sonnet/opus) actually spreads token cost. Use to see who was invoked, how often, tokens per agent/model, and escalation rate. Local and read-only (no Grafana/OTEL needed).
---

# fleet-stats

Read the current session's transcript and report how the subagent fleet behaved —
who ran, how often, tokens per agent and per model tier, and how often executors
escalated to the advisor. Answers "does the cost-spread work" from real data.
Local + read-only.

## Run

```bash
python3 ~/.claude/skills/fleet-stats/scripts/fleet_stats.py   # latest transcript for this cwd
# or a specific transcript:
python3 ~/.claude/skills/fleet-stats/scripts/fleet_stats.py <path-to-session>.jsonl
```

It parses each `toolUseResult` with an `agentType` (a top-level subagent
invocation) for `totalTokens` + `resolvedModel`, then walks
`<session>/subagents/` for nested escalations (see "How nesting is counted").

## Read the report

- **invocations per agent** — who ran, how many times, on which model, tokens.
- **token + cost spread by model tier** — the money shot: `haiku`/`sonnet` should
  carry the volume; `opus` should be a small slice (advisor escalations only). If
  `opus` dominates, the tiering isn't paying off.
- **escalation** — nested executor→advisor calls.
- **delegation diagram** — mermaid; who called whom.

Cost rates in the script are approximate — update to current pricing (see the
`claude-api` skill); tokens-per-model is the real signal.

## How nesting is counted (v2)

Only **top-level** subagent calls (those the orchestrator spawned) appear in the
main transcript. A **nested** call — an executor consulting the `advisor` — runs
as a separate sub-agent, recorded in `<session>/subagents/agent-<id>.jsonl`, and
never lands in the main transcript. v1 read only the main transcript, so nested
escalations were **invisible**: escalation showed `0 nested` and the advisor's
(opus) tokens went uncounted entirely (they do *not* roll into the parent — a
parent's `totalTokens` is its own final-context, disjoint from the child's).

v2 walks the `subagents/` dir too:

- **Top-level** rows use the authoritative `totalTokens` from the main transcript
  — identical numbers to v1.
- **Nested** rows read the sub-agent's own final-context (input + cache + output
  of its last turn — exactly what `totalTokens` measures) from its transcript, and
  link back to the parent that spawned it via `meta.toolUseId`. Some escalations
  (e.g. a reviewer's advisor consult) are never persisted as a result in the
  parent, so the sub-transcript is the only source.

No subtraction is needed — a parent's tokens and its children's are disjoint, so
they simply add. The nested final-context reproduces the authoritative number
exactly where both exist (cross-checked), and within ~1% for a parent that itself
has children (a small returned-summary delta).
