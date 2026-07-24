# SIGNALS.md — Signal-to-Action Fleet (north star)

**Status:** Brainstorm / living design doc (pre-RFC)
**Date started:** 2026-07-24
**Relates to:** [RFC-0002 — autonomous bug-fix fleet](../docs/rfc/RFC-0002-autonomous-bug-fix-fleet.md)
(this fleet is RFC-0002's own **Phase 3 — "o11y-reactive agents (alerts →
diagnose/propose)"**, promoted to its own project). Will crystallize into
**RFC-0003** once the design is worked out here — the same way `BAKEOFF.md`
sat under RFC-0002.

> This is the **living brainstorm doc** — architecture, design, open questions,
> decisions. We write everything here; the RFC is the crystallized surface.
> Mirror of `bugfix-fleet/BAKEOFF.md`. Sections marked **OPEN** are undecided —
> nothing there is invented, it is a question waiting on a decision.

---

## 1. The three-fleet separation of concerns

Top-level separation locked 2026-07-24. Each fleet has one job; they chain.

| # | Fleet | Job | Status |
|---|---|---|---|
| **1** | **Bug-fixing fleet** | Behavior/code issues → diagnose → fix → PR (operator gates merge) | RFC-0002, Phase 0 bake-off in progress |
| **2** | **Signal-to-action fleet** *(this doc)* | Live production signals → **triage** → Dismiss / File / Escalate | design starting here |
| **3** | **Operational remediation fleet** | Act on prod/infra (restart, scale, config, redeploy) | **future project — explicitly out of scope here** |

The boundary that matters: **Fleet 2 never touches production and never fixes
code.** It decides *what a signal means* and *where it should go*. Anything that
resolves a signal by changing prod is Fleet 3; anything that resolves it by
changing code is Fleet 1. Fleet 2 is pure **signal → disposition**.

---

## 2. Charter — what this fleet is, and is NOT

**Is:** the automated triage layer between the monitoring stack (GlitchTip,
Grafana, UX analytics) and the operator. It closes false alarms, cleans up the
mess, and turns genuine defects into clean, actionable work.

**Scope = triage-only, forever.** Not a v1 limitation — a permanent boundary.
Three dispositions only:

- **Dismiss** — false alarm / known noise / already-resolved. Close it, log why.
- **File** — a genuine behavior/code defect → emit an L1-quality issue for Fleet 1.
- **Escalate** — genuinely ambiguous, novel, or high-stakes → the operator.

**Is NOT:** remediation (Fleet 3), code-fixing (Fleet 1), or a decision-maker on
prod state. **The boundary, precisely** (review item 3): it **may write triage
state to the monitoring tools** — ack / close / annotate / silence an alert or
error — but it **may never touch a production service**. Writing "handled" back
to GlitchTip is in scope; changing what the monitored app does is not (that is
Fleet 1 or Fleet 3).

---

## 3. Why it exists — closing the gap

Today the signal firehose lands entirely on the operator. That does not scale and
cannot be assumed. GlitchTip fills with errors, Grafana alerts fire, UX analytics
show drop-offs — and there is no automated answer to *"so what do we do with
this?"*. The gap this fleet closes:

- **False alarms** pile up and bury the real signals → Dismiss, with reasoning.
- **Real defects** sit un-triaged, or reach Fleet 1 as garbage tickets that the
  bake-off proved will fail or grind expensively → File as L1-quality problems.
- **The genuinely-hard** get a human, not a silent guess → Escalate.

---

## 4. The seam to Fleet 1 (the chain that makes this worth building)

RFC-0002's active triager consumes a **`bug`-labeled GitHub issue** carrying an
**L1 problem-template**: symptom · expected behavior + **acceptance criteria** ·
evidence · area · repo-only domain facts (RFC-0002 §Roles; BAKEOFF §6.1–6.3).

**Fleet 2's `File` emits an L1-*candidate*, not a finished L1 — Fleet 1's triager
stays the only normalizer** (review item 2: two normalizers in sequence = double
cost + a fight over the problem statement, and Fleet 1 re-triages every `bug`
issue anyway). The candidate is: best-effort template + **mandatory
correlated-evidence links** + **mandatory intent-source citations** (§4.1). Fleet 1
owns the final acceptance and the oracle gate.

```
[GlitchTip / Grafana / UX signal]
        │
        ▼
  Signal-to-Action Fleet  ──Dismiss──▶ monitoring state closed, logged
        │                 ──Escalate─▶ operator
        │ File
        ▼
  bug-labeled issue (L1-candidate:       ──▶  Bug-fixing Fleet (RFC-0002)
  template + evidence + intent cites)          └─ triager owns final normalization
```

