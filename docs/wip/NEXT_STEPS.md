# Next steps

> Promotion target: this doc itself stays as a rolling plan — content gets
> moved out (to pillar docs / ADRs / templates) as it stabilizes. When
> there's nothing left here, the repo has caught up to v1.0.

Status as of v0.1 scaffold: most pillars are placeholders. The phased
landing plan from ADR-0001 is what drives ordering.

Landed since v0.1 (not yet promoted to a pillar narrative):

- [x] First commit (`b9fb56f v0.1 scaffold`).
- [x] LICENSE chosen + committed (MIT).
- [x] Docs site pipeline: MkDocs Material + Makefile (`docs-*` targets) +
      GH Pages publish workflow. Site at
      <https://chipi.github.io/agentic-ai-homelab/>.
- [x] DGX terminal dashboard recipe templated + moved to `docs/recipes/`.

## Immediately open (from genesis session)

These were surfaced in the session that produced v0.1 but not closed:

- [ ] Fill in `~/docker-compose/grafana-alloy/.env` with Grafana Cloud
      creds → `docker compose up -d` → verify in Grafana Cloud Explore.
      *Recipe drafted: [`recipes/observability-boot.md`](../recipes/observability-boot.md) —
      run-it-and-walk-through.*
- [ ] Pin the Alloy / DCGM exporter / cAdvisor / ollama-metrics image
      tags after first successful boot (currently `:latest` — sufficient
      for v0.1 but generates churn).
- [ ] Write a `gpu-mode-swap` helper script (toggle between
      coder-next-vLLM up vs autoresearch-vLLM up).
      *Recipe + script drafted: [`recipes/gpu-mode-swap.md`](../recipes/gpu-mode-swap.md) —
      compose paths need operator fill-in.*

## v0.2 — Pillar 1 (project setup)

Goal: `cp -r templates/new-project/ ~/Projects/<name>/` actually
bootstraps a working project.

- [ ] `templates/new-project/AGENTS.md` — project-local AGENTS.md template
      that layers on the global (delete-the-repeats pattern; reference
      `[[../../AGENTS.md]]` for universal rules).
- [ ] `templates/new-project/Makefile` — extracted skeleton of the layered
      gate pattern (test-unit / test-integration / ci-fast / ci tiers).
      Target ~100 lines. Source: podcast_scraper's 3586L Makefile, distilled
      to the reusable structural pattern.
- [ ] `templates/new-project/.github/workflows/ci-fast.yml` — minimal CI
      that mirrors `make ci-fast`. Language-neutral or one-per-language.
- [ ] `templates/new-project/.github/PULL_REQUEST_TEMPLATE.md` —
      borrowed from podcast_scraper, sanitized.
- [ ] `templates/new-project/docs/{adr,rfc,wip}/README.md` — convention
      docs copied from this repo (since the pattern is the same).
- [ ] `templates/new-project/.pre-commit-config.yaml` — minimal baseline.
- [ ] `docs/project-setup.md` filled in — narrative walking through what
      each piece is for, when to deviate.

## v0.2 — Pillar 2 (local AI infra) catch-up

Observability is in already (`infra/observability/`). Still missing:

- [ ] `infra/vllm/` — copy the hardened coder-next compose
      template, with all the layers from the session (`--api-key`,
      `--revision` SHA pin, vllm-cache mount, env_file for HF_TOKEN,
      log rotation, healthcheck). Templated for substitution.
- [ ] `infra/vllm/README.md` — model selection, port + GPU mem tuning,
      mode-swap pattern, image-bump sibling-file convention.
- [ ] `docs/local-ai-infra.md` filled in — the operator narrative across
      vLLM + observability + Ollama as a cohesive stack.

## v0.3 — Pillar 3 (cloud AI workflow)

Thinnest pillar; most of this is to-be-authored, not extracted.

- [ ] `examples/claude-api-with-caching/` — Python skeleton showing prompt
      cache hit/miss telemetry, model-version migration pattern.
- [ ] `examples/multi-provider-router/` — generic shape: same interface
      over Claude / OpenAI / Gemini / local vLLM. Pull abstraction shape
      from podcast_scraper's provider classes; strip podcast-domain code.
- [ ] `examples/mcp-tool-template/` — minimal FastMCP server example.
- [ ] `docs/cloud-ai-workflow.md` filled in — narrative: when cloud, when
      local, when both. Cost gates. Prompt caching as a discipline.
- [ ] Eval harness skeleton (`examples/eval-harness/`) — provider-
      agnostic finale-runner-shaped harness pulled from podcast_scraper's
      `finale_runner.py` + genericized.

## v0.3 — Pillar 4 (agent harnesses)

- [ ] `templates/opencode/opencode.json.example` — provider config with
      placeholders for: vLLM custom endpoint, Claude API, OpenAI API,
      multi-model swap. Currently the only opencode file in templates
      is `AGENTS.md` + `rules/lean-ctx.md`.
- [ ] Claude Code `settings.json` skeleton w/ hook patterns (from
      operator's private global) — sanitized.
- [ ] MCP server registry pattern doc.
- [ ] `docs/agent-harnesses.md` filled in.

## v0.x — Maintenance items (parallel)

- [ ] LICENSE chosen + committed (currently TBD per README).
- [ ] Existing project AGENTS.md files (in podcast_scraper / orrery /
      chemigram / oceancanvas) deduplicated against the new global one.
      Open thread #5 from genesis.
- [ ] Decide on a versioning scheme — semver-style tags (v0.1 / v0.2)?
      Or roll always at HEAD with the README's "Status" line being the
      truth? Lean toward the latter for a personal config repo.

## Under evaluation (not committed)

These were stood up in the genesis session but pulled from the active
work list pending hands-on usefulness check. Reinstate by moving back
into the relevant section.

- **LibreChat self-hosted web UI** (was: mobile access, MCP-aware chat,
  RAG-friendly). Stack is already templated in `infra/librechat/` and
  documented in `docs/local-ai-infra.md` — but the operator wants to
  play with it live before committing to maintain the compose / docs /
  ACL hole long-term. If retained → re-add `infra/librechat/` + ACL
  :3080 items above. If dropped → tear out the related sections from
  `local-ai-infra.md` and add a brief "see Chatbox if you want mobile"
  line.

## What's deliberately NOT in scope

Per ADR-0001 — for context if anyone asks why something isn't here.

- Generic "best practices" content not grounded in operator's actual use.
- LangChain / LangGraph / CrewAI orchestration frameworks. The operator
  prefers thin direct API integrations + MCP. If that changes, write an
  ADR.
- Cloud-deployed agentic services (Lambda, Cloud Run, Functions). This
  is a homelab repo.
- Mobile-native apps (custom iOS / Android dev). If mobile access ends
  up wanted post-evaluation, Chatbox (OpenAI-compatible client, no
  deploy) is the lightweight path; LibreChat (currently "under
  evaluation") is the richer alternative.
