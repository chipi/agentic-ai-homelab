# Seat auction 2026-07-26 — full research record

One day of measurement that closed the bug-fix fleet's model-selection
chapter: the production loop verified end-to-end, both LLM seats decided
on frozen-replay evidence, and four instrument defects found and fixed by
the failures themselves. This document is the review-grade record; the
raw per-run data lives in
[`bugfix-fleet/bakeoff/results-snapshots/2026-07-26-seat-auction/`](https://github.com/chipi/agentic-ai-homelab/tree/main/bugfix-fleet/bakeoff/results-snapshots/2026-07-26-seat-auction)
(ledgers, per-chain flow logs, per-consultation rationale JSONs).
Narrative session log: BAKEOFF §6.3 sessions 3k–3m.

## 1. Instruments and bars

- **Closed-loop chain** (`orchestrate.sh`, lab twin of `fleetd chain`):
  triage → fix → kick-back(≤3) → advisor → reporter(≤2) on
  fly-physics-L0, the historically never-shipped bug. Bar: ship rate at
  k=3.
- **Gate row** (worker sieve): 5 fix-ready bugs × 1 episode. Bar: 5/5 —
  anything less eliminates (flash set the bar).
- **Decisive row** (worker): 5 discriminating cells × k=3 (only run for
  gate survivors).
- **Advisor eval** (`advisor_eval.sh`): frozen kick-back evidence
  replayed per model, no chains. 3 fixtures = 3 seat skills:
  - *fly-physics* — REDIRECT under a hard name-trap decoy
    (`visViva` in orbital.ts vs true owner
    `heliocentricSpeed` in orbital/fly-physics.ts)
  - *look-angles* — REDIRECT out of a wrong layer
    (patch went to astronomy/horizontal.ts; owner
    satellite/look-angles.ts::observerEci)
  - *mission-arc* — CONFIRM, don't invent (patch was at the true owner
    mission-arc.ts::transferEllipse; hidden acceptance still red)
  - Bar for a seat win: **≥3/3 decoy AND ≥2/3 confirm**, wall <600s
    (ADVISOR_MAX_WALL, added this day — see §5).
- Scoring hygiene: dead-calls (empty pin, wall ≤10s) and overtime cuts
  (empty pin at wall≈600s) are excluded from accuracy and reported
  separately. Cost is measured $/chain, not $/token.

## 2. Closed-loop verification — the acceptance transition

**Retraction first:** the 3j "SHIPPED (n=1)" did NOT replicate.
advfull k=3 (night batch): **0/3, all stuck at kick-back budget**, with
an identical round signature (see `chain-advfull-k*-flow.log`):

| round | all 3 chains identically |
|---|---|
| 0 | fix off-pin, FAIL |
| 1 | advisor pins `heliocentricSpeed` (correct), fix AT pin, FAIL — acceptance gap |
| 2 | advisor RE-consulted → **invents the fly/+page.svelte call-site** (3/3), fix there, FAIL |
| 3 | advisor back to correct pin, fix at pin, FAIL — budget dead |

Root cause (mechanical, not model): the advisor's pin hands the kb
triager a citable repo-data source every round, so the
uncited→needs-info downgrade can never fire; the 2×2 routing
(FAIL+right-place → reporter) existed as analysis, not code. The
reporter was unreachable **by construction**.

**Fix — acceptance transition** (orchestrate.sh + fleetd chain.go):
fixed-at-pin ∧ still-FAIL → skip advisor (its only move is
re-invention), kb triage in ACCEPTANCE_GAP mode, force
actionable→needs-info post-LLM, synthesize the reporter question if the
triager returns none. Pin memory = accumulated per-run set surviving
reporter-QA restarts (accfix-k1 exposed the reset bug — see log).

**Verification ladder (three script vintages, each run hardening the
next):**

