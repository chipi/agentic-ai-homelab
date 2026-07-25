# ADR-0008 — Fleet daemon in Go; deliberate framework non-adoption (with revisit triggers)

**Status:** Accepted (2026-07-25)
**Context:** RFC-0002 / RFC-0003 fleets are approaching go-live
([rollout plan](../wip/fleet-rollout-plan.md)); both need an always-on
daemon on the mini. The operator's stack is Python/TypeScript and wants a
deliberate learning surface for new tech — plus an explicit
"are we reinventing a wheel?" audit against the agent-framework ecosystem.

## Decision 1 — the daemon is Go (`fleetd`), the intelligence stays Python

One small Go binary supervises **both** fleets: per-fleet poll loops
(goroutines + tickers), kill-switch flag checks, per-day budget counters,
digest notification, metric pushes, `launchd` as the outer supervisor. Each
cycle **shells out to the proven Python cores** (`signal-fleet/mvp/`, later
the bugfix orchestrator) — the evaled decision logic is not rewritten.

Why this split: the daemon is the dumbest, most ops-shaped component in the
system — exactly Go's sweet spot (static binary, concurrency primitives,
signal handling) and exactly where a new language adds no correctness risk:
if `fleetd` dies, nothing intelligent is lost; a bash loop under launchd is
the 20-minute fallback. The measured quality bars live entirely in the
Python + prompts + gates, which stay untouched and re-usable by any shell.

**Rust considered, rejected for this component:** pure I/O orchestration has
no perf or memory-safety pressure; Rust's cost buys nothing here. Named
future candidate where it would: a Fleet-3 lever-executor, where
"provably cannot do the wrong thing" has real value (future RFC).

## Decision 2 — no agent framework adoption; the audit and why

Inventory: the stack is already ~80% reuse — **pi** (the agent harness),
**OpenRouter** (routing/billing), **Langfuse**, **GlitchTip**,
**VictoriaMetrics/Logs/Traces**, **Grafana**. The hand-rolled 20% is the
thin deterministic spine (~few hundred lines), the gates, prompts, probe
menu, and frozen-replay evals — which is precisely what no framework ships,
and where the project's measured value is concentrated.

| Candidate | Verdict | Reasoning |
|---|---|---|
| **LangGraph** (1.0, checkpointing) | not adopted | its value = durable state graphs for LLM-driven flows; our sacred rule is the opposite (no LLM in control flow), loops are ~150 deterministic lines, and chains cost ~$0.50 to simply re-run — durability is not our pain |
| **Temporal** | **track OPEN** | industrial durable execution; the right answer if fleets outgrow "restart the cycle" reliability. **Revisit trigger:** a lost in-flight chain costs more than an hour of operator attention, or fleet count/volume makes launchd babysitting real work |
| **LiteLLM** | **track OPEN** | per-key budget caps, multi-provider routing/fallback, spend tracking. **Revisit trigger:** going beyond OpenRouter (operator explicitly anticipates this). Prior art in-repo: [RFC-0001](../rfc/RFC-0001-litellm-langfuse-capture.md) already designed LiteLLM↔Langfuse capture — resurrect it then |
| CrewAI / AutoGen-style | rejected | LLM-driven multi-agent orchestration — the architecture ADR-0004 measured at 10–180× our cost for equal outcomes |
| promptfoo / DeepEval | not adopted | our eval's value is fixtures + frozen probe tables (domain-specific); the runner is trivial |
| n8n | deferred as designed | RFC-0002 already earmarks it as glue for non-core integrations |

**The elephant-in-the-room verdict:** none found. The genuinely heavy
reusable pieces are already reused; the custom part is small and
load-bearing. 2023-era instincts ("surely LangChain does this") do not
survive the inventory.

## Consequences

- New top-level `fleetd/` (Go module); mini runs a cross-compiled binary —
  only the dev laptop needs the toolchain.
- Two explicitly-open adoption tracks (Temporal, LiteLLM) with named
  triggers — this ADR is the place to return to when either fires.
- Fleet-3's future executor language question is parked here for Rust.

## Alternatives considered

Boring-first (launchd + bash loop now, Go later) — viable, rejected by the
operator in favor of Go-first (~1–2 days, deliberate learning goal).
Rewriting fleet cores in Go — rejected: re-validation cost of evaled logic
for zero functional gain.
