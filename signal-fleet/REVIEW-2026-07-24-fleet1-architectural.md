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

---

# Round 3 — README, Phase-0 proof, and the MVP first slice (2026-07-24, operator-requested)

Scope: `README.md`, `SIGNALS.md` (post-R2 state, §13–14), `RFC-0003`,
`PHASE-0-infra.md`, `mvp/` (all files read), `test-receiver/`. I verified
the §13.4 reuse-table claims against the live `bugfix-fleet/src/` — they
are accurate (the TS pi/opencode adapters do throw not-implemented;
directAdapter does carry the 3-retry). Phase-0's empirical bar is the
best thing in this round: the GlitchTip API was verified live (8 projects,
real issues listed), the Grafana webhook push was proven end-to-end, and
the recipes are concrete. The MVP spine is faithful to the design: the
intent gate is deterministic post-LLM code, parse failure degrades to
escalate (never a silent bad disposition), the ledger stamps model +
prompt_ver, and the live Dismiss-from-real-evidence run is a genuine
end-to-end proof.

Findings, ordered by weight. R3-1 and R3-2 are the two I'd fix before the
next milestone; the rest are doc-vs-code drift and debt to name.

## R3-1. The idempotency key permanently silences recurring alerts

`actions.already_done()` keys on the signal fingerprint;
`sources._fingerprint()` is Grafana's label-hash (or a labels digest) —
**stable across occurrences by construction**. Sequence: alert fires →
fleet Dismisses (correctly — data was fresh) → alert resolves → *next
week the same alert fires for a real outage* → same fingerprint → `already
-> dismiss; skipping`. One correct Dismiss buys every future occurrence of
that alertname a silent skip. Harmless in the single-shot MVP; a real bug
the day the poll becomes a daemon — and it inverts §9's intent (don't
re-litigate the *same occurrence* ≠ never revisit the *same alertname*).
Fix: make the ledger key an **occurrence id** — fingerprint + `startsAt`
(Grafana gives it; you already normalize it into the signal) — and note
that the R2-2 implicit-overturn design *depends* on recurrence being
visible, which this bug would also break.

## R3-2. Dismiss is the autonomy-bound disposition — and it is the only ungated one, fed by silently truncated evidence

Two halves that compound:
- **No dismiss-gate exists.** The intent gate protects File; escalate is
  safe by definition; Dismiss — the disposition §10 wants to make
  autonomous — passes on the model's say-so. Fleet-1's measured lesson
  (shape-valid ≠ correct, confident invention) applies with the sign
  flipped: a hallucinated "already recovered" is exactly the miss the
  overturn metric is supposed to catch, so until the implicit-overturn
  loop exists, propose-first is the *only* thing standing between a
  confident wrong Dismiss and a swallowed real incident. Worth one
  mechanical check now: require the dismiss `reason` to reference at
  least one evidence key that is non-empty and non-error (cheap, no LLM).
- **`build_user()._trim()` cuts each evidence block at 1800 chars with no
  truncation marker.** The triager cannot distinguish "no error lines
  in the logs" from "the error lines were cut at char 1801." That bias
  points *toward* Dismiss — absence of visible evidence reads as absence
  of a problem. Append an explicit `…[truncated N of M chars]` marker.

## R3-3. Dispositions-compose (§7.1) is designed but not implemented — the Tune case loses its File half

The doc's resolved Tune boundary is a **dual output**: Dismiss now AND
File a `config-enhancement`. In `mvp/`, `immediate_recommendation` is
printed and folded into the ledger's reason column — no
`config-enhancement` issue payload is built, so the follow-up half of the
dual output evaporates (exactly what §7.1 says must not be lost). The
live slice's own verified run ("dismissed + recommended the alert fix")
produced a recommendation that now lives only in a print statement and a
truncated TSV cell. MVP-acceptable, but it is doc-vs-code divergence on a
*resolved* decision — either implement the second output (a dry-run File
alongside the Dismiss) or mark §7.1 as not-yet-implemented in the MVP
boundaries list.

## R3-4. Intent-source vocabulary drift: `operator rule` is in the docs but not in the code

SIGNALS §4.1's table lists five sources including **operator rule**;
`triage.py ALLOWED_INTENT = {reporter, spec, repo-data, code-invariant,
baseline, slo}` — no `operator-rule`. A triager legitimately citing a
standing operator preference gets mechanically downgraded to escalate.
Pick one list, write it in both places (and Fleet-1's `agents/triage.md`
should stay the shared base vocabulary + your `slo` extension, as §13.4
already says).

