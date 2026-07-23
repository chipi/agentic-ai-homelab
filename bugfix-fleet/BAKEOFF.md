# Bake-off — north star & evaluation methodology

**Status:** planning (the fleet pipeline is proven on the `direct` baseline;
this doc governs how we evaluate the real harnesses).
**Relates to:** RFC-0002 (the fleet). This is the detailed plan for its Phase 0.

**The question:** given the *same* agents and the *same* real bugs, how do three
fix-engines — **Claude Code**, **opencode**, **pi** — compare, and *at what*?
Concretely: **how close do the cheap harnesses (Chinese-model roster) get to
Claude-quality, and at what cost?**

---

## 1. Mental model — what "running an agent" means

Behind the same `Worker` interface (`triage`/`fix`), three real harnesses + a
baseline:

- **`direct` (baseline / floor)** — NOT a harness. One chat call; *our* glue
  reads/writes files. Works only when the whole repo fits in one prompt. Kept in
  to show what a naive single-shot gets.
- **A harness (`claude` / `opencode` / `pi`)** — an **agentic loop**: the model
  gets tools (`read`/`edit`/`bash`/`grep`) and drives itself — greps, reads,
  runs tests, edits, iterates. This is what scales to real repos.

Each is a `Worker` **adapter**; the orchestrator/flows are identical across them.

### The reuse win: one agent definition, three harnesses
The agent `.md` format (frontmatter + prompt) is **Claude Code's native subagent
format**, **opencode's native agent format**, and pi parses it. So the *same 5
specialist definitions run unchanged in all three.* True apples-to-apples.

## 2. Tool calls — how to think about them

A harness fix is a **loop of turns**; each turn may make a **tool call** (the
agent's *moves*). They matter three ways:

- **Cost (the big one):** every turn re-sends the **accumulating transcript**, so
  an 8-step fix costs *more* than 8 single calls. Inefficient agents (redundant
  greps/re-reads) are expensive.
- **Capability:** tool calls are how an agent investigates a repo it's never seen.
- **Efficiency:** fewer, well-chosen moves = better. Tool-call count + trajectory
  is itself a quality signal.

Langfuse captures the whole trajectory: one trace per fix, a span per turn/tool
call → "opencode fixed #7 in 5 turns / 3 tool calls / $0.004."

## 3. The benchmark — REAL repos, not an artificial sandbox

A toy sandbox (single-file bugs that fit in one prompt) **can't differentiate
harnesses** — `direct` wins trivially and opencode/pi look identical. So we use
**two real, actively-worked projects** ("verticals") that force agentic behavior
(big, multi-file, investigation-required, test-covered):

- **`chipi/orrery`** — TypeScript (SvelteKit + Three.js); styling → AR/3D;
  frontend-heavy; exercises the `ui` specialist + large-context 3D bugs.
- **`chipi/podcast_scraper`** — Python back-end + FastAPI + TS viewer + infra;
  exercises `backend`/`db`/`ui`/`infra`/`docs`.

Both have test suites (the objective floor) and are big enough that `direct`
visibly struggles (informative). **5–8 designated bugs per repo**, chosen
together, spanning easy → investigation-heavy, each with a clear "done."

### 3.1 Sourcing the bugs — replay of real closed bugs

The designated bugs are **real bugs that were already fixed**, replayed by going
back to the bug's **own era** — not by reverting the fix onto today's HEAD. Why
replay beats inventing bugs: each is **genuinely real**, the original fix **diff is
the golden reference** (§7), and the difficulty is authentic.

**One base commit `C` per repo — where a cluster of bugs coexists.** The naive
"revert every fix onto HEAD" model breaks on a fast repo: bugs scattered across
history don't share a baseline (a later bug's buggy code is often introduced
*after* an earlier bug is already fixed — they never coexisted; on `orrery` the
`/fly` file alone churned ~195 commits between one fix and HEAD). So instead we
pick **one base commit `C`** at which a *contiguous cluster* of bugs is all
simultaneously present — buggy code exists at `C`, and every fix lands *after*
`C`. **At `C` the bugs are already there — no reverting; prep just `checkout C`.**
The bug set = that cluster (found by mining a dense window of fix-commits). Two
repos → **two bases `C` → two clusters → two suites**. This single base `C` serves
**both** run scenarios (§6): A resets to it per bug, B works forward from it.

