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
| **3 · Remediation** ([RFC-0005](rfc/RFC-0005-remediation-fleet-post-reboot-recovery.md) = v1) | **config/runtime** | long-term: `config-enhancement` → lever menu (typed, allowlisted, verify-after-apply, auto-rollback). v1: a deterministic check on prod → one registered [prod lever](#prod-levers-how-a-fleet-may-act-on-prod) (post-reboot restage) → outcome verify | v1 proposed; no lever in force yet |

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
6. **The operator gates every irreversible and every change to prod —
   per run, or by approving a named lever.** Merges and deletes are always
   per run. A change to prod may run without the operator only through a
   lever in the [registry below](#prod-levers-how-a-fleet-may-act-on-prod):
   one purpose-built action with a written contract, enforced outside the
   fleet's own code, promoted shadow → propose → live per class. A lever
   not in the registry does not exist, and the never-list can never be a
   lever. Permanently, not provisionally. *(Amended 2026-09-30 with
   RFC-0005; was: "The operator gates irreversibles: merges, deletes, prod
   state.")*
7. **The fleet never triages its own substrate** (added 2026-08-02).
   Infra alerts are fleet *signals* — the triage fleet polls Grafana's
   firing alerts like any source — **except** alerts about the machinery
   the fleet runs on (fleetd, VictoriaMetrics, Grafana itself): a dead
   fleet cannot triage "the fleet is dead". Those rules carry
   `meta: "true"` and the boundary is enforced three times, mechanically:
   the notification policy routes them away from GlitchTip (which is a
   fleet source — the side-door), the fleet's Grafana pass skips the
   label, and they surface on the Operator Inbox dashboard's substrate
   panel instead. Corollary contract for alert authors: fleet-consumable
   alerts must be *truthful symptoms* (stable `alertname`, `service` +
   `environment` labels, a symptom-stating summary, a probe hint);
   plumbing meta-states (`DatasourceNoData`/`DatasourceError`) are never
   fleet food. Health rules over *pushed* metrics must set
   `noDataState: OK` when absence-of-series is the healthy state
   (measured: 6 days of false DatasourceNoData against a fleetd that had
   simply never failed a cycle), paired with an explicit dead-man rule
   where silence genuinely is the alarm.

## Prod levers — how a fleet may act on prod

Added 2026-09-30 with [RFC-0005](rfc/RFC-0005-remediation-fleet-post-reboot-recovery.md).
Invariant 6 lets a fleet change prod without the operator on the gate only
through a **lever**. Levers are expected to grow as prod runs (recovery
after a reboot today; adding capacity under load is the obvious next
candidate), so this is written as a rule with a hard entry bar, not as a
string of one-off exceptions. What keeps it from drifting is not how many
levers exist but three things: a never-list, a contract, and enforcement
outside the fleet.

### Three tiers of prod action

| tier | what | gate |
|---|---|---|
| **Never a lever** | deletes (including scale-in: it deletes a node); restores over prod data; schema or data migrations; minting or rotating secrets; generic infrastructure applies (`infra-apply`-style); merges; **any action that takes free-form inputs** | the operator, every run, permanently |
| **Lever-eligible** | returns prod to a **known prior state** (e.g. restage secrets after a reboot), or makes a **bounded, reversible** change (e.g. add one node, with a spend cap) | the operator approves the lever once, through its RFC; its runs climb the ladder |
| **Everything else** | ad-hoc prod work | the operator, per run |

A lever is always a **purpose-built workflow** with fixed or bounded
inputs — never a generic tool invoked with the right arguments. Changing
the never-list means amending this invariant.

### The lever contract

Every lever's RFC fills this in; a lever without all of it is not admitted:

| field | what it pins down |
|---|---|
| trigger | the signal, from a deterministic check (never an LLM verdict) |
| preconditions | the guards that must hold before acting |
| action | exactly one workflow path, with fixed or bounded inputs |
| blast radius | what it can touch, written down |
| verify | the observability probe that proves the outcome — the loop is closed by evidence, not by "the workflow went green" |
| on failure | latch and page; never retry past a guard |
| rate cap | e.g. at most N runs per 24 h, successes included |
| environment + identity | a dedicated GitHub environment for this lever, approved by a bot identity that is a reviewer **only** there (below) |
| stages | shadow → propose → live, per class, on a frozen-replay eval |
| owner | the RFC that admitted it |

### Containment — enforced outside the fleet

A lever may do what its contract says and nothing more, and that must not
rest on the fleet's own code, because that code holds the credential. Three
layers, weakest first:

1. **The fleet's allowlist** — the code refuses other workflows. Needed,
   but it is the credential holder policing itself.
2. **The purpose-built workflow** — it refuses inputs outside its purpose.
3. **A dedicated environment per lever, approved by a bot.** The lever's
   workflow deploys to its own environment (e.g. `lever-restage`), whose
   required reviewers are a bot machine account plus the operator. The bot
   is a reviewer on **no other environment** — in particular not on `prod`
   — so GitHub itself refuses any other approval, even with a stolen bot
   token. This is the only per-workflow boundary GitHub offers: tokens
   cannot be scoped to one workflow; environments can. A CI check in the
   target repo asserts that exactly one workflow file names each lever
   environment.

The cost is that a lever environment duplicates the environment-scoped
secrets its workflow uses. Values can't be copied between environments
(secrets are write-only), so they are set from the operator's source for
both, and a drift check compares the secrets' `updated_at` metadata.

### Anti-drift

- **This registry is the only source.** Adding a lever means an RFC plus
  the full ladder; nothing reaches `live` without its row here.
- **Every lever run is visible** — a ledger row and an info-level "acted"
  alert. No lever acts silently.
- **Credentials expire.** A lever's bot token carries an explicit expiry;
  renewing it is when the operator re-confirms the levers it serves.

### Registry

| lever | action | environment | owner | status |
|---|---|---|---|---|
| post-reboot restage | `restage-prod-secrets.yml` (`surfaces=all`, `recreate=true`) in `chipi/podcast_scraper` | `lever-restage` | [RFC-0005](rfc/RFC-0005-remediation-fleet-post-reboot-recovery.md) | proposed — **not in force**; no lever approves anything until its row says `live` |

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
