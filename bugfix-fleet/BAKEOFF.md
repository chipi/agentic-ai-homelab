# Bake-off — north star & evaluation methodology

**Status:** planning (the fleet pipeline is proven on the `direct` baseline;
this doc governs how we evaluate the real harnesses).
**Relates to:** RFC-0002 (the fleet). This is the detailed plan for its Phase 0.

The question this answers: **which fix-engine — `direct` (baseline), `opencode`,
or `pi` — fixes bugs better, and *better at what*, on identical tasks?** And the
sharper strategic question underneath: is a harness worth its cost over a naive
single-shot, and if so, which harness.

---

## 1. Mental model — what "running an agent" actually means

There are two fundamentally different ways the fleet can "run an agent" behind
the same `Worker` interface (`triage` / `fix`):

**`direct` — a single-shot text transform (NOT a harness).**
Our code reads the files, stuffs them all into one prompt, makes **one** chat
call, parses the JSON, writes the files, runs the tests. The model never decides
what to read, never uses a tool, never iterates. All the "agent" behavior lives
in *our* glue (`directAdapter.ts`). It works **only** when the whole repo fits in
one prompt.

**A harness (`opencode` / `pi`) — an agentic loop.**
The harness hands the model **tools** (`read`, `edit`, `bash`, `grep`) and runs a
**loop**: the model itself greps, opens the relevant file, maybe runs the test,
edits, re-runs, confirms. Multi-step, tool-using, self-directed. This is what
`direct` fakes by hand — and the only thing that scales to real repos you can't
fit in a prompt.

`direct` is kept in the bake-off as the **baseline / floor**: "how far does a
naive single-shot get?" The harnesses are measured against it.

## 2. Tool calls — how to think about them

In a harness a fix is a **loop of turns**; each turn may make a **tool call**.
Tool calls are the agent's *moves*, and they matter three ways:

- **Cost (the big one).** Every turn re-sends the **accumulating transcript**
  (all prior tool calls + their outputs). So an 8-step fix costs *more* than 8
  single calls — context grows each turn. This is why a harness fix costs more
  than a `direct` single-shot, and why an *inefficient* agent (redundant greps,
  re-reads) is expensive.
- **Capability.** Tool calls are how the agent investigates a repo it's never
  seen. No tools → only what's in the prompt.
- **Efficiency.** A good agent reaches the fix in few, well-chosen moves; a bad
  one thrashes. **Tool-call count + trajectory is itself a quality signal.**

Langfuse captures this: one trace = the whole fix, a span per turn / tool call →
"opencode fixed #7 in 5 turns / 3 tool calls / $0.004" vs "pi in 9 turns / 7 /
$0.011."

## 3. ⚠️ The trap — the benchmark must REQUIRE agentic behavior

**The toy sandbox (single-file bugs that fit in one prompt) is too easy to
differentiate harnesses.** `direct` wins trivially (no exploration needed) and
opencode-vs-pi look identical because neither needs its agentic muscle. **You'd
learn nothing.**

To separate the harnesses, the benchmark must contain bugs that need agentic
behavior:
- **multi-file** changes,
- bugs that need **investigation** to locate (not stated in the issue),
- a repo **big enough that you can't stuff it all in one prompt**,
- fixes that need **running tests / reproducing** mid-way.

**Building a harder benchmark is the most important prep step** — more important
than wiring the adapters. Without it the bake-off is uninformative.

## 4. Evaluation setup

Four parts:

1. **Fixed benchmark set** — N bugs with **known-correct outcomes (tests)**,
   identical across harnesses, plus a **reset mechanism** so every run starts
   from the same repo state.
2. **Controlled variables** — same **model per role**, same prompts, same tasks.
   **Vary only the harness.** (Else you measure model-vs-model, not
   harness-vs-harness.)
3. **Objective grading** — each bug has a test → grading is automatic: *fix
   landed + tests green + regression-clean?* Pass/fail, no judgment call. (Reuse
   the regression-aware gate: turned ≥1 failing test green, broke none.)
4. **Repeat for rates, not points** — tool-loops are non-deterministic → run each
   bug **k times per harness** (k≈3–5) and report a **success rate**.