## R3-5. The validate-retry loop is decorative for shape failures at temperature 0

`triage.triage()` retries up to 3× with the **same messages** and
`temperature: 0` — a deterministic request retried unchanged returns the
same malformed shape; the loop only helps transport flakes. Feed the
validation error back as an extra message on retry (that is what makes
validate-*retry* work), or drop the pretense and treat parse failure as
the escalate-degrade it already is.

## R3-6. Least-privilege debt across every credential — and the "prescribed integration" claim is soft for Grafana

- GlitchTip token minted with **full scopes** for a fleet that needs
  issue-read now (and later issue-resolve for Dismiss write-back).
- Grafana consumed with the **admin password** via basic auth — Grafana's
  actually-prescribed programmatic path is a **service-account token**;
  Phase-0's "consumed the way its platform prescribes" is not quite true
  for this row.
- Umami consumed as the **admin login**.
- `run.sh` sources whole stack `.env`s (admin creds) into the fleet's
  process environment.

None of this blocks the MVP; all of it is the kind of debt that becomes
invisible after productionization. One pass — scoped GlitchTip token,
Grafana service account, Umami view-only user, a fleet-owned sops file —
before the daemon/ingress phase.

## R3-7. Close R2-1 fully: stale "unverified" lines contradict Phase-0

PHASE-0 verified the GlitchTip Sentry-compat API **live** (token, 8
projects, real issue ids). SIGNALS still carries "unverified on-prem"
(§6 pivot chain, §8 verdict column) and §12.2 still opens with "first,
verify the GlitchTip API (R2-1): one curl…" — that curl has happened.
Reconcile the three spots and mark R2-1 closed; also fold the Phase-0
consumption *decision* (poll-over-webhook because the webhook payload is
Slack-shaped) back into §8, which still presents webhook-vs-poll as open.

## R3-8. Smaller

- **`prompt_ver` is a hand-bumped constant** (`"mvp-1"`); edit `SYSTEM`
  without bumping and the ledger lies. Stamp `sha1(SYSTEM)[:8]`
  alongside the human-readable version — free attribution.
- **`OPENROUTER_KEY` is not `required=True`** — a missing key today
  surfaces as a confusing HTTP failure inside the first triage call
  instead of a clean startup error.
- **Escalate is a print statement** — no operator notification path
  beyond the ledger row. Fine for MVP; list it in the boundaries.
- **`GLITCHTIP_TOKEN` is loaded but unused** in the MVP — either wire the
  Phase-B stub or drop it until then.
- **§13.4's "directAdapter is the only working path" is half-right**: the
  bake-off's *bash* pi path did structured output all day (11/12 calls,
  extract+retry) — the TS adapters are what's unimplemented. Your choice
  (raw OpenRouter) is still the right one for the MVP — simpler and
  observable — but the stated reason overclaims.

*(Verified in this round: §13.4 reuse-table claims against
`bugfix-fleet/src/` — accurate; PHASE-0's live-evidence table —
internally consistent; mvp/ code read in full: config, http_util,
sources, correlate, triage, actions, orchestrator, probes.)*

---

# Round 4 — verification of the R3 fold (commit `57807f7`) (2026-07-24, operator-requested)

I read the full diff, not the commit message. **Verdict: all R3 items are
genuinely implemented, and mostly better than asked.** Highlights: the
R3-1 fix keeps the stable `fingerprint` *alongside* the new
`occurrence_id` precisely so the R2-2 recurrence/implicit-overturn signal
survives — that interplay was easy to miss and wasn't; R3-5 is a real
feedback retry (parse error + prior raw appended to the messages) with
transport and shape failures correctly separated and `SystemExit` not
swallowed; the truncation markers, enum alignment, `prompt_sha`
auto-stamp, and the two-gate `_meta`/ledger split are all exactly right.
The stale-"unverified" line I hunted for lives only in the discussion log
(historical record — correct to keep).

Four residuals, none blocking; R4-1 and R4-2 are the two I'd fold:

## R4-1. Ledger schema migration is unhandled (mixed-schema TSV)