**Anchor on fix commits, not issue numbers.** Fast repos mislabel `closes #N`
(on `orrery`, `6048fb11` claims "closes #225" but is a different bug). The fix
*commit* is the reliable unit; the problem statement is a hand-verified bug
description, and the commit diff is the golden reference. Bundled fixes → pin the
**surgical code slice** (the exact files, in the Appendix).

**No failing test is handed to the harness.** A real bug never arrives with a test
proving it — if it had one, the software wouldn't have shipped. Problem = the repo
at `C` (bug present) + the **bug description**, nothing else. The test lives only
in the **grader**, hidden — SWE-bench's `base_commit + test_patch` model: for bugs
whose fix shipped a test we cherry-pick that test as the hidden oracle; for the
rest we author a hold-out acceptance test purely as the answer key (§6).

## 4. The two factors + the fixed reference (experimental design)

**Change one variable at a time.**

- **Factor A — harness** (`opencode` vs `pi`): the comparison. Isolate it by
  holding the model **constant within a run** — opencode and pi use the **same**
  Chinese model + the **identical** per-role mapping. Any difference is then the
  *harness*.
- **Factor B — model** (DeepSeek / Kimi / GLM …): vary **across runs**, holding
  the harness-pair fixed. Tells you whether the harness winner *holds across
  models*, and which cheap model is best.
- **Fixed reference — Claude Code** on Claude models: the **premium yardstick**,
  constant in every run. Not a variable; the bar the cheap bundles are measured
  against.

### The grid
```
                 opencode     pi          Claude (fixed reference)
 DeepSeek-V4-Pro   cell         cell        Claude
 Kimi-K2.7-Code    cell         cell        Claude
 GLM-5.2           cell         cell        Claude
```
- **Across a row** → harness comparison (model fixed).
- **Down a column** → model comparison (harness fixed).
- **Claude column** → the constant quality/cost bar.

**Note the confound, on purpose:** Claude runs Claude-models, the others run cheap
models — so a row compares *bundles* (harness+model), which is exactly the real
question ("cheap-on-cheap vs Claude-on-Claude"). To isolate the *pure* harness,
a row already does that (same model in both cheap cells). Start with **one row**
(one model), prove the machinery, then add rows.

### 4.1 Role → model mapping (the two rosters, same ladder)

The Claude tiering (ADR-0003) and the Chinese roster share a **symmetric 4-rung
ladder**, role-for-role. Holding this ladder **identical across opencode and pi
within a run** is what isolates the harness; a "row" in the grid = swapping the
whole ladder for the next model family (still identical in both cheap cells).

Both ladders are genuinely four rungs deep — Claude's top rung is **`fable`, which
sits *above* `opus`** (capacity + price), so it pairs with the Chinese top rung
`kimi-k2.6`; `opus` then pairs with `glm-5.2` as the high-reasoner rung. No rung is
left without a twin.

| Rung | Fleet role(s) | Claude harness | Chinese roster (opencode/pi) |
|---|---|---|---|
| **0 · classify** | triage, dispatch | `haiku` | `deepseek-v4-flash` |
| **1 · fix (worker)** | backend, db, ui, docs | `sonnet` | `deepseek-v4-pro` |
| **2 · reasoner** | infra *(or a mid escalation step)* | `opus` | `glm-5.2` |
| **3 · architect (top escalation, on-demand)** | any worker, when stuck | `fable` | `kimi-k2.6` |

**The one open call — where `infra` sits.** Rung 2 (`opus`/`glm-5.2`) is symmetric
and gives infra more reasoning, but it spends a *high* rung on **every** infra fix
— against the "volume on cheap rungs, expensive only on escalation" philosophy.
Recommendation: **keep `infra` on rung 1** (`sonnet`/`pro`) for cost, and use rung
2 as an **escalation step** (worker stuck → rung 2 → still stuck → rung 3
architect), so the two top rungs are only ever hit on demand. Operator's call.

> **Divergence to reconcile:** `agents/infra.md` frontmatter currently pins
> `model: z-ai/glm-5.2` (rung 2). If infra drops to rung 1 it becomes
> `deepseek/deepseek-v4-pro`; if it stays on rung 2 the frontmatter is already
> correct. Not changed yet — operator call.

