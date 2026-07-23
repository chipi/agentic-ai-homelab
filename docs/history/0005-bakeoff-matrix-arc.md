# 0005 — bake-off matrix arc (upping-levels measured, two-factor model)

**Date:** 2026-07-23 (two sessions, same day)
**Operator:** Marko (chipi)
**Agent:** Claude Opus 4.8 (1M ctx) → Fable 5 mid-arc, via Claude Code
**Outcome:** The RFC-0002 bake-off instrument is built, calibrated, and
hardened; the L0/L1/L2 upping-level matrix is measured on the base config,
yielding the two-factor model — tickets carry *acceptance*, repo module docs
carry *topology* — and the module-README convention shipped to orrery.

> Sibling to [`0004-agent-config-and-skills.md`](0004-agent-config-and-skills.md).
> Cold-start reading order: `docs/wip/bakeoff-handover.md` (the operational
> read-first, rewritten at this arc's close) → BAKEOFF §6.1–6.3 → this doc's
> Open threads.

Operator opened session 1 pointing at RFC-0002 Phase 0 (harness bake-off);
session 2 (this close) picked up from the session-1 handover note.

## What landed

**Session 1** (commits `da1a9f8`…`fc826ad`): eval runner + 3 harness adapters
(claude/opencode/pi), SWE-bench-style protocol (reset → hidden oracle →
description-only fix → delta-grade → Langfuse), 5-bug orrery replay set gated
green on `pi + deepseek-v4-pro`, and the design shift: description quality
dominates model choice; upping-levels L0→L3; active triage as L1
normalizer+gate (BAKEOFF §6.1–6.3, RFC-0002 Active triager).

**Session 2** (commits `d5d2c60`…`9e8fd7f`, all pushed):

- **Isolating experiment** — a 15-line module-map doc flips fly-physics L1
  FAIL→PASS (missing-context, not impossible-ticket). Runner grew a
  `context_files` substrate hook (docs injected as committed problem state).
- **Ticket triples + full matrix** — all 5 bugs authored at L0/L1/L2 and
  measured (n=1/cell): min level 335=L0 · credits/look-angles/mission-arc=L1
  · fly-physics=L2-or-L1+doc. FAILs cost 2–4.5× passing siblings; zero
  regressions anywhere.
- **Doc-flip experiment** — module docs on garbage (L0) tickets: 0/4 verdict
  flips but 3/4 localization flips → the **two-factor model**, measured from
  both directions. Validates the L1-gate design.
- **Process hardening** — `BAKEOFF_MAX_WALL` budget cap (D-0011), scope
  signal in `result.tsv`, kick-back protocol contract (BAKEOFF §6.2).
- **Module-README convention** — guide + validation
  (`templates/module-readme-guide.md`; D-0012) and, in **orrery**: the guide,
  3 example maps (`src/lib/ar/`, `scripts/`, `tests/e2e/`), AGENTS.md/
  CLAUDE.md wiring — branch `docs/module-readmes` @ `4d3ecd1c9c`, Lock-check
  green, full CI pending PR.
- **Ops fixes** — all 3 adapters force `< /dev/null` (headless harness hangs
  on inherited stdin socket — pi sat 11 min at 0 CPU); Langfuse model pricing
  registered for the 4 reachable OpenRouter models.
- **Shelved by operator**: Fable-brain/tiered-executor delegation mode —
  designed, then parked on ADR-0004 cost data; inline remains default
  (memory: `project_brain_executor_delegation_shelved.md`).

## Open threads (resume here)

1. **k=3 repeats** on the decisive cells — everything above is n=1 (except
   335-L0, n=2). Do this before building on the numbers.
2. **opencode column** — same model, same matrix; substrate-OFF for harness
   rows. First real harness-vs-harness comparison; old glm/kimi runs are
   stale (pre-pin).
3. **Active-triager build** — the measured L0→L1 pairs are its eval set;
   kick-back contract already wired in `result.tsv`.
4. **Orrery PR** — open `docs/module-readmes` PR; full CI proves it; merge is
   operator's call.
5. Scenario B, model rows (glm/kimi), podcast_scraper Phase 0 — untouched.
6. Doc-flip caveat to retire eventually: substrates weren't blind-authored.
