# bugfix-fleet — autonomous bug-fix fleet (MVP)

Prototype for **RFC-0002**. Cheap-harness workers fix `bug`-labeled GitHub issues
on a long-lived `fixes` branch; Claude reviews the batch PR (Phase 1). Runs on the
`homelab` Mac mini. **Unpolished — this is the Phase-0 bake-off**, not production.

## What's here (MVP scope)

- **Flow A — Triage** (`src/flows/triage.ts`): `bug` → structured verdict → labels + recommendation.
- **Flow B — Fix** (`src/flows/fix.ts`): `flow:approved` → worktree → fix → local tests → land on `fixes`.
- **Worker seam** (`src/worker/types.ts`): one interface, two adapters —
  **Pi** (`piAdapter.ts`) and **opencode** (`opencodeAdapter.ts`). Flip `HARNESS`
  to run the same flows on either → the bake-off.
- **Deterministic orchestrator** (`src/orchestrator.ts`): advances issues by
  swapping `flow:` labels (the state machine); LLMs only at the worker leaves.
- **GitHub App auth** (`src/github/appAuth.ts`): installation-token dance hidden.
- **Langfuse trace** (`src/observability/langfuse.ts`): every leaf, for the model/cost comparison.

## Status

Skeleton wired end-to-end; the two adapter `TODO(pi)`/`TODO(opencode)` blocks are
the actual harness integration — filling them in **is** the Phase-0 spike. Not yet
included (Phase 1): the whole-PR review + feedback loop, batch-PR cut, deploy.

## Run (once the App + sandbox + creds exist)

```sh
npm install
cp .env.example .env   # fill via sops on the mini
npm run typecheck
# HARNESS=opencode npm run dev   # or HARNESS=pi
```

## Bake-off protocol

The **north star + full evaluation methodology** lives in **[BAKEOFF.md](BAKEOFF.md)**
— how to think about tool calls, the benchmark-difficulty trap, the eval setup,
scoring dimensions, and how to assess "which harness is better at what." Read
that before wiring the opencode/pi adapters.