**Constant gate (not a variable):** the **reviewer is always Claude**, identical
in every cell — it's the yardstick (§7), never part of the varying worker config.

### 4.2 The architect / escalation tier

Ported from the operator's current Claude strip (ADR-0003 `advisor→opus`): a cheap
fix specialist that hits something above its weight **escalates to an architect** —
the roster's top rung (`fable` / `kimi-k2.6`) — for **read-only guidance**, then
implements the answer itself. Only the architect's *summary* returns to the
worker; its long reasoning stays out of the worker transcript → a bounded,
occasional premium call, not a volume tier.

Two consequences for the bake-off:

1. **It's itself a harness-capability test.** Subagent-calls-subagent isn't free
   everywhere: Claude Code — native nested `Agent()` (depth ≤5) ✓; opencode —
   native subagents ✓; **pi — composed in TS** (that build effort is a data
   point); **`direct` — impossible** (no loop, no subagents), which cleanly
   documents `direct`'s ceiling.
2. **The architect model is held constant across opencode/pi too**, per run — same
   rule as every other rung. And **escalation frequency** ("how often did the
   worker need the architect") is a capability/efficiency signal in §7 — a model
   that phones the architect on every bug is weaker than one that rarely does.

## 5. The artifact — a PR per (bug × harness), never merged

Each harness runs **headless** on its **own git worktree/branch** and ends at a
**PR you never merge**. The PR *is* the deliverable. Three PRs per bug (+ the
`direct` baseline), compared. Isolation per worktree; the App only ever opens PRs
on branches (never merges, never pushes main — the operator rule holds by
construction).

## 6. Evaluation setup — the problem, two run scenarios, and grading

**The problem handed to a harness** = the repo **at base `C`** (bug present, plus
the other cluster bugs as realistic latent mess) + the **bug description**. No test
(§3.1). It's expected to produce a **complete fix**, not a minimal diff — cause fix
+ regression test + any affected-test updates + doc updates on divergence (§7;
encoded in the agent `.md` prompts so all harnesses get the identical definition of
done).

**Two run scenarios** (same base `C`, same hidden oracles — only the protocol
differs). Run **A first** (the control), then **B**:

- **A · Isolated (reset-between)** — before each bug, **reset to `C`**; the harness
  targets that one bug; delta-score; reset; next. The other cluster bugs are
  present but ignored for this round (that's the realistic mess, for free). Every
  harness faces each bug from the identical state → clean head-to-head → **this
  fills the grid** (§4). Answers *"which harness/model fixes a given bug best?"*
- **B · Backlog (cumulative)** — start the harness at `C` **once**; it grinds the
  whole cluster fix-by-fix on **one evolving branch**; score each round as it
  lands; collate. Path-dependent (fix #4 may break fix #2), so **fix one canonical
  bug order** (chronological = the real order) and hold it across all harnesses.
  Answers *"how does it work a realistic messy backlog end-to-end — integration,
  ordering, session degradation?"* The **A-vs-B delta** per bug is itself a signal:
  aces-isolated but-crumbles-cumulative = poor session robustness.

**Delta grading (both scenarios) — the regression-aware gate.** With many latent
bugs present, the suite is *already* partly red at a round's start, so we score by
**delta from the round's starting state**, not against all-green:
- **FAIL→PASS:** the target bug's hidden oracle goes red→green. (Required.)
- **PASS→PASS:** every test **green at round start stays green** (no regression).
- Other latent bugs' already-red tests are **ignored** for this round.

**Protect the oracle.** The harness may freely write/edit tests (graded as quality,
§7), but the grader applies its hold-out oracle **fresh from a clean copy at
scoring time**, so harness edits can't weaken the answer key. Prep note: pick each
bug's oracle test to be one a *correct* fix wouldn't need to rewrite.

- **Controlled variables** — same agents, prompts, and model config across
  opencode/pi within a run; same branch + issue text + oracle across all harnesses.
- **Claude-as-yardstick (the ceiling)** — Claude's fix is the quality reference the
  cheap fixes are judged against (§7).
- **Repeat for rates** — each bug **k≈3** times per cell (Scenario A); report
  success *rate*. (B is one trajectory per harness — a run, not a sample.)
- **Langfuse** collects cost/tokens/turns/tool-calls per run, tagged
  `harness`/`model`/`repo`/`bug`/`scenario`/`run_idx`; its scores API holds
  `passed`/quality.

### 6.1 Intake — establishing context, and the description's *upping-level*

Before any fix, **context must be established**: the worker reads the governing
**instructions** (`AGENTS.md`), the relevant **documentation**, and the
**codebase**, then reasons about what/why/how. This recon — kicked off by the
**prompt** (the ticket) — is the hidden first phase of every run, and *how well a
harness does it is itself something we measure* (§6.3).

Real tickets are noisy. We model description quality as an **upping-level** — how
far the raw issue has been normalized toward a fix-ready spec:

| Level | Contains | Produced by |
|---|---|---|
| **L0** | raw issue, untouched (may be garbage) | reporter |
| **L1** | normalized: symptom · expected behavior + **acceptance criteria** · evidence · scope/area · domain-facts the repo can't supply · go-no-go | **active triage** (the enricher) |
| **L2** | + localized: target file/function named, relevant code mapped | *the harness's recon* |
| **L3** | + prescribed: the fix approach / the diff | *the harness's fix* |

**The line is L1.** Intake normalizes and gates *up to* a well-formed **problem**
(what / why / what-done-means). It must **not** localize (L2) or prescribe (L3) —
that is the recon and fix the harness has to earn. Handing the harness an L2/L3
ticket does the harness's job for it and **flattens the measurement** (every
harness passes a spoon-fed spec).

### 6.2 Active triage — the normalization template + the actionability gate

Flow A's triager (RFC-0002) is **active**: it establishes context and fills a
template, each field one of *given* (in the ticket) / *derivable* (recon fills it
from instructions + docs + code) / *missing*:

```
WHAT      observed / symptom
EXPECTED  desired behavior + acceptance criteria     <- load-bearing
EVIDENCE  repro / trace / example (if any)
SCOPE     area / subsystem   (NOT the file/function — that's the harness)
DOMAIN    world-facts the repo can't supply (e.g. "CMSA = China's agency")
VERDICT   actionable | needs-info(what's missing) | reject
```

"Normalize + fill the gaps" = turn *derivable* → *given* via recon. **Shit-in /
shit-out** = a *required* field stays *missing* after recon → **don't fake it,
gate**. The fatal gap is **`EXPECTED`/acceptance**: subsystem, current behavior,
and domain-facts are usually recon-able, but if the reporter never said what
"fixed" means and neither docs nor code imply it, *no recon recovers intent*.

The gate has a razor-sharp, testable form tied to our whole oracle discipline:

> **actionable ⟺ acceptance criteria are statable ⟺ an oracle (pass/fail test)
> can exist.**

So intake's gate question is literally *"can I write the test that decides
done?"* — yes → normalize to L1 and pass it on; no → **reject**, because without
acceptance there is nothing for a human, a harness, *or* a grader to succeed
against. Same gradeability invariant we enforce on the bug set ("protect the
oracle", §6), applied at intake. Keep it lean: a **template-filler with a reject
valve**, not RAG and not a mini-fixer.

### 6.3 Upping-level as a harness measurement axis

The upping-level is not a fixed setting — it is a **measurement axis**. Run the
same bug at L1 vs L2 across harnesses: **the minimum upping-level a harness needs
to pass = its context-establishment (recon) score.** A harness that fixes a bug
from **L1** is measurably stronger at recon than one that needs **L2**.

Observed (2026-07-23, orrery gate): on `fly-physics` at L0/L1 ("the vis-viva
function returns NaN…"), **both deepseek-v4-pro and sonnet fixed the wrong,
name-matching function** (`visViva`, not the tested `heliocentricSpeed`) — right
logic, wrong target. Pinning to L2 → v4-pro passed. The gap was **recon, not
fix-capability**, and it was invisible until we varied the level.

**Corollary signal — the empty patch.** A description too weak to act on yields
not a *wrong* fix but **nothing** (`look-angles` at L0: 0-line patch, 848 output
tokens). Low engagement / empty diff ⇒ *the spec failed, not the model* — a
detectable **kick-back trigger** from harness → active triage.

**Observed (2026-07-23, isolating experiment): the doc substrate flips L1.**
Same `fly-physics` L1 ticket verbatim, pi+v4-pro, A/B on one variable — a
module-map doc (`src/lib/orbital/README.md`: which of the two vis-viva
implementations serves the fly HUD):
- **No doc → FAIL** (80s, 6 turns): read `orbital.ts`, patched the decoy, done —
  never opened `fly-physics.ts`. Reproduces the historical miss exactly.
- **With doc → PASS** (179s, 18 turns): first grep surfaced the README's mapping
  lines, trajectory deepened, fixed the tested `heliocentricSpeed` correctly.

So the fly-physics gap was **missing repo context, not an impossible ticket**:
recon bridges L1→fix when the repo documents the disambiguation. Consequence:
the cheap lever is the **doc substrate** (module maps that name each subsystem's
owner), not pinning tickets to L2 — pinning does per-ticket what a doc does
once per repo. The substrate is itself a variable now: manifests may carry
`context_files` (injected as problem state by the runner, committed so they
never pollute the graded patch). Caveat: n=1 per cell (no-doc miss is 3
observations across the session; with-doc pass is 1) — k-runs pending.

**Observed (2026-07-23, full matrix on pi+v4-pro, n=1/cell): the axis
discriminates.** All 15 cells run (manifests + results map:
`bakeoff/bugs/README.md`):

| bug | L0 | L1 | L2 | min level |
|---|---|---|---|---|
| fly-physics | FAIL | FAIL · PASS+doc | PASS | **L2** (or L1+repo-doc) |
| credits | FAIL | PASS | PASS | **L1** |
| look-angles | FAIL | PASS | PASS | **L1** |
| 335-merge | PASS | PASS | PASS | **L0** |
| mission-arc | FAIL | PASS | PASS | **L1** |

Readings, all n=1 pending k-runs:
- **Min-upping-level spreads L0/L1/L2 across bugs** — intrinsic context need is
  a real, measurable per-bug property. A true L1 (facts statable in the ticket)
  sufficed for 3/5; only fly-physics needs more, and its missing fact is
  *module topology* — exactly what a repo doc supplies once instead of every
  ticket pinning it (the 2/3 of gate-era L2 pins were unnecessary).
- **Bad tickets are expensive, not just unsuccessful:** every FAIL cost more
  than its passing sibling — credits L0 97k output tokens vs L1 42k;
  look-angles L0 232k vs 52k (4.5×, 27 min wall). Economic case for gating
  garbage *before* the harness burns.
- **Failure shape is bimodal** — empty patch (look-angles historical, 0 lines)
  or expensive wrong-layer grind (same ticket later: 102-line patch into the
  UI/symptom layer, 43 turns). The harness→triage kick-back trigger must key
  on FAIL-at-low-level, not on patch emptiness.
- **Zero regressions in any cell** (PASS_TO_PASS clean) — failures are
  "didn't fix", never "broke". v4-pro fails safe on this set.
- **L2 is cheapest to execute** (fewest turns at equal outcome) but costs
  per-ticket authoring; L1 + doc substrate is the scalable operating point.

**Two scores, kept separate:**
- **Active-triage (intake) score** — L0 garbage → L1-or-correctly-rejected: did it
  produce a solvable problem, correctly reject the unsolvable, classify
  given/derivable/missing right?
- **Harness (fix) score** — L1 → correct fix via *its own* recon (§7), plus the
  **min upping-level to pass**.

## 7. Scoring — keep the dimensions separate (no single number)

Per (harness × model) cell:

| Dimension | Measured by |
|---|---|
| **Success rate** | % bugs the fix passes the hidden oracle (FAIL→PASS) + regression-clean (PASS→PASS), over k (§6) |
| **Min upping-level to pass** | lowest description level (L1 < L2 < L3) at which the harness lands the fix — L1 = strong recon; needs-L2 = weak context-establishment (§6.3) |
| **Quality vs Claude** | judge scores the fix against Claude's fix (correctness beyond the oracle, edge cases, approach) |
| **Fix completeness** | did it do the full job — wrote a regression test? updated affected tests? updated docs on divergence? (the definition of done, §6) — vs a bare code patch |
| **A-vs-B robustness** | per-bug delta between isolated (A) and cumulative (B) success — crumbles-under-backlog = weak session robustness (§6) |
| **$ / successful fix** | tokens × price ÷ successes |
| **$ / attempt** | includes failures |
| **Latency** | wall-clock per fix |
| **Efficiency** | tool calls / turns per fix |
| **Escalations** | how often the worker phoned the architect (§4.2) — lower = stronger |
| **Robustness** | graceful stuck vs runaway/crash |
| **Dev cost** (subjective) | effort to wire + debug the adapter ("configure vs assemble") |

**Judging bias:** if Claude both writes the golden PR *and* judges, it favors
itself. Mitigate: lean on the **objective test floor**, judge on concrete
criteria (fixes the bug? passes tests? handles the golden's edge cases?), operator
spot-checks a few, and/or use a **neutral judge model**.

## 8. Assessment — "which is better in what"

No universal winner. Deliverable = a **decision matrix mapped to our priorities**
(cheap tokens + hands-on control → weight `$ / fix` and dev-control heavily),
per-situation, e.g.:
> "On repo A, opencode+Kimi lands 82% at $0.02/fix in 4 turns and ~90% of Claude's
> quality; pi+Kimi lands 75% at $0.014 in 6 turns but took 2× the dev effort;
> Claude lands 96% at $0.35. → opencode+Kimi is the sweet spot; Claude stays the
> reviewer."

## 9. Prep sequence (ordered)

1. ~~**Pick the two repos' bugs together**~~ **DONE** — 7 (`orrery`) + 8
   (`podcast_scraper`) replay bugs locked in the Appendix, spanning easy →
   investigation-heavy with area spread.
2. **Prep base `C` + hidden oracles** — per repo, tag the coexistence base `C`
   (checkout, no reverts — bugs are already present). Build each bug's hidden
   oracle as a `test_patch`: cherry-pick the fix's shipped test where it has one,
   author a hold-out acceptance test where it doesn't (grader-only, never shown to
   the harness). Fix the **canonical (chronological) bug order** for Scenario B.
   This is the gate that makes grading objective.
3. **Reset mechanism + eval runner** — reset to `C` per round (Scenario A) or run
   the cluster once from `C` (B); apply the hidden `test_patch` at grade time;
   delta-grade; push scores to Langfuse.
4. **Claude adapter** (`claude -p` headless) — likely the reference first.
5. **opencode adapter** (native agents, `serve`).
6. **pi adapter** (embed pi-agent-core; build structured-output/retry — that
   effort is a data point).
7. **Run one row** (one model) across all three on both repos → read the grid.
8. **Add model rows**; write up the decision matrix (RFC-0002 note / new ADR).

## 10. Open decisions to lock

1. **First model** for the opening row (Kimi-K2.7-Code? DeepSeek-V4-Pro?).
2. **k** (runs per bug) — start 3.
3. **Per-role vs single model** within a run (identical mapping either way).
4. **`infra` rung** — rung 1 (`sonnet`/`pro`, cost) vs rung 2 (`opus`/`glm-5.2`,
   more reasoning). Whichever, held constant across opencode/pi. Claude architect
   (rung 3) is fixed = `fable`; Chinese architect = `kimi-k2.6`.
5. **Judge** — Claude (bias, mitigated) vs a neutral model.
6. **App scope** — install on the two real repos (`orrery`, `podcast_scraper`).
7. **Bug list** — orrery **LOCKED** (8 logic bugs, Scenario A per-bug base
   `<fix>^`, Appendix); podcast
   **to rebuild** at its own base `C` in its Phase 0 (candidate pool in Appendix).

## 11. Execution rollout — order of operations + git strategy

**One repo at a time, one harness at a time, troubleshoot as you go, swap models
for round 2, report — then the next repo.** Claude-first each round doubles as the
pipeline shakedown (most reliable harness → debug runner/grading before the flakier
cheap adapters). Lessons flow in three loops: within a harness (troubleshoot),
within a repo (round 1 → round 2), and **across repos (all orrery lessons carry
into podcast from the start)**.

### Per-repo phases (run for `orrery`, then repeat for `podcast_scraper`)

- **Phase 0 · Prep (once, harness-independent):** build the repo's **messy branch**
  (revert all its fixes, surgical slice where flagged); **tag it immutable**
  (`bakeoff/<repo>-baseline`); author the hidden oracles for the no-test bugs;
  reuse shipped tests where they exist; pick the **canonical bug order** for B.
- **Phase 1 · Runner + Claude adapter:** eval runner (reset → dispatch → delta-grade
  vs oracle → Langfuse) + `claude -p` headless adapter.
- **Phase 2 · Round 1** *(Claude models for Claude; Chinese family M1 for
  opencode+pi)* — harness by harness, each doing **Scenario A then B**,
  troubleshooting after each: **1) Claude** (reference/yardstick, shakes out the
  runner) → **2) opencode** (M1) → **3) pi** (M1, structured-output is the risk).
- **Phase 3 · Round 2 (swap model → M2):** apply all Round-1 lessons; **re-run
  opencode(M2) + pi(M2) only** — Claude is run once and its numbers carry over as
  the fixed reference row. Repeat for M3… if wanted (each = a grid row).
- **Phase 4 · Report:** the grid (harness × model, A + B) + decision matrix +
  lessons learned.

Then **cross-repo synthesis:** does the harness/model ranking hold across both
verticals? → RFC-0002 conclusion / a new ADR.

### Git strategy

- **Baseline = each bug's own parent commit `<fix>^`** (Scenario A, per-bug base —
  the runner sets `BASE=${FIX}^` from the manifest). Each bug reproduces in its own
  era where its fix cleanly applies; no reverting onto HEAD. (The earlier
  single-coexistence-base `C` idea was dropped once the set became diverse logic
  bugs spanning many eras — see §3.1 / Appendix.)
