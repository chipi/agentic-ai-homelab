# RFC-0002 — Autonomous bug-fix fleet on the homelab (cheap workers, Claude PR-gate)

**Status:** Proposed
**Date:** 2026-07-21
**Runs on:** the `homelab` Mac mini (always-on, tailnet, observability already there).
**Relates to:** the observability platform (ADR-0005) — Langfuse/GlitchTip/Grafana
watch the fleet. Subagent-tiering intuition from ADR-0003.

## Motivation

Separate **core dev** (operator, laptop) from **bug maintenance** (autonomous, on
the mini). Cheap-token harnesses grind through `bug`-labeled GitHub issues and
produce fixes; **Claude reviews the PR** as the quality gate. Goal: a self-hosted,
modular, operator-in-control pipeline that also doubles as a **hands-on harness
experiment** (Pi vs opencode) and a cost study (DeepSeek/Kimi/GLM on real bugs).

## Proposal

### Scope — bug-only
Trigger is the GitHub **`bug` label**. Epics/stories/other issues are invisible.
This is a bug-processing pipeline, nothing else.

### Roles
- **Orchestrator** — *deterministic code* (no LLM). An always-on service on the
  mini that moves issues through states, routes work, enforces gates/loops/budgets,
  runs tests, opens PRs, parses reviews. LLMs are only **leaf calls**.
- **Triager** (cheap LLM) — classifies a bug: area / severity / actionability;
  emits a **structured JSON verdict**; recommends go/no-go.
- **Specialists** (cheap LLM, routed by area: backend / ui / infra / docs) —
  diagnose + fix, and later *address PR-review comments* (same role, re-invoked).
- **Reviewer** (Claude, self-hosted) — reviews the **whole PR** via the GitHub
  Review API; see below.
- **Operator** (you) — approves go/no-go, merges, deploys. Never automated.

### Branch + batch model (operator's call)
- Fixes commit directly onto **one long-lived `fixes` branch** (each commit =
  `fix #N: …`), each gated by **local tests/lint green** before it lands
  (deterministic, no LLM).
- No per-fix PR, no per-fix LLM review — too much ceremony/cost across many runs.
- When the operator says "cut it," the orchestrator opens **one PR `fixes → main`**
  covering many fixes.
- After merge to main + deploy, `fixes` is **re-cut fresh from main**.

### Whole-PR review + the feedback loop (the core mechanism)
On PR open, Claude reviews the **entire PR** and emits **dual output**:
1. **Human-facing:** a real PR review via the **Review API** — inline comments
   anchored to file:line + summary + verdict (`request-changes`/`approve`). What
   *you* read; the App gives the ergonomics (inline, threads, re-review on push).
2. **Machine-facing:** a **structured JSON task list** the orchestrator consumes —
   `[{file, line, severity: blocking|nit, instruction, thread_id}]`. The
   orchestrator never scrapes prose.

Processing the feedback (deterministic):
- For each **blocking** item → a **work item**: **area** ← file path (→ specialist);
  **origin** ← `git blame` on file:line → the `fix #N` commit → the issue's context.
- Dispatch to the matching specialist in a worktree on `fixes` HEAD → it revises,
  gets local tests green, commits, **replies + resolves the review thread**, pushes.
- On `synchronize`, **re-review the whole PR** (v1: whole-PR, simpler + bounded).
- **Bounded: max 3 rounds** worker↔Claude, then `flow:stuck` → operator.
- `approve` → operator merges → deploy → `flow:shipped`.

### State machine = GitHub labels
Entry `bug` (you add it), then a dedicated `flow:` set is the state store — visible
in the issue list, no separate DB:
```
bug → flow:triaging → (area:* , sev:*) → flow:needs-info | flow:approved
    → flow:fixing → flow:fixed → [in batch PR] flow:in-review
    → flow:changes-requested (round n) | flow:stuck | flow:shipped
```

### Reviewer identity — your own GitHub App
Self-hosted reviewer posts via **your own private GitHub App** (not Anthropic's
cloud Action, not a PAT): bot identity, first-class **webhooks** (auto-re-review on
push, @mention), higher rate limits, revocable fine-grained scopes. The reviewer
model stays **pluggable** (Claude now; a panel/other later) — that modularity is
the whole reason for self-hosting. Inline-suggestions/threading are built on the
Review API (our code), which the App makes clean.

### Triggers
GitHub App **webhooks** via **Tailscale Funnel** (one tiny HMAC-verified public
endpoint): `issues.labeled`(==bug), `pull_request`, `pull_request_review`,
`push`/`synchronize`. Polling is an acceptable spike fallback (no inbound).

### Observability (the loop closes)
Every LLM leaf traced in **Langfuse** (model/tokens/cost/latency — so we compare
DeepSeek vs Kimi vs GLM on real bugs). Errors in **GlitchTip**. A **Grafana panel**
counts issues per `flow:` label. Secrets (OpenRouter, Anthropic, GitHub App key)
via **sops/age**.

## The harness question — Pi vs opencode (decided by a bake-off)

