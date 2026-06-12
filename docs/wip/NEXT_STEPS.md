# Next steps

> Promotion target: this doc itself stays as a rolling plan — content gets
> moved out (to pillar docs / ADRs / templates) as it stabilizes. When
> there's nothing left here, the repo has caught up to v1.0.

Status as of v0.2: all four pillars are real. What's left here is ops
items the operator has to run (live infra), follow-up extractions whose
sanitization cost wasn't worth it yet, and parallel maintenance work.

Full continuity of how v0.2 landed: see
[`history/0003-v0.2-arc.md`](../history/0003-v0.2-arc.md).

## Immediately open (still on the operator)

These need DGX / Grafana Cloud / live-infra access — the recipes are
drafted, but they haven't been run for real yet.

- [ ] Fill in `~/docker-compose/grafana-alloy/.env` with Grafana Cloud
      creds → `docker compose up -d` → verify in Grafana Cloud Explore.
      *Recipe: [`recipes/observability-boot.md`](../recipes/observability-boot.md).*
- [ ] Pin the Alloy / DCGM exporter / cAdvisor / ollama-metrics image
      tags after first successful boot (currently `:latest`).
      *Walkthrough in the same recipe.*
- [ ] Fill in `~/bin/gpu-mode-swap.sh` placeholder paths
      (`<coder-compose-dir>`, `<research-compose-dir>`, ports, service
      names) and install per the recipe.
      *Recipe + script template: [`recipes/gpu-mode-swap.md`](../recipes/gpu-mode-swap.md).*
- [ ] Run `provider-bakeoff/` with your real API keys; pick a primary
      cloud provider for the next round of work. *(Sweep cost ~$2-5.)*

## Maintenance items (parallel, not urgent)

- [ ] **Dedup existing project AGENTS.md files** against the new global.
      Open thread #5 from genesis. Targets: `podcast_scraper-FUTURE`,
      `orrery`, `chemigram`, `oceancanvas`. Each has its own AGENTS.md
      that predates the global rules; the project-level files should now
      keep only project-specific content.
- [ ] **Versioning scheme** — semver-style tags (`v0.1`, `v0.2`, …) or
      roll always at HEAD with README "Status" as the truth? Lean toward
      the latter for a personal config repo; revisit if the repo gets
      external consumers.
- [ ] **`templates/claude-code/`** — currently deferred (per
      `agent-harnesses.md`). If a clean minimum-viable
      `~/.claude/settings.json` extraction becomes viable, ship it. Hook
      patterns (RTK + lean-ctx) are already covered by the recipes; the
      missing piece is the harness-specific defaults.

## Deferred (intentional)

These were considered and explicitly NOT extracted, because the honest
reference lives elsewhere:

- **`examples/multi-provider-router/`** — provider abstraction shape.
  The honest reference is `podcast_scraper-FUTURE`'s `cloud_balanced` /
  `cloud_thin` / `cloud_with_dgx_*` provider classes, where the
  abstraction has been beaten on by real work. Genericizing it cleanly
  is more work than the derived value here.
- **Claude Code settings.json template** — 127K of operator-specific
  config (permissions, MCP allowlists, hook commands). Load-bearing
  pieces are documented in
  [`recipes/token-management-lean-ctx-rtk.md`](../recipes/token-management-lean-ctx-rtk.md)
  and [`recipes/chrome-devtools-mcp-agent-loop.md`](../recipes/chrome-devtools-mcp-agent-loop.md).

## What's deliberately NOT in scope

Per ADR-0001 — for context if anyone asks why something isn't here.

- Generic "best practices" content not grounded in operator's actual use.
- LangChain / LangGraph / CrewAI orchestration frameworks. The operator
  prefers thin direct API integrations + MCP. If that changes, write an
  ADR.
- Cloud-deployed agentic services (Lambda, Cloud Run, Functions). This
  is a homelab repo.
- **Self-hosted multi-model chat UIs as deploy targets.** Tried in
  genesis, pulled out (see `history/0002-decisions.md` D-0007). Phone
  access to the local vLLM is via Chatbox (OpenAI-compatible client, no
  deploy) — see `agent-harnesses.md`.
- Mobile-native apps (custom iOS / Android dev).