- **One long-lived worktree per repo; the eval runner owns git.** The coding
  harness only **edits files** — it does not manage branches.
  `git worktree add ~/.bugfix-fleet/bakeoff/<repo> bakeoff/<repo>-baseline`
- **Scenario A — reset before every attempt** (bug × harness × model × k):
  `git -C <wt> reset --hard bakeoff/<repo>-baseline && git -C <wt> clean -fd`
  — `-fd` **not** `-fdx`: wipes the harness's untracked files but **keeps
  gitignored `node_modules`/`.venv`**, so no dep reinstall across the ~21+ resets
  per harness. Tracked lockfiles are restored by `reset --hard` for free.
- **Capture each result as a patch, not a PR:**
  `git -C <wt> diff bakeoff/<repo>-baseline > results/<repo>/<harness>-<model>-<bug>-<scenario>-k<i>.patch`
  Grade from the patch + Langfuse. Reserve real PRs (§5) for the showcase/judge
  subset — a full grid of PRs is noise.
- **Scenario B — do NOT reset between bugs:** reset once at the start of a harness's
  B run, then let fixes stack; the runner commits after each bug for per-round
  scoring + trajectory diffing.
- **Dep-touching bugs** (a fix that changes a lockfile / dependency): flagged
  per-bug → `npm ci`/`pip install` after reset (since `-fd` kept stale modules).