The ledger gained columns (`occurrence_id`, `prompt_sha`, `gates`) but
rows append to whatever file exists: a ledger that already has v1 rows
keeps its v1 header, new v2 rows land under it misaligned. It's
harmless-by-luck today (`already_done` matches `fp@startsAt` format,
which old index-1 values can't collide with) — but the ledger is the
**overturn dataset**, and mixed-schema TSVs rot analyses silently. Fix
is one line of policy: version the filename (`dispositions-v2.tsv`) or
migrate-once on header mismatch.

## R4-2. The Tune follow-up launders the triager's own idea as `operator-rule`

`_tune_followup()` stamps the recommendation's acceptance criterion with
`intent_source: "operator-rule"` — but no operator stated it; the
triager invented it. That is precisely the invention-laundered-as-citation
pattern the intent gate exists to stop, reappearing on the config side.
Since `config-enhancement` items route to the operator anyway, honesty is
free: add `triager-recommendation` to the vocabulary (clearly marked as
below the intent-source bar, acceptable *only* for operator-gated
work_types), or leave the criterion uncited on this path. Do not let
`operator-rule` mean "nobody said this."

## R4-3. The Tune follow-up still leaves no ledger trace

The dual output's File half exists as a printed dry-run payload; the
ledger row records only `disposition=dismiss` with empty `work_type`.
Until File goes live, the ledger undercounts pending config work — §7.1's
"not lost" is currently stdout-deep. One extra row (or a `followup`
column on the dismiss row) closes it.

## R4-4. Residual, acknowledged: the dismiss gate is a floor, not a link

`_dismiss_gate` requires ≥1 usable evidence query globally; it does not
check that the dismissal's *reason* engages with that evidence (a dismiss
justified by nothing can pass because an unrelated query returned rows).
Right-sized for the MVP — recorded here so the autonomy-flip review
(§10, overturn≈0) remembers the gate's actual strength when it decides.

*(No new review rounds needed for this fold — fold R4-1/R4-2 whenever
convenient; R4-3/R4-4 can ride along with the next milestone.)*

---

# Round 5 — go-live readiness challenge: Phase B + observability + the eval-gate proposal (2026-07-24, operator-requested)

Scope: commits `18721c1→d3f54d5` (Phase-B GlitchTip trigger +
error→trace→metric→logs correlation, `observ.py` producer-separated
observability, least-privilege pass), full diff read. The direct
questions answered first, then the findings that inform them.

## Answers

**Is a bake-off-style eval the right gate? Yes — for the *autonomy*
transitions, and only those.** Split "go live" into three transitions
with different risk shapes: (i) **propose-first live operation** (daemon
polls, dispositions recorded + observable, Dismiss/File held for operator
one-click) — safe *now*, needs no eval, and is itself the best data
collector you have; (ii) **autonomous Dismiss** — gate on the eval,
specifically false-dismiss; (iii) **unattended File to a real repo** —
gate on File L1-quality, cheaply measurable the executable way (below).
Don't let the eval block (i): shadow/propose-first operation *generates*
the labeled set the eval needs, from real traffic, while costing the
operator only the review clicks they already make.

**Is the eval design sound? The skeleton yes; five hardenings from
Fleet-1's measured experience:**

1. **Freeze the evidence bundles.** k-runs against *live* sources are
   unmeasurable: logs roll and metrics move between runs, so model
   variance and evidence variance are confounded (you cannot even settle
   whether PLAYER-4-vs-5 was model inconsistency or evidence drift).
   Capture each labeled signal's evidence bundle once; replay the frozen
   bundle k times. This is the exact reason the bake-off resets a
   worktree per run — pinned problem state is what makes k-runs mean
   something. Replay measures triage quality; live runs measure only
   pipeline integration.
2. **Fight the base rate or the eval teaches "dismiss everything."**
   Your live stream is noise-dominated (all ~6 runs to date). A labeled
   set drawn from history will score an always-dismiss triager near-
   perfect. Seed real-defect signals deliberately — and you have a
   generator nobody else has: **Fleet-1's replayed bugs.** Run orrery at
   a bug's base commit, trigger the defect, let the real error land in
   GlitchTip, capture that signal + evidence → ground truth = File(bug)
   with *known* acceptance. Cross-fleet reuse that gives the File class
   real, non-synthetic members.
3. **Score the File class executably, not by rubric.** Fleet-1's core
   lesson: shape-valid ≠ good — my triager passed every mechanical check
   while writing poison. For seeded-bug signals the quality bar is
   executable: hand the filed L1-candidate to the Fleet-1 pipeline and
   see if it ships (that is the intake score, already defined in BAKEOFF
   §6.3). Rubric-score only `config-enhancement`, where no oracle exists.
4. **Report asymmetric metrics, not accuracy.** False-dismiss is *the*
   number (a missed real defect is the expensive error; a spurious
   File/Escalate is operator annoyance). But pair it with
   **escalate-rate** — an always-escalate triager scores zero
   false-dismiss trivially. The autonomy gate is a pair: false-dismiss ≈
   0 **and** escalate-rate under a stated operator tolerance.
