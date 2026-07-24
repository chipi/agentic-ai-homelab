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