- **Parallelism (later rounds / cross-repo): one worktree per lane** — they share
  one `.git` object store (cheap), each needs its own deps install once. Round 1
  stays single-worktree.
- **Two repos = two worktrees + two baseline tags**; podcast's is built in its
  Phase 0.

## Appendix — the locked replay bug set

Anchored on **fix commits** (§3.1; issue refs unreliable on fast repos). Grading is
**unit-test only — no playwright/visual** (that was the lesson from the first
orrery draft: UI/CSS/3D defects can't be graded deterministically). So the set is
**logic bugs**, and the oracle is a `src/**/*.test.ts` — **Opt1** = the fix shipped
its own test (reuse it, faithful + free), **Opt2** = we author one.

**Base model, corrected:** **Scenario A uses per-bug base `<fix>^`** — each bug in
its own era. That drops the "one shared base" constraint (which was forcing a
UI-heavy cluster) and lets us pick the *best logic bugs from any era*. **Scenario
B** = the subset of these that happens to coexist at one base (June–July here), run
cumulatively — derived when we build B, not now. Nothing about A/B measurement
changes; only where each bug's baseline sits.

### `chipi/orrery` (TS) — 6 **run-verified** logic bugs · Scenario A, per-bug base `<fix>^`
All six verified end-to-end (`bakeoff/verify.sh`): oracle RED at `<fix>^`, GREEN
after the golden fix. Oracle = the unit test the fix shipped (Opt1), except #251
(authored). Manifests in `bakeoff/bugs/`.

| fix commit | bug (problem statement) | area | oracle test | RED→GREEN |
|---|---|---|---|---|
| `0d6644f9` | vis-viva speed returns **NaN** beyond transfer apohelion (fall back to circular; 0 at r=0) | orbital physics | `orbital/fly-physics.test.ts` | 2→0 ✓ |
| `19fb2f17` | transfer-arc geometry ignores **arrival V∞** (endpoints/mid-arc bend wrong) | trajectory math | `mission-arc.test.ts` | 1→0 ✓ |
| `a5cf0981` | observer look-angles use wrong geodetic model → **WGS84** wrong | astro coord math | `satellite/satellite.test.ts` | 2→0 ✓ |
| `0cb1f36` | `mergeFlightEvents` drops rich per-event **labels/descriptions** (#335) | data merge | `mission-event-merge.test.ts` | 2→0 ✓ |
| `aaaab7f6` | CMSA/SpaceIL/CSA/USAF **misgrouped** under Wikimedia | data mapping | `credits-grouping.test.ts` | 1→0 ✓ |
| `78a79e8` | `.jpg`-path writes hold **non-JPEG bytes** (#251) | image bytes | `scripts/lib/image-bytes.test.ts` (authored) | 1→0 ✓ |

**Dropped in verification** (kept honest — they didn't survive the red-at-base gate):
- `feb64eaef` (image URL normalization) — broad "deep-review" commit; the oracle
  reproduced (38 red) but the isolated fix left 33 red — not cleanly isolable.
- `9ca0f2b3` (audio-tour dead route) — the fix is a base-path prepend, but its
  shipped test only checks *route existence* (orthogonal) → 0 red at base.

*Backfill to 8 later from the logic-bug pool if wanted; 6 verified is enough for
the first run.*

*7 of 8 ship their own faithful test (Opt1); only #251 is authored (Opt2). Three
hard physics/math bugs anchor the top; nothing needs a browser. Ladder: 1 easy-med
/ 4 medium / 3 hard.*

### `chipi/podcast_scraper` (Py back + UI + infra) — ⚠ TO REBUILD at its own base `C`
> The 8 below were picked **scattered across history** (PRs #173…#1196) before the
> coexistence-base model. They must be **re-selected around a podcast base `C`** in
> podcast's Phase 0, the same way orrery was. Kept here as the candidate pool:
| # | bug | fix ref | area | difficulty | test |
|---|---|---|---|---|---|
| #161 | summarizer init fails importing `Pipeline` from transformers | PR #173 | backend/deps | easy | author |
| #228 | dashboard `# noqa: E501` hack + slowest-tests extraction broken | PR #239 | docs/reporting | easy | author |
| #696 | focused episode not auto-selected on Graph canvas | PR #700 *(slice: `GraphCanvas.vue`)* | viewer-ui | easy | author |
| #1088 | DR drill: empty `SHA_SHORT` trips `override_image_sha` guard | PR #1196 *(slice: `drill-deploy.yml` + its test)* | infra-ci | easy-med | ✓ |
| #818 | `/api/corpus/episodes` ignores `page_size` + inner cap | PR #824 *(slice off #820/#821 UI bits)* | api/backend | medium | ✓ |
| #823 | `corpus_manifest.json` `cost_rollup` all zeros | PR #848 *(slice: 3 files)* | db-data/obs | medium | ✓ |
| #644 | single- vs multi-feed runs write different corpus dir shapes | PR #646 *(slice: 3 files)* | db-data | med-invest | ✓ |
| #1056 | recurring network-feed hosts stay `SPEAKER_*` (unnamed) | PR #1059 | backend/search | investigation | ✓ |

*Spread: all six area buckets; easy→investigation ladder; 5 ship tests, 3 authored.*

## References
- RFC-0002 — the fleet design (this is its Phase 0 plan).
- `src/worker/types.ts` — the harness-agnostic `Worker` seam (3 adapters).
- Langfuse (`homelab:4000`) — measurement rig; model pricing registered → $ cost.
- Grafana "Bug-fix Fleet" — the `flow:` funnel.
