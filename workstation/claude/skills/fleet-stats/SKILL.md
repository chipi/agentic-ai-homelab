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

It parses each `toolUseResult` with an `agentType` (a subagent invocation) and
aggregates `totalTokens` + `resolvedModel`.

## Read the report

- **invocations per agent** — who ran, how many times, on which model, tokens.
- **token + cost spread by model tier** — the money shot: `haiku`/`sonnet` should
  carry the volume; `opus` should be a small slice (advisor escalations only). If
  `opus` dominates, the tiering isn't paying off.
- **escalation** — nested executor→advisor calls.
- **delegation diagram** — mermaid; who called whom.

Cost rates in the script are approximate — update to current pricing (see the
`claude-api` skill); tokens-per-model is the real signal.