**Langfuse is the collection + scoring layer.** Its scores API attaches
`passed=1/0`, `cost`, `tool_calls`, `turns` to each trace → it aggregates
success-rate + cost per harness. Tag every run with `harness`, `bug`, `run_idx`.

## 5. Scoring — keep the dimensions separate (no single number)

One row per harness:

| Dimension | Measured by | Why it matters |
|---|---|---|
| **Success rate** | % bugs fixed + tests green + regression-clean (over k runs) | primary metric |
| **$ / successful fix** | total tokens × price ÷ successes | cheap-fleet is the point |
| **$ / attempt** | includes failures | flailing is costly even when it fails |
| **Latency** | wall-clock per fix | throughput |
| **Efficiency** | tool calls / turns per fix | cleaner trajectory = better |
| **Robustness** | fails gracefully (stuck) vs runaway/crash | flash went runaway once |
| **Review rounds** (whole-pipeline) | rounds to converge / stuck rate | interaction quality |
| **Dev cost** (subjective) | effort to wire + debug the adapter | "configure vs assemble" |

Do **not** average into one score — the dimensions matter differently to us.
Present a **Pareto** view (X cheaper-but-lower-success, Y pricier-but-higher).

## 6. Assessment — "which is better in what"

**There is no universal winner.** The deliverable is a **decision matrix mapped
to our priorities**, framed per-situation:

- **direct** — cheapest + fastest, trivial/small-context bugs only. Keep as the
  "trivial fast-path."
- **opencode** — turnkey, **native structured output**, real tool-use; heavier
  runtime, per-call overhead.
- **pi** — minimal, we own every layer, potentially leaner; we **build** the
  scaffolding (structured output, retry).

Our stated priorities — **cheap tokens + hands-on control** — mean we weight
**$/fix** and **dev-control** heavily. That tilts toward **pi** *if* its success
rate holds up, toward **opencode** *if* pi's success suffers from the DIY
scaffolding. **The data decides.**

Target deliverable, one honest sentence, e.g.:
> "On the hard benchmark, opencode fixes 85% at $0.02/fix in 4 turns; pi fixes
> 78% at $0.014/fix in 6 turns but took 2× the dev effort; direct fixes 40%
> (simple bugs only) at $0.003. → opencode for reliability, pi if the
> cost/control trade is worth the build, direct as the fast-path."

## 7. Prep sequence (ordered by what actually matters)

1. **Build a harder benchmark** — a small but realistic multi-file repo with
   bugs that need investigation. *Everything depends on this.*
2. **Reset mechanism + eval runner** — reset repo to a known state; run each bug
   k times per harness; grade by tests; push `passed`/`cost`/`turns` scores to
   Langfuse.
3. **Wire the opencode adapter** (more turnkey) → bake off ONE leaf (triage) or
   the fix leaf, direct-vs-opencode; read the Langfuse delta.
4. **Wire the pi adapter** → add it to the same bake-off (time-box the DIY
   structured-output build; that effort is a data point).
5. **Expand to the whole pipeline** once the per-leaf signal is clear.
6. **Write up the decision matrix** → an RFC-0002 discussion note / new ADR.

## 8. Open decisions to lock before building

1. **Scope first** — bake off *one leaf* (triage or fix) or the *whole
   pipeline*? (Rec: one leaf first — fast, isolates the axis.)
2. **k** — how many runs per bug for a stable rate? (Rec: start k=3.)
3. **opencode topology** — one long-running `opencode serve` reused, or
   per-call? (Rec: reuse.)
4. **pi effort time-box** — how long to invest in pi's structured-output layer
   before judging? (Set a limit.)
5. **Benchmark size/shape** — how many bugs, how hard, what repo? (The #1 prep.)
6. **Fairness** — same model per role across harnesses (confirm the mapping).

## References
- RFC-0002 — the fleet design (this is its Phase 0 plan).
- The `Worker` interface (`src/worker/types.ts`) — the harness-agnostic seam.
- Langfuse (self-hosted, `homelab:4000`) — the measurement rig; model pricing
  registered so cost computes in $.
- Grafana "Bug-fix Fleet" dashboard — the `flow:` pipeline funnel.
