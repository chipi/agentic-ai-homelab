# 0001 — Genesis

**Date:** 2026-06-11 → 2026-06-12 (single session, ~one evening)
**Operator:** Marko (chipi)
**Agent:** Claude Opus 4.7 (1M context), via Claude Code
**Outcome:** This repo (`agentic-ai-homelab` v0.1) exists.

> If you're a future Claude session (or future-me) opening this repo cold:
> this doc is the full continuity log of how it came to be. Read it before
> making structural changes — the decisions here were deliberate and most
> are non-obvious from the files alone.

---

## How it started

The session opened with the operator asking to **validate his self-hosted
coding LLM setup**: opencode (laptop) → vLLM (DGX over Tailscale) →
`Qwen/Qwen3-Coder-Next-FP8`. Original framing: "I made it work and it works
fast — can you validate all of this".

What followed was not "is the config syntactically correct" but a session
that progressively widened from validating one compose file to designing a
whole self-hosted agentic-AI stack and finally codifying the patterns into
a public repo.

## The trajectory (in order)

### Phase 1 — Validation
- Confirmed the local opencode config: `~/.config/opencode/opencode.json`
  using `@ai-sdk/openai-compatible` provider pointing at
  `dgx-llm-1.tail6d0ed4.ts.net:8000`.
- SSH'd to DGX, found `~/docker-compose/vllm-Qwen3-Coder-Next/docker-compose.yml`.
  Compose was well-formed (image `nvcr.io/nvidia/vllm:25.11-py3`, tool-call
  parser `qwen3_coder`, `--enable-auto-tool-choice`) but **the container was
  not running** — operator had stopped it because the DGX GPU was busy with
  autoresearch work (which needs the full GB10 budget).
- Concluded: config is right, service is down by design. Operator confirmed
  he didn't want it brought up; he wanted to *review the design* while doing
  other work.

### Phase 2 — Design review (11 findings)
Surfaced 11 review items, tiered HIGH / MEDIUM / LOW. Operator chose to act
on most of them:

| # | Item | Action taken |
|---|---|---|
| 1 | Compose not in git anywhere | Acknowledged, deferred to "personal project" — became the seed of *this* repo. |
| 2 | `container_name: vllm` collision between coder-next and openwebui composes | Renamed → `vllm-coder-next` and `vllm-openwebui`. |
| 3 | Log rotation missing | Added `logging: json-file max-size: 50m max-file: 3` to both. |
| 4 | CUDA-graph cache not mounted | Created `/opt/llm-models/vllm-cache` on DGX, mounted in both composes. |
| 5 | HF_TOKEN not wired | Added `env_file: /home/markodragoljevic/.env` to both. |
| 6 | Image bump 25.11 → 26.05 | Authored sibling `docker-compose.yml.26.05-py3` (one-line image diff). Did NOT swap live. |
| 7 | No `--api-key` on vLLM | Added `--api-key buddy-is-the-king` to both; updated opencode `apiKey`. |
| 8 | Duplicate bf16 model on disk | Deleted `models--Qwen--Qwen3-Coder-Next` (kept FP8). 97 GB freed. |
| 9 | Model revision unpinned | Pinned `--revision da6e2ed27304dd39abadd9c82ef50e8de67bdd4c` (the SHA already on disk = the validated build). |
| 10 | opencode `rules/` only had lean-ctx.md | See Phase 4 — became the trigger to author a global AGENTS.md. |
| 11 | vLLM `/metrics` unused | Became Phase 3 — full observability stack. |

### Phase 2.5 — Port unification
- Original coder-next compose: port 8000 (collided with the DGX `speaches`
  service the operator runs).
- Decision: move to port **9000** for the coder-next vLLM.
- Then operator said "make vllm-openwebui also on 9000" — accepted that the
  two vLLM composes are *mutually exclusive* (GPU contention forces it
  anyway). Same port = one tailnet ACL hole, one URL to remember.

### Phase 3 — Observability
Designed a single unified stack at `~/docker-compose/grafana-alloy/`:
- **Grafana Alloy** (replaces grafana-agent) — scrapes locally, pushes to
  Grafana Cloud via `prometheus.remote_write`.
- **DCGM exporter** — NVIDIA's GPU metrics for GB10.
- **cAdvisor** — per-container CPU/mem/restarts.
- **ollama-metrics** sidecar (`ghcr.io/norskhelsenett/ollama-metrics`) —
  chosen after actually verifying the upstream repo (initial guess was wrong;
  did proper research before committing).

Key design decision: **Level-1 passive Ollama observability**. Both viable
Ollama exporters are transparent proxies (clients route through them).
Operator chose passive-only mode — get model inventory + RAM gauges without
rerouting any client traffic. Doesn't break the autoresearch pipeline's
direct `localhost:11434` calls.

Tailscale FW impact: **zero new inbound ports** (Alloy is outbound-only to
Grafana Cloud over 443).

### Phase 4 — Global AGENTS.md
Operator said "let's author AGENTS.md on global level. look at all my
projects on github, analyze their AGENTS.md files and pull in what is
common and then analyze and implement some other best practices".

Process:
1. Identified active GH repos via `gh repo list`: podcast_scraper, orrery,
   chemigram, oceancanvas, bathys, devwhateverops, url_scraper, app.
