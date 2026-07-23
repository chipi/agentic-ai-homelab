# Handover — bug-fix fleet bake-off (updated end of 2026-07-23, session 2)

Fresh-eyes handover for whoever picks up the RFC-0002 bake-off next. Read this
top-to-bottom once, then work from the pointers. **North star:**
[`bugfix-fleet/BAKEOFF.md`](https://github.com/chipi/agentic-ai-homelab/blob/main/bugfix-fleet/BAKEOFF.md)
(design §6.1–6.3, results are written inline there). **Architecture:**
[`docs/rfc/RFC-0002`](../rfc/RFC-0002-autonomous-bug-fix-fleet.md).

## TL;DR — where we are

The instrument is **built, calibrated, and hardened**; the first real science
is done. On the base config (`pi + deepseek/deepseek-v4-pro`), the full
**L0/L1/L2 upping-level matrix** is measured (15 cells + 4 doc-flip cells,
all n=1), and the day's durable insight is the **two-factor model**, measured
from both directions:

- **Acceptance** (what "fixed" means) must live in the **ticket** — only
  normalization to L1 flips verdicts. Docs never did (0/4 at L0).
- **Topology** (which of the look-alike functions, what owns what) belongs in
  **repo module docs** — they flip *localization* (3/4 scope-flips at L0) and
  turn fly-physics L1 FAIL→PASS.

This directly validates RFC-0002's active-triage L1-gate design: triager and
doc substrate are complementary halves. Everything is committed AND pushed
(homelab `main` @ `9e8fd7f`; orrery branch `docs/module-readmes` @
`4d3ecd1c9c`, Lock-check green, full CI runs when a PR opens).

## Measured results (all n=1, pi+v4-pro, 2026-07-23)

| Bug | L0 | L1 | L2 | min level |
|---|---|---|---|---|
| fly-physics | FAIL | FAIL · PASS+doc | PASS | L2 or L1+repo-doc |
| credits | FAIL | PASS | PASS | L1 |
| look-angles | FAIL | PASS | PASS | L1 |
| 335-merge | PASS (n=2) | PASS | PASS | L0 |
| mission-arc | FAIL | PASS | PASS | L1 |

Plus: FAILs cost 2–4.5× their passing siblings (look-angles L0: 232k
out-tokens, 27 min); failure shape bimodal (empty patch OR wrong-layer
grind); zero regressions in any cell. Full readings: BAKEOFF §6.3. Cell map +
results: `bugfix-fleet/bakeoff/bugs/README.md`.

## What was built this session (beyond session 1's runner+adapters)

- **`context_files` substrate hook** in `run.sh` — manifest lists docs to
  inject as committed problem state (never pollutes the graded patch).
- **Budget cap** — `BAKEOFF_MAX_WALL` (default 1200s); runaway attempts cut,
  graded on partial patch, marked `BUDGET_EXCEEDED`. Smoke-tested.
- **Scope signal** — patch's non-test files vs manifest `code_files` →
  `scope_hit` + off-scope list in `result.tsv` (v2: 9 columns, +scope +budget).
- **Kick-back protocol contract** — BAKEOFF §6.2 (trigger = verdict; payload
  = the failed attempt as evidence). Wired the day the triager exists.
- **Module-README convention** — guide + validation
  (`templates/module-readme-guide.md` here; orrery got its own copy at
  `docs/guides/module-readme-guide.md` + 3 example maps (`src/lib/ar/`,
  `scripts/`, `tests/e2e/`) + AGENTS.md/CLAUDE.md wiring, branch
  `docs/module-readmes`). Validate docs by **localization quiz**, never by
  end-to-end fix success.
- **Langfuse model pricing registered** (v4-pro/v4-flash/glm-5.2/kimi-k2.6 at
  OpenRouter rates) — runs from now on show real $; older traces stay $0.
- **Adapter stdin fix** — all three adapters force `< /dev/null`; a headless
  harness inheriting a held-open stdin socket hangs silently (pi: 11 min,
  0 CPU). Do not remove.

## The base config + gate (unchanged from session 1)

Harness = **pi**, model = **`deepseek/deepseek-v4-pro`** (swappable via
`PI_MODEL`/`OPENCODE_MODEL`/`CLAUDE_MODEL`). Gate: a bug is valid only when
this config solves it red→green from its description. All 5 canonical
manifests pass the gate. OpenRouter zero-retention policy limits reachable
models to v4-pro/v4-flash, glm-5.2, kimi-k2.6 (qwen + older deepseek 404).
pi auth: `~/.pi/agent/auth.json`; no env key needed.

## How to run

```
cd bugfix-fleet/bakeoff
export PI_MODEL="deepseek/deepseek-v4-pro" BAKEOFF_RUN_IDX="label"
./run.sh bugs/orrery-credits.json pi        # pi|opencode|claude
```
Worktrees/results/langfuse.env live outside the repo at
`~/.bugfix-fleet/bakeoff/`. **Sequential runs only** (shared worktree).
Results per cell overwrite by (id, harness) — re-running a cell replaces its
artifacts, so label sweeps via `BAKEOFF_RUN_IDX` and treat Langfuse as the
run ledger. Gotchas from session 1 still apply (NODE_OPTIONS preload, no
macOS `timeout` → `perl -e 'alarm N; exec @ARGV'`, mkdocs strict on docs/**).

## Next iteration (recommended order)

1. **k=3 repeats on the decisive cells** (~30 min, cents): fly-physics
   L1-noctx / L1+doc, credits-L1, look-angles-L1, mission-arc-L0. Turns n=1
   observations into rates before anything is built on them.
2. **opencode column** — same model, same matrix (opencode adapter validated
   with `--pure`, never gated across the set). First true harness-vs-harness
   row; substrate policy: harness rows run substrate-OFF (raw recon), one
   substrate-ON row separately.
3. **Build the active-triager** (RFC-0002 role, thin worker call): template +
   given/derivable/missing + oracle-exists gate. The measured L0→L1 pairs are
   its ready-made eval set (intake score = L0 garbage → L1-or-reject).
4. **Orrery module-README PR** — open PR from `docs/module-readmes`, full CI
   proves the docs-only change; merge is operator's call.
5. Then: measurement grid rows (glm/kimi), Scenario B, podcast_scraper Phase 0.

## NOT done / NOT verified (explicit gaps)

- **Everything is n=1** except 335-L0 (n=2). No rates.
- **No harness comparison exists** — opencode/claude columns unmeasured on
  the current (post-pin) bug set; old glm/kimi runs are stale/pre-pin.
- **Active-triager not built** — design + kick-back contract only.
- **Scenario B (cumulative backlog)** — never exercised.
- **podcast_scraper** — not started; candidate bugs in BAKEOFF Appendix need
  re-selection at their own bases.
- **Doc-flip caveat** — substrates were written by an author who knew the
  bugs (module-intent only, but not blind). Blind-authoring is the clean
  protocol if the finding needs defending.
- **Langfuse $** — only future runs get cost; all 2026-07-23 traces show $0.

## Key pointers

- North star + all results: `bugfix-fleet/BAKEOFF.md` (§6.1–6.3, §7)
- Cell map: `bugfix-fleet/bakeoff/bugs/README.md` · substrates: `bakeoff/substrates/`
- Runner/adapters: `bugfix-fleet/bakeoff/{run.sh,harnesses/}` · Langfuse project `agentic-bakeoff` @ homelab:4000
- Module-README guide (operator template): `templates/module-readme-guide.md`
- RFC: `docs/rfc/RFC-0002-autonomous-bug-fix-fleet.md` (Active triager)
- Memory: `project_bugfix_fleet_bakeoff.md`, `project_bakeoff_description_is_lever.md`
