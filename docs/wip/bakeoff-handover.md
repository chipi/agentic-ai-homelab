# Handover — bug-fix fleet bake-off (session 2026-07-23)

Fresh-eyes handover for whoever picks up the RFC-0002 bake-off next. Read this
top-to-bottom once, then work from the pointers. **North star:**
[`bugfix-fleet/BAKEOFF.md`](https://github.com/chipi/agentic-ai-homelab/blob/main/bugfix-fleet/BAKEOFF.md).
**Architecture:** [`docs/rfc/RFC-0002`](../rfc/RFC-0002-autonomous-bug-fix-fleet.md).

## TL;DR — where we are

The eval pipeline **works end-to-end** and the 5-bug orrery set is **green on the
base config** (`pi + deepseek/deepseek-v4-pro`). The session's real output is a
**design shift**, now written into BAKEOFF §6.1–6.3 + RFC-0002: **bug-description
quality is the dominant variable**, and *how much a description must be "upped" to
succeed is itself a harness measurement axis*. Next up is building/measuring
**active triage** (the L1 normalizer+gate) — but the immediate recommended step is
one cheap experiment (see "Next iteration").

**Nothing is pushed.** 4 local commits sit on `main` ahead of `origin/main`,
awaiting operator approval to push (rule #1). Do **not** push without an explicit
"push/ship it".

## The base config (decided this session)

- **Harness = pi**, **model = `deepseek/deepseek-v4-pro`**. Chosen over opencode
  for lowest friction (single binary, one clean event stream, no plugin/state-db
  fights). **Swappable** — `PI_MODEL` / `OPENCODE_MODEL` / `CLAUDE_MODEL` env vars
  are already parameterized in the adapters.
- **Gate model = deepseek-v4-pro, NOT sonnet.** A bug is "valid" only when this
  cheap base worker solves it red→green from its description alone. (We tried
  sonnet-as-gate first; the operator flipped it — v4-pro is cheap enough to iterate
  freely and is the actual base-worker tier.)

## The 5-bug set — all PASS the gate

Manifests: `bugfix-fleet/bakeoff/bugs/orrery-*.json`. All verified PASS on
`pi + deepseek-v4-pro` on 2026-07-23.

| Bug | Gate | Description was |
|---|---|---|
| orrery-fly-physics | PASS | **re-pinned** — name-trap "vis-viva fn" → two exist; pinned `heliocentricSpeed` (fly-physics.ts), warned off `visViva` decoy |
| orrery-credits | PASS | **re-pinned** — added exact mappings (CMSA→cnsa, SpaceIL→spaceil, USAF→us-space-force, CSA primary→csa) + substring guard |
| orrery-look-angles | PASS | **re-pinned (2 iters)** — described RA/Dec symptoms but oracle grades `observerEci` WGS84 radius; retargeted + added altitude param |
| orrery-335-mission-event-merge | PASS | already good |
| orrery-mission-arc | PASS | already good |

**Dropped:** `orrery-image-bytes` → `bugfix-fleet/bakeoff/bugs/dropped/` (reason in
that folder's README): only structure-coupled oracle in the set — a feature-add
with no stable behavioral interface; `validate-data` is unusable at base (missing
LFS binaries). Do not resurrect without a solution-agnostic oracle.

## Key decisions taken (with rationale)

1. **Gate = v4-pro, base = pi.** (above)
2. **image-bytes dropped.** No solution-agnostic oracle possible.
3. **3/5 descriptions re-pinned to L2** to pass the gate — but note the *pinning
   itself* became the central learning (it does the harness's recon job; see
   design below). The current manifests are L2 (localized). To measure harnesses
   we will need L1 versions too (not yet authored).
4. **OpenRouter data policy = zero-retention only.** Empirically mapped: 14
   providers allowed (StreamLake, Baidu, GMICloud, Novita, DeepInfra, DigitalOcean,
   Alibaba, SiliconFlow, Venice, AtlasCloud, BaseTen, WandB, Together, Fireworks);
   **DeepSeek first-party blocked** (trains on inputs). **Reachable models:
   `deepseek-v4-pro`, `z-ai/glm-5.2`, `moonshotai/kimi-k2.6` only.** All other
   deepseek (`v3.2`, `v3.1-terminus`, `r1-0528`, `chat-v3.1`) and **both qwen
   coders are 404-blocked** — no per-provider workaround (filter is per-endpoint).
   Operator chose to **keep the strict policy** (do not relax to test qwen/older
   deepseek unless they say so).

## The major learning + the design (this session's real output)

**Learning:** description quality dominates model choice. Proof: on `fly-physics`
with a vague spec, **both v4-pro AND sonnet fixed the wrong (name-matching)
function** (`visViva` not the tested `heliocentricSpeed`) — right logic, wrong
target. Pinning the target → v4-pro passed. The "model capability" story chased for
much of the session was an artifact of under-specified descriptions. (Retraction on
file: an earlier "sonnet navigates better" claim was refuted by sonnet's identical
fly-physics miss.)

**Design (written into BAKEOFF §6.1–6.3, RFC-0002 role, and memory):**
- **Upping-level L0→L3:** L0 raw · **L1 normalized + gated (active triage's ceiling)**
  · L2 localized (harness's recon) · L3 prescribed (harness's fix). Enricher must
  never cross past L1 or it flattens the measurement.
- **Active triage** = establish context (AGENTS.md + docs + code) → fill a template
  (WHAT / EXPECTED+acceptance / EVIDENCE / SCOPE / DOMAIN / VERDICT), each field
  *given | derivable-by-recon | missing* → **gate**. Gate invariant:
  **actionable ⟺ acceptance statable ⟺ an oracle can exist.** Missing acceptance
  that recon can't recover → **reject, never fake** ("shit-in/shit-out").
- **Min upping-level to pass = the harness's recon score** (new §7 row).
  Empty-patch / low-engagement = "spec failed, not model" = kick-back trigger.
- **Two separate scores:** intake (garbage→L1-or-reject) vs harness (L1→fix).
- Keep it lean: active triage is a **template-filler with a reject valve**, NOT RAG
  and NOT a mini-fixer.

Memory: `memory/project_bakeoff_description_is_lever.md` (full taxonomy of bad
descriptions + the fix-ready-spec recipe).

## Pipeline mechanics — how to run

Everything under `bugfix-fleet/bakeoff/`. Run artifacts + the orrery worktrees live
**outside the repo** at `~/.bugfix-fleet/bakeoff/` (`orrery-src` = clean clone,
`orrery` = the scratch worktree, `results/<bug>/<harness>/`).

Run one bug:
```
cd bugfix-fleet/bakeoff
export PI_MODEL="deepseek/deepseek-v4-pro" BAKEOFF_RUN_IDX="label"
./run.sh bugs/orrery-credits.json pi          # harness = pi|opencode|claude
```
`run.sh` (SWE-bench-style): reset worktree to `<fix>^` → apply hidden oracle → run
(record FAIL_TO_PASS + PASS_TO_PASS) → hide oracle → hand harness ONLY the
description → capture code-only patch → re-apply oracle fresh → delta-grade →
push to Langfuse. Verdict PASS iff every FAIL_TO_PASS goes green AND no PASS_TO_PASS
regresses. Golden-path check: `./verify.sh` (red at base → green at fix).

Adapters (`harnesses/{claude,opencode,pi}.sh`) all use the IDENTICAL fix prompt and
emit their native JSON; `run.sh` unifies cost/token/turn parse across the three
shapes. opencode uses `--pure` (disables oh-my-openagent plugin so plain edits are
captured). All three tuned to output plain edits + a result stream.

## Langfuse

Dedicated project **`agentic-bakeoff`** on self-hosted `http://homelab:4000`.
Every run auto-pushes a trace + per-call generations + `passed` score via
`langfuse_push.py`. Source attribution: `userId=harness`, `sessionId=bug`,
`environment=bakeoff`, tags `[bakeoff, harness, model, bug, run:N]`. Creds in
**`~/.bugfix-fleet/bakeoff/langfuse.env`** (outside repo, gitignored). Verified
`207/201`. Note: **pi/opencode report `$0` cost natively** (tokens present) — to
get cost, register model pricing in Langfuse Settings→Models (not yet done).

## Gotchas (bit us this session)

- **`NODE_OPTIONS`** — the harness env carries a broken `--require
  restore-node-options.cjs` preload. `run.sh` overrides it
  (`--max-old-space-size=4096`); in ad-hoc shells `unset NODE_OPTIONS` or vitest/tsx
  dies with "Cannot find module restore-node-options.cjs".
- **Shared worktree → no parallel runs.** All bugs use `~/.bugfix-fleet/bakeoff/orrery`;
  `run.sh` resets it each run. Run bugs **sequentially**.
- **Reasoning models don't work as agents in pi.** `r1-0528` stalled 26 min
  (0-CPU, retry-loop on a 404). Use tool-trained models only.
- **`timeout` is not on macOS** — use `perl -e 'alarm N; exec @ARGV' ...`.
- **Broad `grep -r ~/Projects`** balloons on huge single-line files (a runaway hit
  32 GB). Scope with `--exclude-dir` / use `rg`.
- **mkdocs `--strict`** gates `docs/**` — run `make docs-build` (exit 0) before any
  docs commit. Links from `docs/` to files outside it must be absolute
  github-blob URLs.

## Git state — UNPUSHED, do not push without approval

Several local commits ahead of `origin/main` — source of truth is
`git log --oneline origin/main..HEAD`. As of this handover:
```
fc826ad docs(wip): bake-off handover note (this file)
07c08dd bakeoff+RFC-0002: active triage — context-establishment, upping-level, two scores
5cfbda2 bugfix-fleet(bakeoff): gate bug set on pi+deepseek-v4-pro; pin 3 descriptions, drop image-bytes
bacbad7 bugfix-fleet(bakeoff): opencode+pi adapters, unified cost parse, Langfuse push
da1a9f8 bugfix-fleet(bakeoff): Phase 1 — working claude adapter + runner (smoke PASS)
```
(A follow-up commit updates this list; run the command for the live set.)

## Next iteration (recommended order)

1. ~~**Isolating experiment**~~ **DONE 2026-07-23 (later session): answer =
   missing-context.** A/B on pi+v4-pro, same L1 ticket verbatim: no doc → FAIL
   (decoy-only, 6 turns); with `src/lib/orbital/README.md` module map → PASS
   (18 turns, correct target). Result + consequence written into BAKEOFF §6.3.
   Runner grew a `context_files` manifest hook (substrate committed as problem
   state, never in the graded patch). Manifests: `bugs/orrery-fly-physics-L1.json`
   (+`-noctx` control). Also fixed: all 3 adapters hung inheriting a held-open
   stdin (`< /dev/null` now forced — pi sat 11 min at 0 CPU).
2. **Ticket triples.** Author each of the 5 bugs at {L0 degraded, L1 normalized,
   L2 pinned}. (We have L2 now; originals ≈ L0/L1.) This is the upping-axis test
   matrix.
3. **Build active-triager** as a thin worker call (template + given/derivable/missing
   + oracle-exists gate). Feed L0 tickets → emits L1 or correctly rejects = intake
   score.
4. **Measurement grid:** harness × bug × level → min-upping-level per harness.

## NOT done / NOT verified (explicit gaps)

- **Only v4-pro passes are verified.** glm-5.2 + kimi-k2.6 were run on credits/
  fly-physics **before** the description pins and the drop — those FAILs are stale
  (mixed with the mis-authored descriptions). No clean harness-comparison grid exists
  yet.
- **L1 ticket versions not authored** — current manifests are L2. The upping-axis is
  designed but unmeasured.
- **Active-triager not built** — design only.
- **`podcast_scraper` repo not started** — bake-off Appendix lists 8 candidate bugs
  "to rebuild"; orrery is the only live repo.
- **Model pricing not registered in Langfuse** — pi/opencode cost shows `$0`.
- **k-runs (repeat for rate)** — every result so far is n=1 per cell.
- **Scenario B (cumulative backlog)** — not exercised; only Scenario A (isolated).
- **opencode as base** — validated it runs (`--pure`) but not gated across the set.

## Key pointers

- North star: `bugfix-fleet/BAKEOFF.md` (design in §6.1–6.3, scoring §7)
- RFC: `docs/rfc/RFC-0002-autonomous-bug-fix-fleet.md` (Active triager role)
- Existing triage code (the seed to evolve): `bugfix-fleet/src/flows/triage.ts`
- Agent defs: `bugfix-fleet/agents/*.md`
- Runner/adapters/oracles: `bugfix-fleet/bakeoff/{run.sh,verify.sh,harnesses/,oracles/,langfuse_push.py}`
- Memory: `project_bakeoff_description_is_lever.md`, `project_bugfix_fleet_bakeoff.md`
- Off-repo state: `~/.bugfix-fleet/bakeoff/` (worktrees, results, langfuse.env)
