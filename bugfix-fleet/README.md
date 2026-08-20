# bugfix-fleet — autonomous bug-fix fleet (MVP)

Prototype for **RFC-0002**. Cheap-harness workers fix `bug`-labeled GitHub issues
on a long-lived `fixes` branch; Claude reviews the batch PR (Phase 1). Runs on the
`homelab` Mac mini. **Unpolished — this is the Phase-0 bake-off**, not production.

## ⚡ Current state — read first (2026-08-19, saves you the archaeology)

- **Two different things are called "bugfix-fleet" — don't conflate them:**
  1. **This TS MVP** (`src/main.ts`) — the GitHub issue → triage → fix → PR loop.
  2. **The bake-off rig** (`bakeoff/*.sh`) — the pi-vs-opencode *measurement study*
     that shells the real `pi`/`opencode`/`claude` CLIs. Separate codepath entirely.
- **Harness = `direct` only.** The `pi`/`opencode` adapters are Phase-0 **stubs that
  `throw "not implemented"`** — don't set `HARNESS=pi`/`opencode` expecting them to
  run (it prints "adapter not wired yet" and falls back to direct). This is fine:
  **the bake-off concluded the harness barely moves fix-rate — ticket quality is the
  lever** (BAKEOFF §8; [`docs/history/0005-bakeoff-matrix-arc.md`](../docs/history/0005-bakeoff-matrix-arc.md)).
  `pi + v4-pro` was the vindicated cheap *worker seat*; Claude = the *reviewer* gate.
- **LLM routing goes through the homelab LiteLLM gateway** (not OpenRouter-direct):
  `LLM_BASE_URL=http://localhost:4001/v1` + `LLM_API_KEY=<LITELLM_FLEET_BUGFIX_KEY>`,
  models are litellm aliases `fleet-bugfix-{flash,pro,reviewer}` (see
  [`infra/litellm/config.yaml`](../infra/litellm/config.yaml) +
  [`infra/litellm/README.md`](../infra/litellm/README.md)). Spend is budget-capped +
  metered; Langfuse traces (fleet + gateway) land in project **"agents"**.
- **Run:** build then run — `npm run build && node --env-file=.env dist/main.js <cmd>`,
  or `npm run dev -- <cmd>` (cmd ∈ `poll|dispatch|cutpr|review|metrics|ship`).
  `dispatch` is the safe no-mutation smoke test. **Verified working E2E 2026-08-19**
  (200s through the gateway, spend metered, traces landed).
- **Autonomous/nonstop by design — currently DORMANT on purpose (deliberate pause).**
  It's built to run continuously, picking up the bug issues the **triage fleet
  (`signal-fleet/`) files** — triage → bugfix is a pipeline. It is NOT on-demand and
  NOT a work/sleep rhythm. Right now it's **paused** (`fleetd.json` bugfix cycle
  disabled = the `"Track B gate"`): it ran ONE batch, and the operator paused it to
  review those results and decide how to fine-tune before letting it run nonstop.
  **Do not wake the fix-loop** (`poll`/`cutpr`/`review`/`ship` mutate GitHub) while
  it's parked — only read-only ops (`dispatch`, `metrics`) are safe. The metrics
  pusher (`com.homelab.bugfix-metrics`, every 120s) keeps running during dormancy.
- **Gotcha — recreation casualties:** a colima/DB recreate wipes the litellm virtual
  key → every call 401s. Fix = recreate the key ([`infra/litellm/README.md`](../infra/litellm/README.md)
  → *Recreate after a DB wipe*).

## What's here (MVP scope)

- **Flow A — Triage** (`src/flows/triage.ts`): `bug` → structured verdict → labels + recommendation.
- **Flow B — Fix** (`src/flows/fix.ts`): `flow:approved` → worktree → fix → local tests → land on `fixes`.
- **Worker seam** (`src/worker/types.ts`): one interface, three adapters —
  `directAdapter.ts` (**the only one wired**), plus `piAdapter.ts` / `opencodeAdapter.ts`
  which are **Phase-0 stubs that throw** (see Current state above). `direct` is both
  the working path and the bake-off's control baseline.
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
cp .env.example .env   # fill via sops on the mini (HARNESS=direct; litellm routing)
npm run typecheck
npm run dev -- dispatch     # safe no-mutation smoke test (real LLM via the gateway)
# npm run dev -- poll       # the real triage→fix loop (mutates the target repo)
```

## Bake-off protocol

The **north star + full evaluation methodology** lives in **[BAKEOFF.md](BAKEOFF.md)**
— how to think about tool calls, the benchmark-difficulty trap, the eval setup,
scoring dimensions, and how to assess "which harness is better at what." Read
that before wiring the opencode/pi adapters.