2. Of these, 4 had AGENTS.md locally: podcast_scraper (505L), orrery (631L),
   chemigram (405L), oceancanvas (281L).
3. Dispatched an Explore agent to read all four + the 2554-line
   `.ai-coding-guidelines.md` and surface universal/strong/project-locked
   patterns + tone signals + gaps.
4. Layered the agent's findings on top of the operator's existing feedback
   memory rules (`~/.claude/projects/.../memory/MEMORY.md`).
5. Authored `~/.config/opencode/AGENTS.md` — 34 rules in three tiers:
   NON-NEGOTIABLE / STRONG defaults / Operating discipline / Communication /
   Documentation / Safety / Big-bets. Closed with a precedence section.

This same file lives at the repo root as `AGENTS.md` and at
`templates/opencode/AGENTS.md` (for direct drop-in to other operators'
`~/.config/opencode/`).

### Phase 5 — Mobile / agent-from-mobile
Operator wanted to play with the model from his phone. Surveyed options:

- **Chatbox** (iOS/Android) for instant gratification — OpenAI-compatible
  client, just paste the tailnet URL.
- **Open WebUI** (already deployed) for richer chat with persistence.
- **LibreChat** — the agentic option (MCP support, RAG, multi-provider in
  one UI). Operator picked this.

Deployed LibreChat as a slim 3-container compose at
`~/docker-compose/librechat/`: `api + mongodb + meilisearch`. Skipped
nginx (tailnet encrypts transport) and RAG containers (deferred).
Pre-wired the vLLM coder-next endpoint via `librechat.yaml`.

Mobile path: tailnet → `:3080` → register first user → chat. Tailscale
ACL on `3080` is the only new firewall hole.

### Phase 6 — Repo creation
Operator: "I am thinking of setting new public GH repo for coding best
practices and DGX local coding, my generic things from all projects I could
extrapolate there".

Trade-off discussion: framed as personal `dotfiles`-style not "best
practices" to avoid maintenance expectations.

Name negotiated: `agentic-ai-homelab` (the exact phrase "agentic ai" for
searchability, "homelab" for honest self-hosted scope).

Then scope widened: "I want to cover both how I work with cloud LLM APIs
and local AIs, but also how I setup projects etc". → **four-pillar
structure** (project setup, local AI infra, cloud AI workflow, agent
harnesses).

### Phase 7 — Scaffold (this commit)
This document is one of the files in that scaffold. The rest:

- `README.md` — overview, status, philosophy summary
- `AGENTS.md` — the global one, ported
- `docs/philosophy.md` — the underlying "how I work" essay
- `docs/{project-setup,local-ai-infra,cloud-ai-workflow,agent-harnesses}.md`
  — pillar placeholders with TODO sections
- `docs/adr/ADR-0001-repo-scope.md` — first ADR, scope decision formalized
- `docs/history/0002-decisions.md` — decision log table
- `docs/wip/NEXT_STEPS.md` — phased v0.2 → v0.3 plan
- `infra/observability/*` — real templated config from session work (the
  most-tested artifact)
- `templates/opencode/*` — global AGENTS.md + lean-ctx rule + opencode.json
  example
- Placeholders in `templates/new-project/`, `infra/vllm/`,
  `infra/librechat/`, `examples/`

## What is *not* in this scaffold (deliberately)

- **Live secrets.** All API keys, tailnet hostnames, operator user paths
  templated to placeholders.
- **The full Makefile.** podcast_scraper's Makefile is 3586 lines; the
  reusable structural pattern is ~100 lines and lives in the project-setup
  pillar (v0.2 work).
- **Cloud AI patterns.** Pillar 3 is the thinnest — explicitly deferred to
  v0.2 because cloud-LLM workflow patterns mature with use, and there's no
  point freezing them now.
- **A LICENSE.** Operator hasn't picked one. Repo is treat-as-private until
  added.

## Open threads (for next session)

These were surfaced this session but not closed:

1. **First commit** — directory is scaffolded but no git history yet. `git
   init` was run; first commit shape is operator's call.
2. **Observability stack going live** — Grafana Cloud creds need to be
   filled into `.env`, then `docker compose up -d` on DGX. Verified working
   only at the config layer.
3. **LibreChat mobile test** — stack is up; FW ACL on 3080 not yet opened;
   first mobile login not yet done.
4. **GPU mode-swap helper script** — operator suggested earlier ("`code`
   vs `research` mode toggle"). Not yet written.
5. **opencode rules → projects/AGENTS.md** — the existing project AGENTS.md
   files were *analyzed*, but they haven't been updated to layer cleanly
   on top of the new global one. Eventually they should be deduplicated.
6. **Pillar 1 (project setup)** — most concrete v0.2 work; templates dir
   is just placeholders today.

## How to resume

If you're picking this up fresh:
1. Read `AGENTS.md` (the global rules).
2. Read `docs/philosophy.md` (the underlying values).
3. Read this doc through "Open threads".
4. Pick from `docs/wip/NEXT_STEPS.md` — that file has the prioritized work.

The operator's preference (per global AGENTS.md): **do exactly what was
asked, nothing more**. If unsure whether a "while-I'm-here" cleanup is in
scope, ask.

---

*This document is append-only history. Future sessions should add
`0002-...md`, `0003-...md` rather than editing this file. The decisions
log (`0002-decisions.md`) IS append-only as well.*