Deep-dive (2026-07-21):
- **opencode** — mature platform (~160K★). `serve` HTTP server + `@opencode-ai/sdk`;
  agents/subagents configured via markdown/JSON (per-agent model/prompt/tools/
  permissions); **native structured output** (JSON-schema + StructuredOutput tool +
  retry); 75+ providers incl. OpenRouter; MCP. **Configure a fleet.**
- **Pi** (earendil-works, MIT) — minimal harness; 4 core tools, everything else
  (subagents, MCP, structured output) **composed in TypeScript**; `pi-agent-core`
  is an **embeddable runtime**; JSON/RPC/SDK first-class. **Build a fleet from
  primitives** — lowest impedance for a custom TS orchestrator; max control.

The fork is **configure (opencode) vs build (Pi)**. The critical requirement is
**structured output the orchestrator can parse** — and cheap models (DeepSeek/Kimi)
are weaker at schema adherence. opencode gives structured-output-with-retry free;
Pi you build it (feasible on pi-agent-core, but yours to own). Operator leans Pi
for control/learning. **Decide with evidence, not vibes → the MVP bake-off.**

## MVP — minimal GitHub App + two flows, on BOTH harnesses

Unpolished prototype that *connects everything*; it's the bake-off:

- **Minimal GitHub App** — webhook receiver on the mini (Funnel), issue/PR read,
  label write, PR/branch write. Auth scaffolded (installation token).
- **Flow A — Triage:** `bug` labeled → triager → **structured JSON verdict** →
  orchestrator applies `area:*`/`sev:*` + `flow:` labels + posts a recommendation.
  *Exercises:* App+webhook, worker invocation, **structured output on a cheap
  model**, label state machine.
- **Flow B — Fix:** `flow:approved` → specialist in a **git worktree** → fix +
  **local tests green** → commit to `fixes` → open/update the batch PR.
  *Exercises:* worktree isolation, a cheap model doing real code, the branch model,
  PR creation.
- Implement A+B on **Pi** and on **opencode**, wire both to **Langfuse**, run on
  **~5 real bugs**, and compare: (1) effort to get reliable structured output,
  (2) schema-adherence/quality on a cheap model, (3) how cleanly the orchestrator
  drives it. → pick the harness.
- **Not in the MVP:** the whole-PR review + feedback loop (Phase 1), ergonomics,
  auto-merge, deploy. Prove triage+fix first; the riskiest orchestration (review
  feedback) lands once the substrate is chosen.

## Open questions
1. **Harness** — the MVP bake-off decides.
2. **Target repos** — which repos does the fleet run against first? (this repo /
   podcast / orrery?) — names the App's install scope.
3. **Batch-PR trigger** — operator command vs threshold-notify ("10 fixes waiting").
4. **`fixes` hygiene / conflicts** — serial merges; a conflicting fix → `flow:stuck`
   (cheap models won't resolve integration conflicts reliably).
5. **Re-review** — whole-PR (v1) vs delta-only (cheaper, stateful) — revisit if cost bites.
6. **Deploy mechanism** — per target repo; stays an operator action (rules #1/#4).
7. **Cost caps / concurrency** — per-issue token budget, max parallel worktrees, kill switch.
8. **App permission scope** — minimal set (PRs RW, Contents RW, Issues RW, metadata R).

## Alternatives considered
- **Claude GitHub cloud Action** — rejected: not self-hosted, reviewer not pluggable.
- **Claude as worker too** — rejected: cost; cheap workers + Claude *gate* is the point.
- **Per-fix PR to main** — rejected by operator: ceremony too expensive across many runs.
- **Per-fix LLM review** — rejected by operator: whole-PR review chosen.
- **Fine-grained PAT** (vs App) — rejected: want webhooks/bot-identity/modularity.
- **Reuse the general oh-my-opencode fleet** — rejected: purpose-built fleet for this.
- **DB state store** — rejected: GitHub labels are transparent + zero-infra.
- **LLM orchestrator** — rejected: deterministic control loop, LLMs at leaves only.

## Phased rollout
- **Phase 0 — MVP bake-off** (above): minimal App + Flow A + Flow B on Pi & opencode → pick harness. Evaluation methodology (tool calls, benchmark design, scoring, assessment) is the north-star doc `bugfix-fleet/BAKEOFF.md`.
- **Phase 1 — full pipeline** on the chosen harness: whole-PR review + feedback loop,
  complete `flow:` state machine, batch PR, operator gates, bounded revise loop.
- **Phase 2 — ergonomics + safety:** inline suggestions / thread-resolve / auto-re-review
  on push; Grafana pipeline-state panel; cost caps + kill switch.
- **Phase 3 — expand:** o11y-reactive agents (alerts → diagnose/propose), more repos,
  marketing/email automation (n8n as the glue) when Orrery/podcast need it.

## Discussion
- **2026-07-21 (initial):** Design worked out interactively. Locked: bug-only scope,
  cheap workers + self-hosted Claude PR-gate via operator's own GitHub App, whole-PR
  review with dual (human+structured) output, long-lived `fixes` branch + batch PR,
  `flow:` labels as state, deterministic orchestrator, custom purpose-built fleet.
  Harness (Pi vs opencode) deferred to an MVP bake-off — the structured-output-on-
  cheap-models axis is the deciding factor and is best settled with real data.
