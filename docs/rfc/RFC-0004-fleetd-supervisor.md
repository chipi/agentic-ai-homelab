# RFC-0004 — `fleetd`: the fleet supervisor daemon

**Status:** Proposed (2026-07-25)
**Runs on:** the `homelab` Mac mini, under `launchd`, as one static Go binary.
**Relates to:** RFC-0002 (bug-fix fleet), RFC-0003 (signal-to-action fleet),
ADR-0008 (tech choice + framework non-adoption),
[rollout plan](../wip/fleet-rollout-plan.md) (the gate items this implements).
Top-level picture: [Agentic fleets — architecture](../fleet-architecture.md).

## Motivation

Both fleets are gated on the same operational shell: an always-on daemon
with a kill switch, budget caps, staged autonomy, and a propose-first
surface. That shell is deliberately dumb — all intelligence stays in the
evaled Python cores (RFC-0003 triage) and the chain orchestrator (RFC-0002).
One supervisor serving both fleets *is* the "shared foundations" track of
the rollout plan, implemented once.

## Proposal

One binary, one config file (`fleetd.toml`), N fleet blocks:

```toml
[fleet.triage]
enabled   = true
interval  = "10m"
cycle_cmd = "python3 /Users/operator/signal-fleet/mvp/orchestrator.py --cycle"
workdir   = "/Users/operator/signal-fleet/mvp"
env_file  = "/Users/operator/signal-fleet/fleet.env"
stop_flag = "/Users/operator/signal-fleet/STOP"
budget_day_usd = 2.0
stage     = "shadow"          # shadow | propose | live  (passed to the cycle)

[fleet.bugfix]
enabled   = false             # flips on when Track B gates close
...
```

### Responsibilities (all deterministic, no LLM)

- **Scheduler** — one goroutine per enabled fleet; tick = run the fleet's
  `cycle_cmd` as a subprocess with `stage` + budget context in env; capture
  exit code + duration; never overlap cycles (skip tick if previous still
  running).
- **Kill switch** — `stop_flag` file checked before every cycle; present →
  skip and log. `SIGTERM` drains the in-flight cycle then exits (launchd
  restart-safe).
- **Budget guard** — per-fleet daily USD counter (fed back by the cycle's
  ledger output); cap reached → fleet paused until midnight + alert metric.
  This is defense-in-depth layer 2 of 3 (per-item caps live in the cores;
  the OpenRouter per-key limit is the hard backstop).
- **Health + spend metrics** — one VictoriaMetrics sample per cycle
  (`fleetd_cycle{fleet,outcome,stage}`, `fleetd_spend_day{fleet}`), same
  no-auth import path the fleets already use; Grafana panels per the
  rollout plan.
- **Digest hook (propose stage)** — after a cycle produces proposals, POST
  them to the notify target (ntfy topic v1). Approval mechanics stay in the
  fleet cores; fleetd only transports.

### Non-goals

No workflow engine, no state beyond a tiny JSON day-counter, no LLM calls,
no queue — cycles are idempotent and cheap to re-run by design (the cores
own idempotency via their ledgers). If reliability needs ever exceed this,
that is the **Temporal revisit trigger** (ADR-0008), not a fleetd feature.

## Rollout

fleetd itself follows the plan's Track A: first deployed with
`stage=shadow` for the triage fleet only; the bugfix block flips on when
Track B's gate closes. Deploy = `GOOS=darwin GOARCH=arm64 go build` on the
laptop, scp the binary + a launchd plist to the mini.

## Open questions

1. ntfy vs GH-issue digest as the v1 propose surface (operator ergonomics).
2. Where the day-counter resets live (fleetd local midnight vs UTC).
3. Whether bugfix cycles (long chains) run under fleetd's scheduler or stay
   operator-triggered until Track B stage B2.
