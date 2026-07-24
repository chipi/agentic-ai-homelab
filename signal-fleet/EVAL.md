# EVAL.md — evaluating the signal-to-action triager

**Status:** design (pre-build). North-star for how we measure the triager before
trusting it with autonomy. Mirror of `bugfix-fleet/BAKEOFF.md` for Fleet 2.
**Date:** 2026-07-24. **Shaped by:** Fleet-1's round-5 review (in
`REVIEW-2026-07-24-fleet1-architectural.md`).

> The gap this closes (operator, 2026-07-24): we proved the *pipeline* works
> end-to-end but never measured whether the *dispositions are correct*. ~6 live
> runs on noise/test signals is anecdote, not evaluation. This doc is the
> evaluation.

## 1. Go-live is three transitions, not one gate

Each has a different risk shape and a different gate (Fleet-1 review, round 5):

| Transition | What it means | Gate |
|---|---|---|
| **(i) Propose-first live** | daemon polls; dispositions recorded + observable; **Dismiss/File held for operator one-click** | **none** — safe now; it *generates* the labeled set |
| **(ii) Autonomous Dismiss** | fleet closes false alarms without a click | **false-dismiss ≈ 0 AND escalate-rate ≤ tolerance** on the eval |
| **(iii) Unattended File** | fleet opens real issues in a real repo | **executable File L1-quality** (the candidate ships through Fleet 1) |

The eval gates (ii) and (iii). It does **not** gate (i) — and (i) is the best data
collector we have: real traffic + the operator's review clicks = the labeled set,
at no extra cost.

## 2. Why an eval at all (the failure the pipeline hides)

The triager passed every *mechanical* check while being *semantically* wrong (same
lesson Fleet-1 measured: shape-valid ≠ correct). Concretely, in our own runs two
identical `SyntaxError` issues (PLAYER-4/5) drew different dispositions. The
pipeline can't tell us if that's model nondeterminism or evidence drift — only a
controlled eval can.

## 3. Design — five hardenings (from Fleet-1's measured experience)

### 3.1 Freeze the evidence bundles; replay k≥3
Live k-runs confound **model variance** with **evidence variance** — logs roll and
metrics move between runs, so you can't even settle whether PLAYER-4-vs-5 was the
model or the data. **Capture each labeled signal's evidence bundle once, freeze it,
replay the frozen bundle k≥3 times.** This is exactly why the bake-off resets a
worktree per run: pinned problem state is what makes k-runs mean anything. Replay
measures *triage quality*; live runs measure only *pipeline integration*.
(k≥3 stays necessary even at `temperature: 0` — the residual variance is
provider/MoE nondeterminism, measured in Fleet-1 too.)

### 3.2 Fight the base rate — seed real defects from Fleet-1's bugs
Our live stream is **noise-dominated**; a labeled set drawn from history scores an
always-dismiss triager near-perfect. We have a defect generator nobody else does:
**Fleet-1's replayed bug set.** Run orrery at a bug's base commit (`<fix>^`),
trigger the defect so the real error lands in GlitchTip, capture *that* signal +
its evidence bundle → **ground truth = File(bug) with a *known* acceptance** (the
bug's oracle). Cross-fleet reuse that gives the File class real, non-synthetic
members with objective ground truth.

### 3.3 Score the File class *executably*, not by rubric
For seeded-bug signals the quality bar is executable: hand the filed L1-candidate
to the Fleet-1 pipeline and **see if it ships** (that is the *intake score*,
already defined in `BAKEOFF.md` §6.3). Rubric-score only `config-enhancement`,
where no oracle exists.

### 3.4 Report asymmetric metrics, not accuracy
| Metric | Why |
|---|---|
| **false-dismiss rate** ⭐ | a missed real defect is the expensive error — *the* number |
| **escalate-rate** | pair with false-dismiss, or an always-escalate triager games it to zero |
| **File L1-quality** (§3.3) | does the candidate ship / cite intent / route work_type |
| **consistency** (§3.5) | near-duplicates → same disposition |

The **autonomy-Dismiss gate is a pair**: `false-dismiss ≈ 0` **AND**
`escalate-rate ≤ <operator tolerance>`. Accuracy alone is a trap (base rate).

### 3.5 Near-duplicate pairs as a first-class probe
Manufacture near-identical signal pairs (PLAYER-4/5 is the found example); they
must draw the same disposition across the k frozen replays. Consistency is its own
score, not folded into accuracy.

## 4. The reference set (grounded in the real inventory, 2026-07-24)

A **reference case** = a frozen fixture: `{signal, evidence_bundle (frozen),
ground_truth_disposition, [expected work_type + acceptance/oracle]}`. Live at
`signal-fleet/reference/`.

**Coverage — span the space + the adversarial cases.** From the real signals:

| Class | Real examples | Ground truth |
|---|---|---|
| clear dismiss (noise/test) | `PLAYER-3` "ops validation test event", `*validation/smoke/probe*`, `ORRERY-DEV-1` "x" | dismiss |
| real client defect | `ORRERY-5/6` `null` deref (n=3), `ORRERY-8` dynamic-import fail | File(bug) |
| real backend defect | `PODCAST-4` span-export timeout (n=42) | File(bug) |
| miscalibrated alert | Grafana `orrery-stale` while data fresh | dismiss + `config-enhancement` |
| genuine ops | Grafana `disk-critical`, `scrape-down` | File(config) / escalate |
| expected security noise | Grafana `ssh-probes`, `fail2ban` | dismiss |
| **consistency pair** | `PLAYER-4` vs `PLAYER-5` (same `SyntaxError`) | same disposition |
| **false-dismiss trap** | seeded Fleet-1 bug that *looks* like noise | File(bug) — dismiss = FAIL |
| **seeded defect (executable)** | orrery bug at `<fix>^` → real GlitchTip error | File(bug) w/ oracle (§3.2/3.3) |

Grafana rules each contribute ≥2 cases (real vs false-alarm): `5xx elevated`,
`scrape down`, `disk low/critical`, `orrery stale`, `ssh probes`, `fail2ban`.

**Sourcing, in order:** (1) replay real signals (snapshot + freeze the bundle);
(2) **operator labels the ground truth** — the human oracle, ~20–30 cases, the one
input only the operator can give; (3) seed real defects from Fleet-1 bugs (§3.2);
(4) curate the adversarial pairs/traps (§3.5).

## 5. The harness (to build)
- `signal-fleet/reference/*.json` — frozen fixtures + labels.
- a **freezer**: given a live signal, snapshot its evidence bundle to a fixture.
- a **scorer**: replay each fixture's frozen bundle through `triage.triage` k times,
  aggregate the §3.4 metrics + §3.5 consistency; for seeded-bug File cases, invoke
  the Fleet-1 intake check (§3.3).
- append-only `results/eval-runs.tsv` stamped with `prompt_sha` + model (the
  `runs.tsv` pattern), so eval runs are comparable across triager versions.

## 6. What this is NOT
- Not a blocker on propose-first (§1). Ship (i) now.
- Not a single number (§3.4) — false-dismiss and escalate-rate are reported apart.
- Not rubric-only — the File class is scored executably where an oracle exists (§3.3).

## 7. Open (needs operator)
- The **ground-truth labels** on the ~20–30 real cases (§4 sourcing #2).
- The **escalate-rate tolerance** for the autonomy-Dismiss gate (§3.4) — operator's number.
