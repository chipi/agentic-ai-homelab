# Architectural review of TRIAGE.md — from the Fleet-1 (bake-off) side

**Reviewer:** the agent building RFC-0002's bake-off + orchestrator MVP
(`bugfix-fleet/`), i.e. the owner of the seam this fleet feeds.
**Reviewed:** `signal-fleet/TRIAGE.md` as of 2026-07-24 (§1–§13).
**Standing:** operator-requested review. Comments ordered by how
load-bearing they are. Items 1–3 are contract-level; 4–6 are decisions on
your OPEN questions with reasons from measured Fleet-1 data.

The overall shape is right: the three-fleet separation is clean,
triage-only-forever is the correct permanent boundary, the deterministic
orchestrator rule carried over intact, and label-as-router with the
`bug`-only guard is exactly how the fleets stay decoupled. Nothing below
challenges the architecture's skeleton.

---

## 1. The seam contract has the acceptance epistemics backwards (measured today)

§4 has Fleet 2 emitting the *finished* L1 template. Fleet-1's intake eval
(2026-07-24, mission-arc-L0, flash triager — BAKEOFF §6.2/§6.3 context,
`docs/wip/bakeoff-handover.md` item 1d) measured what happens when a triager
derives acceptance from the *system* instead of from *intent*:

- The triager produced a well-shaped, well-researched L1 with **confidently
  wrong acceptance criteria** (it demanded a pure Keplerian ellipse; the
  maintainer's actual intent, encoded in the hidden oracle, is arrival-V∞-bent
  arcs — unknowable from the code/geometry alone).
- The worker leg on that triaged ticket cost **more than the raw garbage
  ticket** and still FAILed: 782s / 231k output tokens vs the L0 baseline's
  617s / 133k. Invented-wrong acceptance is not neutral — it is poison with
  a price tag.
- On kick-back the triager invented *again* (deeper diagnostics, still no
  V∞), and the round-1 worker leg FAILed again. **In two calls it never
  once fired the `needs-info` valve**, in a case purpose-built for it.

Your triager is *more* exposed to this failure, not less: its entire input
is system-derived evidence (traces, metrics, UX events). Correlation can
prove **what happened**; it cannot recover **what was intended**.

**Requested change (structural, not prompt-level):** every `expected` /
`acceptance` field in a File must **cite an intent source** — an SLO, a
spec/ADR, a prior-baseline window ("p95 was X for 30d"), or an operator
rule. No citable intent source → **Escalate, not File**. Force it in the
template/schema (a required `intent_source` per criterion), because the
measured fact is that models do not fire the "I don't know" valve
voluntarily. This is your equivalent of RFC-0002's
actionable ⟺ oracle-can-exist gate, and it is the single highest-leverage
line you can add to the doc.

## 2. Two normalizers own L1 quality — so neither does

Fleet 2 Files "exactly the template" (§4); Fleet 1's active triager then
re-triages every `bug` issue anyway — that is its job, and its kick-back
loop assumes it *authored* the acceptance it later sharpens
(`bugfix-fleet/agents/triage.md`, second pass). Two normalizers in
sequence = double cost and a fight over the problem statement when they
disagree.

**Recommendation:** Fleet 1's triager stays the **only normalizer**.
Fleet 2's File emits an **L1-candidate**: best-effort template +
**mandatory correlated-evidence links** + **mandatory intent-source
citations** (item 1). Fleet 1 owns the gate and the final acceptance.

This also discharges item 1 cleanly: Fleet 2 then needs to be excellent at
evidence + intent *gathering*, not acceptance *authoring* — which matches
what correlation actually gives you. Suggested doc change: §4's "emits
exactly that template and creates the issue" → "emits an L1-candidate
(template + evidence + intent citations); Fleet 1's triager owns final
normalization and the gate."

## 3. §2 contradicts §7 — fix the boundary wording now

§2: *"It proposes and routes; it does not act on the systems it watches."*
§7 Dismiss: *"close/ack on the source."* Closing a GlitchTip issue **is**
acting on a watched system.

The boundary you actually mean: **may write triage state to monitoring
tools** (ack / close / annotate / silence) — **may never touch production
services**. Say it explicitly, or Fleet 3's scope creeps in through the
Dismiss door and the "never touches production" claim stops being
auditable.

## 4. State store (§9 OPEN) — take the local append-only ledger

- Pre-File, the primary object does not exist on GitHub → labels cannot
  carry pre-File state.
- GlitchTip-native status is human-writable — idempotency breaks the first
  time a human clicks resolve — and covers only one of three sources.
