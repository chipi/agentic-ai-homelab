# ADR-0001 — Repo scope: four pillars, personal framing

**Status:** Accepted
**Date:** 2026-06-11
**Context source:** see `docs/history/0001-genesis.md` Phase 6 + 7

## Context

Need: a single place to codify how the operator works with agentic AI —
patterns extracted from across his projects, plus the homelab/local
infrastructure he just hardened — so it doesn't have to be re-derived in
every new project or every new conversation with an agent.

Existing distribution of these patterns:
- Project AGENTS.md files repeat universal rules with drift.
- DGX compose files live outside any git repo (only on `~/docker-compose/`
  on the DGX itself).
- Cloud LLM workflow patterns are mostly in his head + scattered across
  eval harnesses in `podcast_scraper`.
- Agent harness configs (`opencode`, `Claude Code`) are in his global
  dotfiles but not shared between machines.

## Decision

This repo covers FOUR pillars, no more, no less:

1. **Project setup** — scaffolding for new repos. AGENTS.md template,
   ADR/RFC conventions, docs/wip/ pattern, layered Makefile gates, PR
   template.
2. **Local AI infrastructure** — self-hosted LLM stack templates. Hardened
   vLLM compose, observability (Alloy → Grafana Cloud), mobile access
   (LibreChat).
3. **Cloud AI workflow** — patterns for Claude API / OpenAI / Gemini:
   prompt caching, batch API, multi-provider routing, eval harness, cost
   gates.
4. **Agent harnesses** — opencode / Claude Code / Cursor configs, MCP
   server wiring, the connective tissue across (1)-(3).

Framed as **"what I run"**, not "best practices" / "cookbook" / "playbook".
The framing decision (D-0001 in the decision log) is load-bearing — it
sets the expectation level for issues, PRs, and the maintenance cost the
operator is willing to absorb.

## Consequences

**Positive:**
- Clear in-scope / out-of-scope test for new content: "does it serve one
  of the four pillars?". If yes, find which one. If no, don't add it.
- New projects can be bootstrapped from `templates/new-project/` (target
  state — placeholders today).
- Future agent sessions read `AGENTS.md` + `docs/philosophy.md` and have
  most of the operator's preferences without re-derivation.
- The session that produced v0.1 is preserved in `docs/history/` —
  continuity across sessions is structural, not memorial.

**Negative:**
- Maintenance gravity: as projects' workflows evolve, this repo's
  patterns need updating too. Not free.
- Pillar 3 (cloud workflow) is the thinnest today; risk of it never
  catching up to the others. Mitigated by phasing decision below.

**Neutral:**
- One more public repo to keep tidy.

## Alternatives considered

### Alt A: A general "agentic-ai-best-practices" guide

Rejected. Would invite PRs and issues from the wider community for a repo
that's fundamentally personal-config. Maintenance cost too high. Framing
risk (people would expect it to be authoritative).

### Alt B: Three pillars (drop "agent harnesses" as a separate pillar)

Rejected. Agent harness config (opencode, Claude Code) is materially
different from project setup and from infra — it's the per-operator layer
that ties everything together. Folding it into "project setup" or "local
infra" would either bloat those pillars or hide important content.

### Alt C: Just publish the homelab compose files, skip the rest

Rejected. The compose files alone are less than half the value. The
AGENTS.md + project conventions + decision-making patterns are at least
as reusable, and were the easier extraction (no sanitization burden).

## Phasing

To avoid premature canonicalization, content lands in waves:

- **v0.1 (this commit)**: scaffold + AGENTS.md + observability stack
  (the most-templated piece) + history + this ADR. Pillars 2/3 have
  placeholder docs.
- **v0.2** (~2-3 weeks out): Pillar 1 (project setup) — templates dir
  filled, Makefile skeleton, PR template, ADR/RFC templates. Real-use
  feedback from v0.1 baked in.
- **v0.3**: Pillar 3 (cloud AI) — Claude API patterns, multi-provider
  router, eval harness skeleton. Done last because cloud workflow
  patterns benefit from longer real-use observation before being frozen.

If at v0.2 the operator finds the repo isn't getting opened in actual work,
that's a signal to *delete* not to expand. The cost of dead patterns is
higher than their value.

## References

- `docs/philosophy.md` — underlying values driving the four pillars.
- `docs/history/0001-genesis.md` — the session that produced this
  decision.
- `docs/history/0002-decisions.md` D-0001 — the framing decision
  (personal-not-authoritative).
- `docs/wip/NEXT_STEPS.md` — the concrete v0.2/v0.3 task lists.