| chain | vintage | outcome | what it proved |
|---|---|---|---|
| accfix-k1 | gap rule only | needs-info (park) | rule fires, but pin memory reset across QA restart + question-less downgrade |
| accfix-k2 | + pin fix pending | needs-info (park) | gap fires at the exactly-intended round, no re-invention |
| accfix-k3 | complete | **SHIPPED** r0 96s | full path: fix@owner FAIL → pin → QA → fix@pin FAIL → acceptance-gap → synthesized question → reporter → PASS |
| accfin-k2 | complete | **SHIPPED** | both reporter paths exercised (triager's own needs-info AND downgrade+synthesis); pin memory survives QA restart |
| accfin-k3 | complete | **SHIPPED** | shortest: one reporter round, PASS 75s |

**Final-script rate: 3/3.** Advisor pins: **15/15 on first
consultations** (lifetime, incl. 3 flash-worker chains below); **4/4
WRONG on re-consultations under fail-at-pin evidence** — that mode is
now structurally eliminated, which is the correct fix: the advisor is a
topology instrument and fail-at-pin is not a topology signal.

## 3. Worker seat — flash promoted; the floor is flash

**Promotion evidence (flashchain k=3, PI_MODEL=v4-flash, all SHIPPED):**

| chain | r0 fix | advisor | r1 fix@pin | transition | final |
|---|---|---|---|---|---|
| k1 | FAIL 42t/190s scope=no | pin 50s | FAIL 9t scope=yes | acceptance-gap → reporter | **PASS 10t/85s** |
| k2 | FAIL 24t/145s scope=no | pin 121s | FAIL 10t scope=yes | acceptance-gap → reporter | **PASS 12t/65s** |
| k3 | FAIL 22t/150s scope=no | pin 115s | FAIL 29t/270s scope=yes | acceptance-gap → reporter | **PASS 20t/106s** |

flash follows advisor pins and integrates reporter answers identically
to v4-pro (which also shipped 3/3 on the same loop), at ~¼ price, faster
walls, and cheaper failures (night decisive row: identical k=3 rates on
all 5 cells, 8-turn bails where v4-pro grinds 2–4.5×). **Wired into
fleetd as `worker_model` (default v4-flash); the lab pi.sh base stays
v4-pro as the frozen reference instrument.**

**Floor hunt (gate rows below flash's $0.14):**

| candidate | $/M in/out | gate | failed cells | note |
|---|---|---|---|---|
| deepseek-v4-flash (bar) | 0.14/0.28 | **5/5** | — | the floor |
| qwen3.5-flash-02-23 | 0.07/0.26 | 4/5 | mission-arc | 335 "fail" was a flake — retry PASSed 90s |
| glm-4.7-flash | 0.06/0.40 | 4/5 | mission-arc | best cheap score; 50-turn grinds |
| qwen3-coder-30b-a3b | 0.07/0.27 | 4/5 | mission-arc | first row burned by provider mis-route (§5), clean re-run |
| seed-2.0-mini | 0.10/0.40 | 3/5 | credits, mission-arc | **only REGRESSION of the hunt** (broke an existing test) |

**Every sub-flash model died on the same cell (mission-arc) with the
same signature: scope=yes, 28–50 turn grind, one acceptance test still
red.** The cheap tier reaches the right code and cannot close
precision. Per-model prompt tuning was considered and rejected: the
same prompt is verdict-invariant across flash/v4-pro/sonnet/opencode
(the capable tier), failures are in the precision step not
comprehension, and a bespoke-prompt worker is no longer a commodity
seat (tuning cost eats the ≤25%-of-chain saving).

## 4. Advisor seat — glm retained; the seat is two anti-correlated skills

**Round 1 (incumbent + stack models), valid runs, avg wall:**

| fixture (skill) | flash | v4-pro | glm-5.2 | kimi-k2.6 |
|---|---|---|---|---|
| fly-physics (redirect/decoy) | 2/3 · 70s | 1/3 · 228s | **3/3 · 108s** | 1/3 · 628s |
| look-angles (redirect/layer) | 2/3 · 146s | **3/3** · 617s | 3/4 · 253s | 0 valid (cuts) |
| mission-arc (confirm) | **3/3 · 170s** | 3/3 · 513s | 1/3 · 115s | 3/3 · ~32 min |

kimi: capable (3/3 confirm unbounded) but 27–38 min/consultation — 66–72k
output tokens per read-only pin at ~45 tok/s. **Formally disqualified by
the latency contract** (0 usable under the 600s cap it caused to exist).

**Round 2 (challengers, all ZDR/provider-enabled by operator same day):**

| challenger | $/M in | decoy | layer | confirm |
|---|---|---|---|---|
| qwen3.7-plus | 0.32 | 2/3 | 2/2 +cut | 0/3 (2 cuts + `explore/+page.svelte` invention) |
| minimax-m3 | 0.30 | 0/3 | **3/3** | 0/3 (fly call-site ×3) |
| stepfun-3.7-flash | 0.20 | 2/2 +cut | **3/3** | 0/3 (2 cuts + invention) |
| qwen3-max-thinking | 0.78 | 0/3 | 0/3 | **3/3 · 55–101s** |

**No model in either round clears both skills.** Across 8 models the
pattern is near-perfectly anti-correlated:

- *Redirect specialists* (glm, stepfun, minimax-on-layer): overrule the
  failed patch well; under confirm evidence they cannot accept "the
  location is right" and invent alternates.
- *Confirm specialists* (flash, v4-pro, kimi, max-thinking): accept the
  true owner cleanly; under decoy evidence they follow the name-trap.
- **Price is uncorrelated with either skill** ($0.78 max-thinking went
  0/6 on redirects; $0.20 stepfun was never wrong on a finished
  redirect).

**Rationale archaeology** (`advisor-rationales/`): the confirm-fixture
"inventions" are not hallucinations — the models found a REAL structural
feature (Moon missions bypass `buildArcs`/`transferEllipse` via a
route-local `moonHelioArc` in the fly route) and over-weighted it.
Suspicion-tuned models find genuine alternate paths and can't resist
them; the oracle (and the actual failing test) is at `transferEllipse`.

**Decision: glm-5.2 retains the seat.** Its known weakness
(confirm-invention, 1/3) is already mechanically guarded in the loop:
the acceptance transition removes the advisor from pinned confirm
situations entirely, and glm handled the production confirm shape
(round-0 right-file fail on fly-physics) correctly in all 8 shipped
chains. **Deferred design, ready if real bugs demand it: split the
consultation by evidence shape** — redirect-mode (patch touched
off-target) → glm; confirm-mode (patch touched where ticket/pin points)
→ flash. Both models already in the stack; the mode signal is
mechanical; no new vendors, no new prompt axis.

## 5. Instrument defects found by failures (all fixed same day)

1. **No advisor wall cap** — kimi ran 27–38 min consultations before
   anyone noticed the leaf had no bound (triage leaf had 900s). Fix:
   `ADVISOR_MAX_WALL=600`, same cut pattern. The seat's contract IS
   bounded latency; under it, kimi scores zero usable consultations.
2. **pi resolves bare model ids against its BUILTIN catalog first** —
   `qwen3-coder-30b` mapped to huggingface (no key) → 0-turn deaths that
   burned a full gate row while looking like model failures. Fix: every
   leaf pins `--provider openrouter`; all candidates registered in
   `~/.pi/agent/models.json`. Corollary: provider allowlist changes
   reroute serving (post-change the whole roster served via Baidu;
   glm-4.7-flash unreachable until Novita was allowed) — wall times are
   not comparable across serving stacks; provider is now noted alongside
   numbers.
3. **Dead-call guard threshold too tight** — real dead-calls take 5–6s
   through pi startup; the guard said ≤2s, so 16 garbage rows got
   written during the second budget wall before a manual stop. Fix:
   threshold ≤10s; eval aborts after 3 consecutive; raw episodes
   archived per run.
4. **Two distinct budget walls in one day, same face** — (a) OpenRouter
   ORG monthly cap ($50): 403 "Budget limit exceeded (monthly)";
   (b) prepaid credits exhausted (75.26/75): "Insufficient credits."
   Both present as instant empty completions across ALL models,
   indistinguishable from model failure without the guards.
   Recommendation on file: auto top-up / larger buffer — prepaid walls
   are the one failure mode unattended fleets cannot route around.
   Related decision: per-vertical OpenRouter keys (pi / opencode /
   mini-fleet) — rewire deferred until no measurements in flight.

## 6. Decisions taken / deferred

| decision | status |
|---|---|
| Worker seat = flash (fleetd `worker_model`) | **TAKEN** — measured promotion, 3/3 closed-loop |
| Lab base config stays pi+v4-pro | **TAKEN** — frozen reference |
| Advisor seat = glm-5.2 | **TAKEN** — no challenger cleared the bar |
| Acceptance transition (mechanical reporter routing) | **TAKEN** — verified 3/3 |
| Split consultation (redirect→glm, confirm→flash) | **DEFERRED** — until real-bug confirm consultations show up in volume |
| Sub-flash worker tier | **REJECTED** — all die on mission-arc precision |
| Per-model prompt tuning | **REJECTED** — breaks commodity-seat premise; capable tier is prompt-invariant |
| Per-vertical OpenRouter keys | **DEFERRED** — operator-gated rewire, no measurements in flight |

## 7. Data map (snapshot inventory)

`bugfix-fleet/bakeoff/results-snapshots/2026-07-26-seat-auction/`:

- `advisor_eval.tsv` — all 100 advisor consultations (ts, fixture,
  model, run, pin, file_ok, fn_ok, wall). Dead-calls: wall≤10 + empty
  pin. Overtime cuts: wall≈600 + empty pin.
- `floor-and-flash-runs.tsv` — worker cells: flash gate+decisive rows,
  all floor-hunt gate rows (verdict, wall, cost-est, turns, out-tokens,
  scope, regressions). Cost columns use v4 pricing constants — treat as
  relative, not absolute, for non-DeepSeek models.
- `chain-*-flow.log` — round-by-round flow for all 11 verification
  chains (advfull retraction ×3, accfix ladder ×3, accfin ×2,
  flashchain ×3).
- `advisor-rationales/<fixture>-<model>-<run>/advisor.json` — pin +
  decoy + rationale per consultation (raw streams deleted: 13 GB → 184
  KB; reproducible from fixtures).
- Fixtures (frozen, reusable): `bugfix-fleet/bakeoff/advisor-eval/fixtures/`.
- Master ledgers (cumulative, outside git): `~/.bugfix-fleet/bakeoff/results/{runs,flow,k3-sweep}.tsv`.