**Two gates, one per fleet — they compose:**
- **Fleet 2's gate — "is there a citable intent source at all?"** No citable
  intent ⇒ **Escalate, not File** (§4.1). Cheap filter; plays to what correlation
  actually gives — evidence + intent *gathering*, not acceptance *authoring*.
- **Fleet 1's gate — "is acceptance statable into an oracle?"** The final
  authoring (RFC-0002's `actionable ⟺ oracle-can-exist`).

**The bake-off proved the load-bearing fact:** triage/evidence quality dominates
model strength — a weak ticket fails even a strong model. But the same eval also
proved the inverse danger (§4.1): a *confidently-wrong* ticket costs **more** than
a garbage one. So Fleet 2's job is to be excellent at **evidence + intent
gathering** and to escalate rather than invent. It is the active-triage stage of
the bake-off, sourced from production instead of replayed closed bugs.

### 4.1 The intent gate — acceptance must cite an intent source

**The measured hazard (Fleet-1 eval, 2026-07-24, review item 1):** a triager fed
only system-derived evidence produced a well-shaped L1 with **confidently-wrong
acceptance** (it demanded a pure Keplerian ellipse; the maintainer's real intent —
arrival-V∞-bent arcs — was unknowable from code/geometry alone). The worker leg on
that "clean" ticket cost **more** than the raw garbage baseline (782s / 231k tok
vs 617s / 133k) and still FAILed — and the triager **never fired `needs-info` in
two calls**, in a case built for it. Invented-wrong acceptance is poison with a
price tag.

**This fleet is *more* exposed:** its entire input is system-derived (traces,
metrics, UX events). **Correlation can prove what happened; it cannot recover what
was intended.**

**The gate (structural — a required schema field, not a prompt nicety):** every
`expected` / `acceptance` criterion in a File must carry an **`intent_source`**:

| intent_source | example |
|---|---|
| **self-evident invariant** | a 5xx, a crash, a null-deref, an unhandled rejection — the app must not do this (operator rule 0.7). *No external doc needed.* |
| **SLO / error budget** | "p95 latency < 300ms", "availability ≥ 99.9%" |
| **spec / ADR / PRD** | a documented intended behavior |
| **prior-baseline window** | "p95 was 120ms for the last 30d" (regression vs measured normal) |
| **operator rule** | a standing operator preference / decision |

**No citable intent source ⇒ Escalate, not File.** Models do not fire the "I
don't know" valve voluntarily (measured), so the schema forces it. This is
Fleet 2's half of the two-gate split and the single highest-leverage rule in the
doc. The **self-evident invariant** row stops obvious crashes over-escalating: a
5xx cites itself as intent and Files cleanly; only genuinely *"is this even
wrong?"* cases escalate.

**A self-evident invariant is an acceptance *floor*, not the acceptance (R2-3).**
"No 5xx" justifies the *File decision*, but as the *whole* acceptance it invites
symptom-suppression — swallow the exception, return 200/empty; the crash is gone,
the defect is not (operator rule 0.7). So the L1-candidate marks it as a **floor**,
and Fleet 1's triager still owes the positive *"what should it do instead?"* — if
that is unanswerable, its own `needs-info` fires. This keeps Fleet 2 from
laundering symptom-level acceptance through Fleet 1.

---

## 5. Architecture — replicated from RFC-0002 (this is "another version" of it)

The shared agentic-fleet architecture is WIP; we **follow its patterns and keep
it in sync** as we build. Direct mapping:

| RFC-0002 pattern | Signal-to-action version |
|---|---|
| **Deterministic orchestrator**, LLMs at leaves only | same — poll/correlate/route is code; the model only classifies + drafts |
| **Active triager** (establishes context → normalizes → structured verdict) | **correlation-aware triager** (pivots across logs/metrics/traces/UX → disposition + L1-candidate draft) |
| Verdict `actionable / needs-info / reject` | disposition `File / Escalate / Dismiss` (structured JSON, never scraped) |
| Worker seam (`src/worker/types.ts`), harness-swappable | same `Triager` seam — harness-agnostic (Pi/opencode, whichever the bake-off picks) |
| State = GitHub `flow:` labels | **local append-only ledger** pre-File (signal-fingerprint → disposition → prompt+model version → ts); GitHub `flow:` labels take over post-File (§9) |
| Langfuse (leaf traces) · GlitchTip (errors) · Grafana panel | same — plus a **model bake-off axis** on the triager, like RFC-0002 |
| Runs on the homelab **Mac mini** (always-on, tailnet) | same host |
| Secrets via **sops/age** | same |
| Bounded loops, per-item budgets, kill switch | same |

**Sacred rule carried over:** no LLM decides pipeline control flow. The model
lives only behind the `Triager` seam (classify + draft). The orchestrator parses
structured output; it never scrapes prose.

---

## 6. Correlation-centric triage — the heart

The decisive design choice: **triage is decided from the correlated picture, not
a single signal.** The operator has already invested in bringing **logs +
metrics + traces** together (follow-and-investigate across sources); this fleet's
triager *uses that capability* rather than rebuilding it.

Worked example — the concrete pivot chain (grounded, recon 2026-07-24):

```
Trigger fires  (Grafana alert OR GlitchTip error/regression — §8)
  → extract: job · instance · alertname/error · time-window
  → VictoriaMetrics  GET :8428/api/v1/query           (PromQL — confirm metric shape)
  → VictoriaLogs     GET :9428/select/logsql/query     (LogsQL — logs for job/instance in window)
       → if a log line carries trace_id → VictoriaTraces :10428/select/jaeger/…  (failing span)
  → GlitchTip        — cross-check via Sentry-compat REST API (unverified on-prem — §8)
  ⇒ disposition from the WHOLE picture:
      • transient blip, already recovered, no impact      → Dismiss (+ rec if noisy)
      • real regression, traceable + acceptance-statable  → File (L1-candidate)
      • novel / broad blast radius / no citable intent    → Escalate
```

**How correlation actually works here — a query-time join, not pre-wired links.**
The three backends are directly queryable on the tailnet (no auth), host
**`homelab`**: VictoriaMetrics (PromQL, `homelab:8428`), VictoriaLogs (LogsQL,
`homelab:9428`), VictoriaTraces (Jaeger/Tempo, `homelab:10428`). The triager
**joins them on shared keys** — `job`, `instance`, time-window, and `trace_id`
when present. That join *is* the correlation; done at query time by the triager,
not by following pre-built pivots. **Host (R2-4, resolved 2026-07-24):** the o11y
stack runs on **`homelab`** (the Mac mini) — Phase-0 confirmed `homelab:*` live and
`dgx-llm-1:*` dead, so the DGX→mini migration is done. Bind to `homelab:<port>`.

**Correlation substrate — what exists vs what's missing (a prerequisites list,
recon 2026-07-24).** The pre-wired links are mostly *not built yet*:
- ✅ **logs→traces**: a Grafana `derivedFields` regex extracts `trace_id` from log
  lines → click-through to VictoriaTraces — **conditional** on apps emitting
  `trace_id` in logs, which no doc confirms today.
