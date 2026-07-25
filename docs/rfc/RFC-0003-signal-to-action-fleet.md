# RFC-0003 — Signal-to-Action Fleet (o11y triage: dismiss / file / escalate)

**Status:** Proposed
**Date:** 2026-07-24
**Runs on:** the `homelab` Mac mini (always-on, tailnet) — same host as RFC-0002.
**Relates to:** **RFC-0002** (this fleet is its **Phase 3 — "o11y-reactive agents
(alerts → diagnose/propose)"**, promoted to its own project); **ADR-0005**
(Langfuse/GlitchTip self-host); **ADR-0007** (Umami analytics). North-star / living
design doc: [`signal-fleet/SIGNALS.md`](https://github.com/chipi/agentic-ai-homelab/blob/main/signal-fleet/SIGNALS.md)
(this RFC is its crystallized surface, the same way `bugfix-fleet/BAKEOFF.md` sits
under RFC-0002).

## Motivation

The monitoring stack — GlitchTip (errors), Grafana alerting, VictoriaMetrics/Logs/
Traces, Umami (UX) — surfaces signals, but every one currently lands on the
operator. That does not scale and cannot be assumed. There is no automated answer
to *"so what do we do with this?"*: false alarms bury the real signals, genuine
defects reach the bug-fix fleet (RFC-0002) as garbage tickets — which the bake-off
proved fail or grind expensively — and the genuinely-hard get a silent guess
instead of a human. This fleet closes the gap: it **triages live production
signals** into **Dismiss / File / Escalate**.

## The three-fleet separation of concerns

| # | Fleet | Job |
|---|---|---|
| **1** | Bug-fixing (RFC-0002) | behavior/code issues → diagnose → fix → PR |
| **2** | **Signal-to-action (this RFC)** | live signals → triage → Dismiss / File / Escalate |
| **3** | Operational remediation (future) | act on prod/infra — restart, scale, config, redeploy |

**Fleet 2 never touches production and never fixes code** — it is pure
*signal → disposition*. Resolving a signal by changing prod is Fleet 3; by changing
code is Fleet 1.

## Proposal

### Scope — triage-only, forever
Three dispositions — **Dismiss** (false alarm/noise/resolved), **File** (genuine
defect → typed work item), **Escalate** (ambiguous/novel/no citable intent →
operator). Remediation is explicitly **Fleet 3**. The boundary, precisely: the
fleet **may write triage state to the monitoring tools** (ack / close / annotate /
silence) but **may never touch a production service**.

### Roles (mirrors RFC-0002)
- **Orchestrator** — *deterministic code*. Receives/polls triggers, runs the
  correlation queries, routes, writes dispositions to the ledger, creates issues.
  LLMs are leaf calls only.
- **Correlation-aware triager** — cheap LLM behind a `Triager` seam
  (harness-agnostic, Pi/opencode per the bake-off). Establishes context by
  **joining the queryable backends**, then emits a **structured disposition** and,
  on File, an **L1-candidate**.
- **Consumers** — Fleet 1 (subscribes to the `bug` label), the operator
  (`config-enhancement` items + escalations).
- **Operator** — gates; overturns a disposition via **GitHub label/comment**.

**Sacred rule (from RFC-0002):** no LLM decides pipeline control flow; the
orchestrator parses structured output and never scrapes prose.

### The seam to Fleet 1 + the intent gate (the core correctness mechanism)
Fleet 2's **File emits an L1-*candidate*, not a finished L1** — Fleet 1's triager
stays the **only normalizer** (two normalizers in sequence = double cost + a fight
over the problem statement). Two gates compose:
- **Fleet 2 gate — "is there a citable intent source?"** No → **Escalate, not File.**
- **Fleet 1 gate — "is acceptance oracle-statable?"** (RFC-0002's
  `actionable ⟺ oracle-can-exist`).

Every `acceptance` criterion in a File must carry a required **`intent_source`**:
*self-evident invariant* (a 5xx/crash — the app must not do this, no doc needed) ·
*SLO/error-budget* · *spec/ADR/PRD* · *prior-baseline window* · *operator rule*.
**Rationale (measured, Fleet-1 eval 2026-07-24):** a triager fed only
system-derived evidence produced confidently-wrong acceptance that cost **more**
than a raw garbage ticket (782s/231k tok vs 617s/133k) and **never fired
`needs-info` in two calls**. Correlation proves *what happened*, never *what was
intended* — so the schema forces the citation. This is the single
highest-leverage rule in the design. A self-evident invariant is an acceptance
**floor**, not the whole acceptance: "no 5xx" as full acceptance invites
symptom-suppression (swallow the exception, return 200 — the crash is gone, the
defect is not; rule 0.7), so Fleet 1's triager still owes the positive *"what
should it do instead?"* or fires `needs-info`.

### Dispositions compose + the filed-work taxonomy (the label is the router)
Dispositions are **not mutually exclusive**: one signal may yield an **immediate
action and a follow-up artifact** (e.g. a miscalibrated-but-real alert →
Dismiss+recommendation *now* **and** File a `config-enhancement` *follow-up*). When
the fleet Files, it creates a **typed** work item and the **label routes it**:

| Label | Consumer |
|---|---|
| `bug` | **Fleet 1** (bug-fixing) |
| `config-enhancement` | **operator** backlog (future Fleet-3-adjacent) — never Fleet 1 |

RFC-0002's fleet triggers on the **`bug` label only**, so non-bug types are
invisible to it for free. The taxonomy grows as new work-types recur.

### Triggers + correlation (grounded against the o11y recon, 2026-07-24)
**Two triggers:** **Grafana Alerting** (trigger-ready today — outbound webhook
contact points, or poll the Alerting API) and **GlitchTip** (errors/regressions).
As a Sentry fork, GlitchTip ships the **Sentry-compatible REST API** (`/api/0/…`,
token auth — reads *and* writes), so it supports a poll-trigger **and** the
**Dismiss write-back** (close/ack) — **unverified on-prem and not wired in-repo;
one `curl` to `homelab:8090/api/0/projects/` confirms** (open question).

**Correlation is a query-time join, not pre-wired links.** The triager joins the
three queryable backends on host **`homelab`** — **VictoriaMetrics** (PromQL,
`homelab:8428`), **VictoriaLogs** (LogsQL, `homelab:9428`), **VictoriaTraces**
(Jaeger/Tempo, `homelab:10428`), all tailnet / no-auth — on shared keys (`job`,
`instance`, time-window, `trace_id`). *Host (resolved 2026-07-24):* the o11y stack
runs on **`homelab`** (Mac mini); Phase-0 confirmed it live (`dgx-llm-1:*` dead),
so the DGX→mini migration is done. Bind to `homelab:<port>`. The pre-wired pivots mostly **do not exist yet** (only a
conditional logs→traces derived field); **building them** (metrics→traces
exemplars, confirmed `trace_id`-in-logs) are themselves `config-enhancement`
filings — the design is self-improving.

### State + idempotency
A **local append-only ledger** keyed
`signal_fingerprint → disposition → prompt+model version → timestamp`. Pre-File the
primary object does not exist on GitHub (labels can't carry pre-File state) and
source-native status is human-writable (idempotency breaks on a human click), so
the ledger owns pre-File state; GitHub `flow:` labels take over post-File. The
ledger **doubles as the overturn-feedback dataset**. The **version stamp is
mandatory** — the triager prompt is a config factor (BAKEOFF §4.3), so the overturn
metric is unattributable without it. **Dismiss-overturn surface:** a Dismiss has no
GitHub object, so GH-label overturn covers File only. In propose-first mode the
declined proposal is the surface; once Dismiss is autonomous, overturn is detected
**implicitly** — the same `fingerprint` re-firing hot after a Dismiss, or a human
re-opening the GlitchTip issue — and appended to the ledger with no new UI.

### Autonomy
The fleet proposes; the operator gates. **Dismiss = propose-first** (operator
one-click) until the **overturn rate is measured near zero**, then flip to
autonomous — the Fleet-1 triager passed every mechanical shape-check while being
semantically wrong twice, so shape-valid ≠ correct. **File = autonomous** (a bad
issue is cheap and double-gated downstream). **Escalate = operator.** **Nothing
touches production.**

### Observability of the fleet itself
Langfuse traces every triager leaf call (model/tokens/cost — doubles as a model
bake-off axis, like RFC-0002); the fleet's own errors go to GlitchTip; a Grafana
panel shows dispositions over time and the **overturn rate = the trust metric**.
Secrets via **sops/age**.

## Phased rollout (baseline: orrery → podcast)
- **Phase A — orrery (prove the plumbing).** Thinnest but cleanest slice: the
  **launch-data-stale** Grafana alert as trigger + queryable VictoriaLogs/Metrics
  for correlation. No traces/errors/UX. Proves trigger → query → disposition →
  File/Dismiss end-to-end cheaply. (Orrery's public browser errors can't reach the
  tailnet-only GlitchTip, so the GlitchTip trigger arrives in Phase B.) Does **not** validate
  the `bug`→Fleet-1 seam — the staleness alert's natural disposition is
  `config-enhancement`/Dismiss, not `bug`; that seam is proven in Phase B.
- **Phase B — podcast (prove correlation + the GlitchTip trigger).** Richest
  surface — errors (GlitchTip trigger) + traces (VictoriaTraces) + metrics —
  exercises the full error→trace→metric chain.
- **Later.** UX/Umami correlation (ingress wired by another agent, issue #8);
  building the missing correlation links; then Fleet 3 (remediation) as its own
  project, subscribing to `config-enhancement`.

The concrete MVP build order + first vertical slice (orrery staleness alert →
correlate → File/Dismiss) live in [`signal-fleet/SIGNALS.md`](https://github.com/chipi/agentic-ai-homelab/blob/main/signal-fleet/SIGNALS.md)
§13, along with the reuse map from Fleet 1's orchestrator.

## Go-live (added 2026-07-25 — quality bar passed, rollout gated)

The triager's quality bar — **false-dismiss = 0 AND escalate ≤5%, both at
once, k≥3** — is **passed** (v4-pro + prompt `c2ece738`: 0/27 + 0/9
false-dismiss across two fixture sets; escalate 0.045/0.048). The fleet's
success metric in production is **handled-rate** (signals correctly disposed
without the operator), with escalations required to be *unique* — a
recurring escalation class is a missing rule, converted via the weekly
review into an `operator-rule` intent source + fixture (compounding
autonomy).

Rollout is three stages, promotion **per disposition-class and reversible**:
**shadow** (daemon decides, acts on nothing, 1–2 weeks — the shadow ledger
is the real-world labeled dataset) → **propose-first** (daily digest,
one-click approval, timeout-approval; operator clicks feed the overturn
metric) → **autonomy by class** (cleanup-with-marker first, then
dismiss-with-evidence, then File; escalate stays human forever).

Remaining gate items before shadow (occurrence-churn fix, recurrence dedup,
daemon, digest) and the full tick list live in the master rollout plan:
[`docs/wip/fleet-rollout-plan.md`](https://github.com/chipi/agentic-ai-homelab/blob/main/docs/wip/fleet-rollout-plan.md)
(Track A). Fleet 2 rolls out independently of Fleet 1.

## Open questions
1. **Filed-work taxonomy** — final label names + full starter set.
2. **Trigger wiring** — **first verify the GlitchTip API on-prem** (one `curl` to
   `homelab:8090/api/0/projects/` — settles both the trigger and the Dismiss
   write-back). Then: Grafana (webhook receiver via Funnel like RFC-0002's App, vs
   poll the Alerting API); GlitchTip (notification webhook → fleet endpoint vs poll
   the REST API). RFC-0002's webhook infra is a reuse candidate.
3. **Correlation-link prerequisites** — confirm apps emit `trace_id` in logs;
   metrics→traces exemplars; traces→logs reverse pivot.
4. **Triager harness/model** — reuse the bake-off's winner, or run its own study?
5. **Feedback-loop training** — overturn *mechanism* is decided (GH label/comment);
   how corrections re-train the triager (prompt/context vs a labeled example set)
   is open.
6. **Intent-source registry** — the canonical `intent_source` values + where each
   is looked up (SLO store? ADR index? baseline query?).

## Alternatives considered
- **Fleet 2 emits a finished L1** — rejected: double normalization + a fight over
  the problem statement; Fleet 1 re-triages every `bug` anyway. Fleet 2 emits an
  L1-candidate; Fleet 1 owns the gate.
- **GlitchTip as the primary/only programmatic source** — rejected as *primary*
  (Grafana Alerting is the ready trigger), but GlitchTip *is* a co-trigger and
  Dismiss write-back via its Sentry-compat REST API (reads+writes) once verified
  on-prem — not UI-only.
- **Classify monitoring-config work as `bug`** — rejected: pollutes Fleet 1;
  `config-enhancement` keeps it operator-owned and invisible to the fix fleet.
- **LLM orchestrator** — rejected: deterministic control loop, LLM at leaves (RFC-0002).
- **Source-native / GitHub-label state store** — rejected: no pre-File object;
  human-writable status breaks idempotency → local append-only ledger.
- **Autonomous Dismiss from day 1** — rejected: shape-valid ≠ correct → propose-first.
- **Fold remediation in** — rejected: separated to Fleet 3 (permanent boundary).

## Discussion
- **2026-07-24 (initial):** Designed interactively in `signal-fleet/SIGNALS.md`,
  reviewed by the Fleet-1 (bake-off) agent — six findings folded (intent gate,
  single-normalizer L1-candidate, monitoring-vs-prod boundary, local ledger,
  propose-first Dismiss, version stamp), and grounded against an o11y-stack recon.
  Locked: three-fleet separation, triage-only-forever, two triggers (Grafana +
  GlitchTip), correlation as a query-time join over VM/VL/VT, the intent gate,
  the L1-candidate seam, local-ledger state, propose-first Dismiss, staged
  orrery → podcast. Deferred to build/measurement: trigger-wiring choice,
  correlation-link prerequisites, triager harness/model, feedback-training
  mechanism, intent-source registry.
- **2026-07-24 (round-2 review):** Five further findings from the Fleet-1 agent,
  all folded: GlitchTip Sentry-compat REST API reconciled (a trigger **and**
  Dismiss write-back, not UI-only — unverified on-prem, curl to confirm);
  Dismiss-overturn surface specified (implicit, via signal-recurrence / human
  reopen against the ledger fingerprint); self-evident invariant marked an
  acceptance **floor** (Fleet 1 still owes positive acceptance or fires
  `needs-info`); correlation host pinned `homelab` + DGX→mini migration caveat;
  Phase A flagged as not validating the `bug`→Fleet-1 seam.