5. **Keep near-duplicate pairs as a first-class probe.** PLAYER-4 vs
   PLAYER-5 is a *consistency* test case of a kind worth manufacturing:
   near-identical signals must draw the same disposition. At
   temperature 0 the remaining variance is provider/MoE nondeterminism —
   measured in Fleet-1 too (same config, same ticket, different
   verdicts) — so k≥3 per frozen bundle stays necessary even at temp 0.

**Do Phase-B failure modes make an unevaluated go-live unsafe? Yes —
three concrete ones found in this diff, the first two on the Dismiss
path:**

## R5-1. The dismiss gate is structurally vacuous on the error path

`_dismiss_gate` requires ≥1 usable evidence query. For GlitchTip signals,
`evidence_for_glitchtip_error()` always yields `event_summary` — the
error's own details — unless the API call itself fails. The error being
triaged **is** the evidence that satisfies the gate that approves
dismissing it. On Phase-B signals the R4-4 "floor" is not weak, it is a
no-op: every hallucinated "transient, already recovered" passes. Fix
before any autonomous Dismiss: the gate must require usable evidence
*beyond the triggering event itself* (trace, logs, or metrics), or a
dismiss-reason that engages with named evidence.

## R5-2. Absence-of-trace reads as absence-of-problem

A client-side error legitimately has no server trace — and a failed
trace lookup *also* produces nothing. The bundle doesn't distinguish
"trace not expected (browser error)" from "trace lookup failed" from
"trace expected but missing." Fleet-1 measured exactly this bias shape
(silent truncation → dismiss-leaning); label the absence explicitly in
the bundle (e.g. `trace: <not expected: client-side platform>` vs
`<error: …>`), or the model will keep reading blanks as recovery.

## R5-3. `http_5xx_rate` is mislabeled evidence — it's total traffic

`sum(rate(http_requests_total{job=~".*proj.*"}[5m]))` has **no status
filter**: the query returns the *total* request rate, presented to the
model under the name `http_5xx_rate`. Wrong data under an authoritative
label is worse than no data — a healthy traffic number read as "5xx rate
is nonzero and steady" can swing a disposition either way. Add the
status-label filter (whatever the exporter's convention is), or rename
the evidence key to what it actually measures.

## R5-4. Occurrence-id churn on hot errors (R3-1's mirror image)

`occurrence_id = shortId@lastSeen` — but `lastSeen` advances on **every
new event** of an unresolved issue. A hot recurring error gets a fresh
occurrence id each poll → re-triaged every cycle: the opposite failure
from R3-1 (cost/churn instead of permanent silence), same root cause
(occurrence boundary not tied to a state transition). Key it on a real
transition instead: `firstSeen` + resolved→unresolved regression count
(the Sentry-compat API exposes status changes), so one occurrence =
one unresolved episode.

## R5-5. Smaller

- **Langfuse model pricing is project-scoped** — the new `triage-fleet`
  project won't show $ until the model definitions/prices are registered
  there too (Fleet-1 hit the same: pricing registered in its own project
  only). One-time setup, do it before quoting cost dashboards.
- **`sort=-last_seen&limit=5` starves old-but-real defects** behind hot
  noise once volume grows; fine for MVP, note it for the daemon.
- The least-privilege pass and producer separation
  (`environment=operations`, separate Langfuse project, Viewer SA,
  scoped token) address R3-6 properly — good close.

## Recommended gate, concretely

1. **Now:** fix R5-1/R5-3 (small), label trace absence (R5-2), then go
   live **propose-first** — daemon on, everything recorded and
   observable, File as draft/queued issues, Dismiss as one-click
   proposals. The shadow ledger + operator clicks become labeled data.
2. **Autonomous Dismiss:** the eval as amended — frozen bundles,
   seeded-defect class from Fleet-1 bugs, k≥3, false-dismiss ≈ 0 AND
   escalate-rate within tolerance, near-duplicate consistency clean.
3. **Unattended File:** executable L1-quality on the seeded class
   (filed candidate ships through Fleet 1), plus R4-2/R4-3 folded so
   the ledger tells the truth about follow-ups.

The eval is the right gate; the unsafe part today isn't the missing
eval, it's that two of the three Dismiss safeguards (gate, evidence
neutrality) have Phase-B-specific holes that no amount of k-runs would
catch from noise-only traffic.
