# ADR-0004 — Hardening: inline-by-default; dynamic workflow only for blind-spots

**Status:** Accepted
**Date:** 2026-07-02
**ctx src:** live 5-variant experiment this session; workflow at
`workstation/claude/workflows/harden.js`; per-run cost from the workflow subagent
transcripts.

## ctx

Goal: a repeatable "harden before I close a segment" pass — audit the session
delta for issues, gaps, and drift across code/docs/tests, run the gates, auto-fix
the safe things, and surface what needs a decision. Open question: is a
**model-tiered dynamic multi-agent workflow** worth its cost and complexity versus
the **traditional inline review** — just asking the main agent, which already
holds the session context? We built the workflow (`harden.js` — a deterministic JS
skeleton with all work in `agent()` subagents) and ran five variants on the same
~8-file delta.

## The experiment

| # | variant | cost | notes |
|---|---|---|---|
| v1 | cold workflow, all-opus | **$17.95** | no model tiering |
| v2 | cold, tiered (haiku/sonnet; opus only for high-sev verify) + batched verify | **$1.10** | **16× cheaper than v1, quality identical** |
| v3 | v2 + output-token budget cap | $1.01 | cap works but saves little; it drops the *verify* phase to fit → unverified findings |
| v4 | v2 + main-agent scope+intent brief | $1.23 | brief injection *adds* cost; its value is **precision** (suppresses false positives on intentional choices), not economy |
| v5 | **inline (main agent)** | **~$0.10 marginal** | reuses warm context; catches the obvious ~70%; blind to the author's own subtle bugs |

## Decision

1. **Inline (v5) is the default hardening pass.** Most of the job needs *knowledge
   of the work* (which the main agent holds), not *independence*. Inline reuses
   context the workflow pays full price to rebuild.
2. **Model-tier any workflow you do run** (v2). Tiering is the one unambiguous win.
3. **Reserve the independent tiered workflow for high-stakes changes** where the
   payoff — catching the author's own blind-spot bugs (e.g. the same-session
   `GPU_MODE_SUDO` `:-`→`-` bug a fresh agent caught while the author shipped it) —
   justifies the cost.
4. **Skip the budget cap.** It trims cost by dropping verification — the exact
   thing that makes a workflow's findings trustworthy. If cost matters that much,
   use inline.
5. **Add a brief only for precision** (fewer false positives), never for economy.
6. **Keep `harden.js`** as an experimental tool, not a default, with the caveats
   below.

## Alternatives rejected

- **Workflow-as-default.** Rejected on cost (~10× inline for the routine 80%) and
  reliability (see caveats).
- **No workflow at all.** Rejected — it loses the one real value: independent
  blind-spot catching on critical changes.

## Consequences / how to run

- Invoke via `Workflow({scriptPath, args:{repo, exclude, budgetTokens?, brief?}})`.
  `args` arrives as a JSON **string** — the script parses it. (A latent bug where
  it did not silently disabled `exclude`/`budget`/`brief` for four runs before it
  was caught. Lesson: verify args plumbing, don't trust it.)
- **Orchestrator-level exclude is mandatory.** The in-workflow exclude depends on
  LLM-reported paths and is unreliable; the *caller* must snapshot the do-not-touch
  paths before the run and restore them byte-for-byte after. That held every time
  the in-workflow guard leaked.
- The workflow never commits or pushes — it applies safe fixes to the working tree
  and returns a report. The push stays a gated main-loop action (rule #1).