- A ledger keyed `signal fingerprint → disposition → prompt+model version →
  timestamp` doubles as the overturn-feedback dataset (§9's loop) for free.

It is the bake-off's `runs.tsv` with a different schema — the shape is
proven. GitHub labels take over only after File, where RFC-0002's state
machine already owns them.

## 5. Autonomy (§10 OPEN) — propose-first for Dismiss, with data

Fleet-1's triager passed **every mechanical shape check while being
semantically wrong, twice in two calls**. Shape-valid ≠ correct. Run
Dismiss propose-first (operator one-click) until the overturn rate is
measured near zero over a real window, then flip to autonomous.
Autonomous File from day 1 is fine — a bad issue is cheap and double-gated
downstream (agrees with the doc's lean).

## 6. Smaller

- **Stamp prompt+model version on every disposition.** The triager prompt
  is a config factor (BAKEOFF §4.3: prompt changes = new grid row, results
  not comparable across them). The overturn metric is unattributable
  without the version stamp.
- **Filename:** `TRIAGE.md` will collide conceptually with Fleet 1's
  triager the day both are discussed in one thread — consider `SIGNALS.md`.
  Cosmetic; operator's call.

---

*Pointers for the measured claims: `bugfix-fleet/BAKEOFF.md` §6.2 (2×2
kick-back rule, orchestrator MVP), §6.3 ("Observed 2026-07-24" blocks: k=3
rates, fixmap experiment), §4.3 (prompt-as-config); artifacts under
`~/.bugfix-fleet/bakeoff/results/` (`triage_runs.tsv`, `runs.tsv`,
`orrery-mission-arc-L0-triage*/`).*

---

# Round 2 — re-review of `SIGNALS.md` (renamed) + `RFC-0003` (2026-07-24, operator-requested)

All six round-1 items adopted, correctly and with attribution. The
*self-evident invariant* intent source is an improvement beyond my
suggestion — it fixes the over-escalation problem I hadn't addressed. The
grounded o11y recon (§6/§8) and the RFC are consistent with each other.
New findings below; item 1 is load-bearing, the rest are holes or caveats.

## R2-1. GlitchTip API: the docs contradict themselves, and the fact is checkable in 2 minutes

Both docs simultaneously claim:
- §8 / RFC triggers: GlitchTip trigger via *"poll the Sentry-compatible
  REST API (`/api/0/projects/.../issues/`, `:8090`)"* — polling **is**
  reading;
- §6 pivot chain / RFC correlation / RFC alternatives-considered:
  *"GlitchTip … no agent query API (UI-only)"*.

Both cannot be true. To my knowledge GlitchTip, as a Sentry fork, ships
the Sentry-compatible REST API — reads *and* writes (issue list, update,
resolve) with token auth — I have not verified this against the on-prem
instance. Why it matters twice: (a) the **Dismiss disposition requires a
programmatic close/ack on GlitchTip** — if reads/writes were truly
UI-only, the Dismiss path is dead for the error source entirely; (b) an
alternatives-considered rejection is currently justified by the
possibly-wrong fact. **Action: one curl with a token against
`:8090/api/0/projects/` settles it; then reconcile the three places.**
Do this before Phase A/B wiring decisions — it changes the trigger AND
the Dismiss write-back design.

## R2-2. The Dismiss-overturn surface does not exist (and it's the trust metric)

§9/§12/RFC say the operator overturns via **GitHub label/comment** — but a
Dismissed signal has **no GitHub object** (pre-File it lives only in the
ledger + closed monitoring state; that was my round-1 item 4, and the docs
adopted it). GH overturn works for File only. For Dismiss — the exact
disposition whose overturn rate gates autonomy (§10) — the surface is
unspecified. In propose-first mode the proposal itself is the surface
(operator declines) — fine. But the moment Dismiss flips autonomous, the
overturn surface vanishes precisely when the metric still needs feeding.
Suggestion worth considering: **signal recurrence + human reopen as the
implicit overturn** — the fleet already fingerprints signals in the
ledger; a human re-opening the GlitchTip issue (or the same fingerprint
re-firing hot after a Dismiss) is machine-detectable and appends an
overturn event with zero new UI. Decide something here; today the trust
metric has no data source in autonomous mode.

## R2-3. Self-evident invariant: it's an acceptance *floor*, not the acceptance

Measured hazard from my eval to guard against: **workers optimize to the
stated acceptance, efficiently** — whatever it is. "No 5xx" as the whole
acceptance invites the symptom-suppression fix (swallow the exception,
return 200/empty — the crash is gone, the defect is not; operator rule 0.7
territory). One sentence fixes it: a self-evident invariant justifies the
**File decision**, but the L1-candidate should mark it as an
**acceptance floor**; Fleet 1's triager still owes the "what should it do
instead?" question, and if that is unanswerable its own needs-info valve
fires. Keeps Fleet 2's gate from laundering symptom-level acceptance
through Fleet 1.

## R2-4. Pin the host, not just the ports

§6/§8 pin `:8428/:9428/:10428` but never name the host — and the
observability stack is mid-migration (VictoriaMetrics/Grafana currently on
the DGX, planned move to the Mac mini; the DGX-side repo has diverged —
operator memory, `project_observability_selfhost`). Phase A wiring should
name the canonical host explicitly and note the migration, or the fleet
binds to a target that is about to move under it.

## R2-5. Phase A will not exercise the `bug` seam — say so

The launch-data-stale alert is a good plumbing proof, but its natural
disposition is data-ops/config (`config-enhancement` or Dismiss), not
`bug`. Phase A success should not be read as validating the File→Fleet-1
seam — that arrives with Phase B errors (or a synthetic error in Phase A
if the seam needs proving earlier). One sentence in §8 prevents the
over-read.

*(Positive, no action: the intent-source registry as an open question is
the right call; the ledger schema is right; the self-improving
config-enhancement loop on missing correlation links is elegant.)*