- ✗ **metrics→traces exemplars** — not provisioned.
- ✗ **traces→logs** reverse pivot — not provisioned.
- ✗ **GlitchTip→traces** — trace sampling disabled in GlitchTip, so errors carry
  no trace id (no error→trace link). *(GlitchTip does expose the Sentry-compat
  REST API for reads/writes — R2-1, §8 — so this is a missing correlation link,
  not a missing API.)*

Consequence: the triager relies on shared-dimension joins, not link-following —
and *building the missing links* (exemplars, confirmed `trace_id`-in-logs,
GlitchTip programmatic access) are themselves **`config-enhancement`** items this
fleet would file (§7.2). The design is self-improving.

---

## 7. Disposition taxonomy (definitions + evidence bar)

| Disposition | Trigger | Evidence required | What gets written |
|---|---|---|---|
| **Dismiss** | false alarm, known noise, already-resolved, no user impact | the correlated picture shows no real/ongoing defect | close/ack on the source + a logged reason (auditable) |
| **File** | genuine behavior/code defect, acceptance-statable | reproducible-enough that an oracle can exist (RFC-0002 gate) | `bug`-labeled issue, L1 template, links to the correlated evidence |
| **Escalate** | ambiguous, novel, high blast radius, or acceptance not statable | — (that's the point) | operator ping with the correlated summary |

**RESOLVED (2026-07-24) — the "Tune" boundary is a *dual* output, not a choice.**
A miscalibrated-but-real alert gets **both**:
- **Immediate:** **Dismiss + recommendation** — quiet the noise now, log the
  suggested fix ("alert noisy, suggest threshold X / add dedup on Y").
- **Follow-up:** **File** it as a **`config-enhancement`** work item — so the
  root cause gets structurally solved long-run. The **operator** (not Fleet 1)
  owns these.

This forces two structural additions (§7.1, §7.2): **dispositions can compose**
(one signal → an immediate action *and* a follow-up artifact), and a **filed-work
taxonomy** where the label routes the item to the right consumer. Crucially a
`config-enhancement` is **not a bug** — it must stay invisible to the bug-fixing
fleet.

### 7.1 Dispositions can compose

Dispositions are **not mutually exclusive**. A single signal may yield an
**immediate action** *and* a **follow-up artifact** at once — the Tune case
(Dismiss-now + File-config-later) is the first example. The orchestrator emits a
*set* of outputs per signal, not a single verdict: the immediate action clears
the live noise; the follow-up captures the structural work so it is not lost.

### 7.2 Filed-work taxonomy — the label is the router

When the fleet **Files**, it creates a **typed** work item, and the **type
(label) routes it** to the right consumer. This is what keeps the fleets
decoupled — each consumer subscribes only to its own label(s).

| Label | Meaning | Consumer |
|---|---|---|
| `bug` | behavior/code defect, acceptance-statable | **Fleet 1** (bug-fixing, RFC-0002) |
| `config-enhancement` | monitoring/infra config improvement (root-cause a noisy alert: threshold, dedup, sampling) | **operator** backlog (future **Fleet 3**-adjacent) — **never** Fleet 1 |

**Guard:** RFC-0002's fleet triggers on the **`bug` label only** ("Epics/stories/
other issues are invisible") — so `config-enhancement`, and every future non-bug
type, is *already* invisible to it. The taxonomy leans on that existing guard.

**This taxonomy will grow.** `bug` and `config-enhancement` are just the first
two; expect more work-types as signals teach us what recurs (perf,
ux-regression, data-quality, security, docs…). Establishing and evolving this
taxonomy is an **explicit part of this fleet's design** — each new type is added
here and names its consumer. **OPEN:** final label names (`config-enhancement`
vs `config-improvement` vs a `config:*` namespace) + the full starter set.

---

## 8. Signal sources (grounded — recon 2026-07-24)

> **Phase 0 complete (2026-07-24):** every surface below is **proven consumable**
> with live data via each platform's prescribed API — see
> [`PHASE-0-infra.md`](PHASE-0-infra.md). The stack is on `homelab` (mini). The
> `homelab:8090` host caveat (R2-4) is resolved: the migration is done.

**Two triggers: Grafana Alerting *and* GlitchTip** (operator, 2026-07-24). Grafana
Alerting is trigger-ready today (outbound webhook contact points; or poll the
Alerting API). **GlitchTip triggers too** — on new errors / regressions. As a
Sentry fork it ships the **Sentry-compatible REST API** (`/api/0/projects/…`,
token auth — reads *and* writes: list / update / resolve), so it supports both a
poll-trigger **and** the **Dismiss write-back** (close/ack). **Unverified against
the on-prem instance and not wired in-repo — one `curl` with a token against
`homelab:8090/api/0/projects/` confirms it (R2-1, §12), and should happen before
Phase-B wiring since it decides both the trigger and the Dismiss-writeback
design.** The Victoria\* backends stay pull-only correlation inputs.

| Source | Role | Interface | Verdict |
|---|---|---|---|
| **Grafana Alerting** | **trigger** (metric/log alerts) | outbound webhook contact point, or poll Alerting API | ready — fires on `up==0`, disk, FastAPI 5xx, **orrery launch-data stale** (`rules.yaml`) |
| **GlitchTip** | **trigger** (errors/regressions) **+ correlation input + Dismiss write-back** | Sentry-compat REST API (`homelab:8090/api/0/…`, token; reads+writes) or notification webhook | **wiring prereq** — API unverified on-prem, not wired in-repo (R2-1) |
| **VictoriaMetrics** | correlation input | PromQL `GET :8428/api/v1/query` (tailnet, no auth) | **queryable** |
| **VictoriaLogs** | correlation input | LogsQL `GET :9428/select/logsql/query` | **queryable** |
| **VictoriaTraces** | correlation input | Jaeger/Tempo `:10428/select/…` | **queryable** |
| **UX / Umami** | correlation input (later) | not receiving data yet — ingress pending (issue #8); **being wired by another agent** | **not-yet-wired** — designed-in, not a baseline blocker |

**Baseline staging (operator, 2026-07-24): orrery → podcast.**
- **Phase A — orrery (prove the plumbing).** Thinnest surface, a *clean* slice:
  the **launch-data-stale Grafana alert** as trigger + fully-queryable
  **VictoriaLogs / VictoriaMetrics** for correlation. (Orrery's public browser
  errors can't reach the tailnet-only GlitchTip — its project holds only
  test/telemetry events — so the **GlitchTip trigger comes online at Phase B**,
  where podcast's server-side errors actually land.) Proves trigger → query →
  disposition → File/Dismiss end-to-end cheaply. **Caveat (R2-5): the staleness
  alert's natural disposition is `config-enhancement`/Dismiss, not `bug` — so
  Phase A does NOT validate the `File → bug → Fleet 1` seam.** That arrives with
  Phase B errors (or a synthetic error injected earlier if the seam needs proving
  sooner).
- **Phase B — podcast (prove correlation + the GlitchTip trigger).** The richest
  surface — errors (GlitchTip **trigger**), traces (VictoriaTraces), metrics —
  exercises the full error→trace→metric chain the design rests on.

**Monitored surfaces:** orrery (baseline), then podcast player + operator surfaces.

---

## 9. State & idempotency

The fleet must remember **what it already triaged and how**, so a re-poll doesn't
re-litigate the same GlitchTip issue every cycle. Same shape as the bake-off's
append-only ledger.

Plus a **feedback loop**: when the operator overturns a Dismiss (it was real) or
rejects a File (it was noise), that correction has to be captured and teach the
triager (prompt/context, or a labeled example set).

**The Dismiss-overturn surface (R2-2) — the trust metric needs a data source in
autonomous mode.** GitHub label/comment overturn (§10) only works for **File** (it
has a GitHub object); a **Dismiss** has no GitHub object — it lives only in the
ledger + closed monitoring state. So:
- **Propose-first Dismiss:** the proposal *is* the surface — the operator declines,
  the orchestrator records the overturn.
- **Autonomous Dismiss:** the surface would otherwise vanish exactly when the
  overturn rate still gates autonomy (§10). Fix: **implicit overturn** — the same
  signal `fingerprint` re-firing hot after a Dismiss, or a **human re-opening** the
  GlitchTip issue (via the Sentry-compat API, §8), is machine-detectable and
  appends an overturn event to the ledger with **zero new UI**. The fingerprint
  the ledger already carries is the hook.

**RESOLVED (2026-07-24, review item 4) — a local append-only ledger.**
Reasoning: pre-File the primary object does not exist on GitHub, so labels
**cannot** carry pre-File state; GlitchTip-native status is human-writable, so
idempotency breaks the first time a human clicks *resolve*, and it covers only
one of three sources. The ledger is keyed:

    signal_fingerprint → disposition → prompt+model version → timestamp

It is the bake-off's `runs.tsv` with a different schema — a proven shape — and it
**doubles as the overturn-feedback dataset** for the loop above, for free. GitHub
`flow:` labels take over only **after** File, where RFC-0002's state machine
already owns them.

**Version stamp (review item 6a):** the `prompt+model version` in the key is
mandatory. The triager prompt is a config factor (BAKEOFF §4.3: a prompt change =
a new grid row, results not comparable across versions) — without the stamp the
overturn metric (§11) is unattributable.

---

## 10. Autonomy stance

Carried from RFC-0002: **the fleet proposes; the operator gates.** Mapped to
dispositions by blast radius:

- **Dismiss** — low blast radius, reversible, fully logged/auditable, **but**
  RESOLVED (2026-07-24, review item 5) to **propose-first**: the Fleet-1 triager
  passed *every* mechanical shape check while being semantically wrong twice in
  two calls — shape-valid ≠ correct. Run Dismiss as operator one-click until the
  **overturn rate is measured near zero over a real window**, then flip to
  autonomous. The ledger (§9) supplies that measurement — and §9 specifies the
  **Dismiss-overturn surface** (implicit, via signal-recurrence / human-reopen)
  that keeps feeding it once Dismiss is autonomous.
- **File** — creates a GitHub issue. Cheap, reviewable, non-destructive →
  autonomous is reasonable (a bad issue is a cheap mistake and Fleet 1 + operator
  gate downstream anyway).
- **Escalate** — by definition to the operator.
- **Nothing touches prod.** That's Fleet 3, and it is not in this fleet.

---

## 11. Observability of the fleet itself (the loop closes on itself)

- **Langfuse** — every triager leaf call traced (model/tokens/cost/latency).
  Doubles as a **model bake-off axis** — which cheap model triages reliably,
  same as RFC-0002's harness/model study.
- **GlitchTip** — the fleet's own errors.
- **Grafana panel** — dispositions over time (Dismiss/File/Escalate counts,
  overturn rate = the trust metric).

---

## 12. Open questions (consolidated)

1. **Filed-work taxonomy** (§7.2) — final label names + full starter set. *(Tune
   boundary resolved; taxonomy is a living part of the design.)*
2. **Trigger wiring** (§8) — **first, verify the GlitchTip API (R2-1):** one
   `curl` with a token to `homelab:8090/api/0/projects/` settles whether the
   Sentry-compat REST API (reads+writes) is live on-prem — it decides the GlitchTip
   trigger *and* the Dismiss write-back; reconcile §6/§8 to the result. Then:
   *Grafana Alerting* — webhook receiver (Funnel, like RFC-0002's App) vs poll the
   Alerting API; *GlitchTip* — notification webhook → fleet endpoint vs poll the
   REST API. RFC-0002's webhook infra is a reuse candidate for both.
3. **Correlation-link prerequisites** (§6) — confirm apps emit `trace_id` in logs;
   metrics→trace exemplars; traces→logs reverse pivot. Each is a candidate
   `config-enhancement` filing.
4. **Triager harness/model** — reuse the bake-off's winner, or its own study?
5. **Feedback-loop training** (§9) — overturn *mechanism* resolved (GH
   label/comment); how corrections re-train the triager (prompt/context vs a
   labeled example set) is open.
6. **Intent-source registry** (§4.1) — the canonical list of `intent_source`
   values + where each is looked up (SLO store? ADR index? baseline query?).

*Resolved since first draft:* Tune boundary (§7, dual output), state store (§9,
local ledger), autonomous Dismiss (§10, propose-first), naming (`SIGNALS.md` /
`signal-fleet/` / RFC-0003), **primary trigger** (§8, Grafana Alerting),
**correlation interfaces** (§6, VM/VL/VT query APIs), **first surface** (§8, staged
orrery → podcast), **overturn mechanism** (§9, GH label/comment), **signal scope**
(reactive-only), **UX** (designed-in, wired by another agent).

---

## 13. MVP — first end-to-end slice (the build plan)

**Goal:** the smallest end-to-end loop that proves the spine — one real orrery
signal → correlate → disposition → act (File / Dismiss / Escalate) — running on
the homelab. Phase-0 ([`PHASE-0-infra.md`](PHASE-0-infra.md)) already proved every
surface is consumable, so the MVP is the orchestrator + triager on top. This fleet
is "another version" of Fleet 1 (RFC-0002), so we **reuse its scaffolding**
wherever possible (§13.4).

### 13.1 Decisions to lock first
1. **Trigger mode (v1):** **poll** — the orchestrator polls the Grafana
   Alertmanager API + the GlitchTip issues API on an interval. Simplest (no
   ingress/ACL); the Phase-0 webhook receiver stub is kept for the low-latency
   upgrade later.
2. **Triager harness/model:** reuse the bake-off's winner + the cheap model that
   triages reliably — do not re-run that study.
3. **File target:** the GitHub repo the fleet opens issues in + the label set
   (`bug` → Fleet 1, `config-enhancement` → operator). **OPEN:** the target repo
   (orrery's own vs a dedicated fleet-issues repo).
4. **Host:** the orchestrator runs on the **mini** (same box as Fleet 1 and every
   source → localhost reads, no ACL).

### 13.2 Build order (each step small)
1. **Orchestrator skeleton** — deterministic poll loop on the mini; reuse Fleet-1's
   worker seam + Langfuse + GitHub App (§13.4).
2. **Ledger** — append-only `signal_fingerprint → disposition → prompt+model
   version → timestamp` (idempotency + the overturn dataset, §9). Fleet-1's
   `runs.tsv` with a new schema.
3. **Correlation module** — turn the Phase-0 curls into code: given a signal, query
   VM/VL/VT (§6) → an evidence bundle.
4. **Triager** — structured output (disposition + L1-candidate + `intent_source`,
   §4.1). Reuse Fleet-1's structured-output-with-retry harness (§13.4).
5. **Action handlers** — Dismiss (ledger, propose-first, §10), File (labeled GitHub
   issue → chains to Fleet 1 at the seam, §4), Escalate (operator ping).
6. **Observability** — Langfuse traces on the triager calls + a Grafana panel
   (disposition counts + overturn rate = the trust metric, §11).

### 13.3 First vertical slice (the "Flow A" of RFC-0002)
The **orrery launch-data-stale** Grafana alert → correlate the refresh logs in
VictoriaLogs → triager → **File a `config-enhancement`** issue *or* **Dismiss**.
One path, fully end-to-end. Deliberately *not* the `bug` seam (Phase A doesn't
exercise it, §8) — that arrives with Phase B (GlitchTip errors + trace
correlation). Success = the loop runs unattended on the real alert and produces
the right disposition with a citable intent.

### 13.4 Reuse from Fleet 1 (RFC-0002 orchestrator) — mapped

Recon of the live `bugfix-fleet/` (2026-07-24): it's further along than assumed —
a real TypeScript service (`src/orchestrator.ts`, `src/main.ts`) *and* a bash
control loop (`bakeoff/orchestrate.sh`). Ranked lifts, most valuable first:

| # | Reuse | Where (`bugfix-fleet/`) | Verdict | For the signal fleet |
|---|---|---|---|---|
| 1 | **Worker seam** | `src/worker/types.ts` | lift pattern | define `SignalTriageTask`/`SignalActionTask` + a `SignalWorker`; orchestrator never talks to LLMs directly |
| 2 | **Structured output + validate-retry** | `src/worker/directAdapter.ts` (`parseVerdict` + 3-retry) · `schemas.ts` (`TRIAGE_SCHEMA`) | **lift as-is** | the *working* reference (pi/opencode adapters are still `throw "not implemented"`); copy the retry loop, `response_format: json_object`, comment-free-schema tip |
| 3 | **Intent-source gate (deterministic)** | `bakeoff/triage_run.sh:176` → `orchestrate.sh:40-43` | **lift as-is** | our §4.1 gate exactly: prompt cites sources, **orchestrator mechanically counts uncited criteria → downgrades to needs-info, no LLM in the gate** |
| 4 | **Control loop** | `bakeoff/orchestrate.sh` (outer triage→reporter, inner action→kickback, bounded, `flow.tsv`) | adapt | swap ticket→signal, `triage_run.sh`→signal triager, `run.sh`→action executor; keep the bounded loops + state append |
| 5 | **LLM client + Langfuse** | `src/llm.ts` `orChat()` (auto-traced) | lift as-is | add `phase:"signal-triage"` → observable day 1 |
| 6 | **Ledger** | `runs.tsv`/`triage_runs.tsv`/`flow.tsv` (append-only, `prompt_ver` stamp) | lift pattern | our §9 ledger *is* this; add signal columns |
| 7 | **GitHub App** | `src/github/appAuth.ts`·`issueOps.ts`·`prOps.ts` | lift as-is | the **File** action = create a labeled issue via the existing App |
| 8 | **Reporter-oracle** | `bakeoff/reporter_answer.sh` + `reporter/*.md` | pattern | maps to our escalate-for-clarification: a signal-owner facts file answers needs-info |

**Two lessons that change our build:**
- **Structured output on cheap models is the stated risk** — the pi/opencode
  adapters are unimplemented; the **directAdapter (raw OpenRouter + validate-retry)
  is the only working path.** Start our triager there, not on a harness adapter.
- **The intent gate is a deterministic post-LLM check** (`orchestrate.sh:40-43`),
  not a prompt hope. Port it exactly.

**Vocabulary alignment:** Fleet-1's `agents/triage.md` (v2) intent_source enum is
`reporter | spec | repo-data | code-invariant | baseline` — its **`code-invariant`
= our self-evident invariant** (an acceptance *floor*, §4.1). Keep the vocab
shared across fleets; our signal-specific addition is `slo`/error-budget.

---

## 14. Discussion log

- **2026-07-24 (initial brainstorm):** Locked — three-fleet separation of
  concerns (bug-fix / signal-to-action / remediation); this fleet is
  **triage-only, forever** (Dismiss / File / Escalate), remediation split to a
  future Fleet 3. Determinism seam carried from RFC-0002 (LLM only behind a
  `Triager` seam); this is "another version" of the shared agentic-fleet
  architecture (WIP) and kept in sync. **Correlation across logs/metrics/traces/UX
  is the heart of triage**, reusing the operator's existing correlation
  investment. Chains to Fleet 1 at the GitHub-issue seam (File output = RFC-0002's
  bug-label input), which is exactly the bake-off's proven "triage quality is the
  lever." Deliverables: this living doc now, **RFC-0003** to crystallize later.
  The other agent reviews here too.
- **2026-07-24 (Tune boundary + taxonomy):** A real-but-miscalibrated alert gets
  a **dual output** — immediate Dismiss+recommendation *and* a follow-up `File`
  tagged **`config-enhancement`** (operator-owned, **not** a bug → invisible to
  Fleet 1 via its bug-only trigger). Two structural consequences added:
  **dispositions compose** (§7.1) and a **filed-work taxonomy where the label is
  the router** (§7.2), which grows as new work-types recur.
- **2026-07-24 (Fleet-1 architectural review folded in — `REVIEW-2026-07-24-fleet1-architectural.md`):**
  Six findings from the bake-off owner, all adopted. **(1)** Intent gate (§4.1):
  acceptance must cite an `intent_source` or Escalate — the measured
  confidently-wrong-acceptance hazard; added *self-evident invariant* as a
  first-class source so obvious crashes don't over-escalate. **(2)** Single
  normalizer: Fleet 2 emits an **L1-candidate** (evidence + intent cites), Fleet 1
  owns final acceptance; the two gates compose (§4). **(3)** Boundary fixed (§2):
  may write monitoring state, never touch production. **(4)** State store = local
  append-only ledger (§9). **(5)** Dismiss propose-first until overturn≈0 (§10).
  **(6a)** prompt+model version stamped on every disposition (§9). **(6b)** doc
  renamed `TRIAGE.md` → `SIGNALS.md` (avoids collision with Fleet 1's triager).
- **2026-07-24 (o11y grounding — recon over the handovers):** Concrete plumbing
  pinned. **Primary trigger = Grafana Alerting** (only source with outbound
  delivery); **GlitchTip is UI-only** (no agent API) → human cross-check, not a
  programmatic input. **Correlation = a query-time join** across the three
  queryable backends (VictoriaMetrics PromQL `:8428`, VictoriaLogs LogsQL `:9428`,
  VictoriaTraces Jaeger/Tempo `:10428`, tailnet no-auth) on shared keys
  (job/instance/window/trace_id) — the pre-wired links mostly don't exist yet
  (only a conditional logs→traces derived field), so building them is future
  `config-enhancement` work. Baseline staged **orrery → podcast** (Phase A proves
  plumbing on orrery's thin-but-clean staleness-alert slice; Phase B proves
  correlation on podcast's rich surface). Scope reactive-only; UX/Umami
  designed-in but wired by another agent (issue #8), not a baseline blocker.
- **2026-07-24 (correction — GlitchTip is also a trigger):** Not
  Grafana-Alerting-only. GlitchTip triggers on errors/regressions too; its trigger
  path needs wiring (notification webhook → fleet endpoint, or poll the
  Sentry-compat REST API — undocumented in-repo). Goes live at **Phase B**
  (podcast), where errors actually flow to GlitchTip; orrery (Phase A) has none.
  §8/§6/§12 updated.
- **2026-07-24 (Fleet-1 round-2 review folded — `REVIEW-…-fleet1-architectural.md`):**
  Five findings, all adopted. **(R2-1)** GlitchTip contradiction fixed: it *does*
  ship the Sentry-compat REST API (reads+writes) → trigger **and** Dismiss
  write-back — flagged unverified on-prem; one curl to `homelab:8090/api/0/`
  confirms (§8/§6/§12). **(R2-2)** Dismiss-overturn surface specified — implicit
  overturn via signal-recurrence / human-reopen against the ledger fingerprint,
  since a Dismiss has no GitHub object (§9/§10). **(R2-3)** self-evident invariant
  is an acceptance *floor*, not the acceptance — Fleet 1 still owes positive
  acceptance or fires needs-info, blocking symptom-suppression (§4.1). **(R2-4)**
  correlation host pinned `homelab` + DGX→mini migration caveat (§6). **(R2-5)**
  Phase A does not validate the `bug`→Fleet-1 seam (staleness → config/Dismiss);
  that's Phase B (§8).
- **2026-07-24 (Phase 0 proven + MVP plan):** Every surface confirmed consumable
  with live data via its prescribed API (`PHASE-0-infra.md`); stack confirmed on
  `homelab` (R2-4 resolved, migration done). Added **§13 MVP** — smallest
  end-to-end slice (orrery staleness alert → correlate VictoriaLogs → File
  `config-enhancement` / Dismiss), the 4 decisions to lock (poll-first trigger,
  reuse the bake-off model, file-target repo, mini host), and the build order.
  §13.4 (reuse from Fleet 1's orchestrator) to be detailed from the recon.
