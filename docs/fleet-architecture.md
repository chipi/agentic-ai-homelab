# Agentic fleets — the architecture

The homelab's autonomous-agent system, in one picture. This page ties the
RFCs together; each RFC owns its own depth. Written 2026-07-25, at the
lab→wild transition ([rollout plan](wip/fleet-rollout-plan.md)).

## The one-sentence version

Deterministic orchestration with LLMs only at the leaves, three fleets that
each own one lever on a running system, gates that make invented knowledge
impossible to act on, and evals that replay frozen reality — so autonomy is
*earned per class, measured, and reversible*.

## The three fleets = the three levers

| Fleet | Lever | Pipeline | Status |
|---|---|---|---|
| **1 · Bug-fix** ([RFC-0002](rfc/RFC-0002-autonomous-bug-fix-fleet.md)) | **code** | GH `bug` issue → active triage (L1, intent-cited) → specialist fix (repro-first) → kick-back loop → PR; operator merges, always | bake-off measured; real-issue wiring = Track B gate |
| **2 · Signal-to-action** ([RFC-0003](rfc/RFC-0003-signal-to-action-fleet.md)) | **meaning** | o11y signal → bounded investigation (probe menu) → dismiss / cleanup / file / escalate; File chains into Fleet 1 via the `bug` label; `config-enhancement` awaits Fleet 3 | quality bar **passed**; daemon+digest = Track A gate |
| **3 · Remediation** (future RFC) | **config/runtime** | `config-enhancement` → lever menu (typed, allowlisted, verify-after-apply, auto-rollback) | design notes only; most homelab config is IaC → v1 ≈ Fleet 1 wearing an ops hat |

The seam between fleets is a **typed label** — each fleet subscribes only to
its own work type, so they compose without coupling and roll out
independently.

## The invariants (every fleet, no exceptions)

1. **No LLM decides control flow.** Orchestrators are deterministic code
   (bash/Python today, Go supervisor per [RFC-0004](rfc/RFC-0004-fleetd-supervisor.md));
   models are leaf calls behind seams.
2. **Invention cannot reach action.** Every claim that drives an action must
   cite a source (the intent gate; dismissal evidence; cleanup markers) and
   the gates are *mechanical post-LLM checks*, not prompt hopes — measured
   necessity: models do not fire the "I don't know" valve voluntarily.
3. **Asking beats guessing, structurally.** needs-info/escalate are
   first-class terminals; the reporter/operator answer becomes a citable
   rule → each escalation buys permanent autonomy (escalations must be
   *unique*).
4. **Autonomy is earned per class on frozen replay** (the eval bars), never
   granted per fleet — and it is reversible.
5. **Everything fails safe and loud** — oracle-passed or an honest
   stuck/needs-info; billing failures are `stuck:provider`, never a graded
   verdict; append-only ledgers stamp model + prompt-sha on every decision.
6. **The operator gates irreversibles**: merges, deletes, prod state.
   Permanently, not provisionally.

## The measurement machinery (why we trust any of this)

- **Bake-off** (`bugfix-fleet/BAKEOFF.md`): replayed real bugs + hidden
  oracles; produced the load-bearing findings — description quality
  dominates model choice; the two-factor model (ticket carries acceptance,
  repo carries topology); k≥3 or it didn't happen.
- **Triage eval** (`signal-fleet/EVAL.md`): frozen probe-tables, dual
  labels, asymmetric metrics (false-dismiss=0 AND escalate≤5%).
- **In production the hidden oracle is replaced by the pipeline** —
  repro-first tests, CI, reviewer, operator — and both eval rigs stay alive
  as the *hiring pipeline*: models/prompts earn seats on frozen replay for
  cents before touching reality. Incidents become fixtures (the lab and the
  wild converge).

## The substrate (reused, not rebuilt — ADR-0008)

pi (agent harness) · OpenRouter (routing/billing; per-key caps) · Langfuse
(LLM traces/cost) · GlitchTip (errors) · VictoriaMetrics/Logs/Traces +
Grafana (o11y) — all self-hosted on the mini. Deliberately NOT adopted:
agent frameworks (audit + revisit triggers for Temporal/LiteLLM in
[ADR-0008](adr/ADR-0008-fleet-daemon-tech-and-framework-non-adoption.md)).

## Reading order for a fresh brain

1. This page → 2. the [rollout plan](wip/fleet-rollout-plan.md) (where we
are) → 3. RFC-0002/0003 (per-fleet depth) → 4. `BAKEOFF.md` §6 + `EVAL.md`
(how anything got measured) → 5. ADR-0008 / RFC-0004 (the shell it runs in).
