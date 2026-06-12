# agentic-ai-homelab

How I work with agentic AI, end-to-end: cloud LLM APIs, local self-hosted
models, project scaffolding, and the connective tissue between them.

Not a tutorial. Not best practices. **This is what I run.** Patterns here
have been used in real projects; configs here are the actual templates I
deploy (with secrets stripped). Take what's useful, leave the rest.

## Status

**v0.1 — initial scaffold.** Most pillars are placeholders. Real content
lands incrementally per `docs/wip/NEXT_STEPS.md`. The session that produced
v0.1 is captured in `docs/history/0001-genesis.md` — that's the place to
start if you (or a future agent session) need full context.

## What's here

```
.
├── AGENTS.md                 — global agent rules (drop into any project)
├── docs/
│   ├── philosophy.md         — the underlying "how I work" 1-pager
│   ├── project-setup.md      — pillar 1: scaffolding for new projects
│   ├── local-ai-infra.md     — pillar 2: self-hosted LLM stack (DGX, vLLM, Ollama)
│   ├── cloud-ai-workflow.md  — pillar 3: working with Claude / OpenAI / Gemini APIs
│   ├── agent-harnesses.md    — pillar 4: opencode / Claude Code / Cursor configs
│   ├── adr/                  — architecture decision records for this repo
│   ├── rfc/                  — open proposals not yet decided
│   ├── wip/                  — work-in-progress notes, next-steps plans
│   └── history/              — session-by-session continuity log
├── templates/
│   ├── new-project/          — copy this dir to bootstrap a new repo
│   └── opencode/             — drop into ~/.config/opencode/
├── infra/
│   ├── vllm/                 — vLLM compose templates (hardened)
│   ├── observability/        — Grafana Alloy + DCGM + cAdvisor + Ollama metrics
│   └── librechat/            — LibreChat slim self-hosted deploy
└── examples/                 — small concrete code samples (cloud + local)
```

## Four pillars

1. **Project setup** — how I scaffold a new repo. AGENTS.md template, ADR
   convention, docs/wip/ pattern, layered Makefile gates, PR template.
2. **Local AI infra** — DGX homelab stack: hardened vLLM compose, observability
   layer (Alloy → Grafana Cloud), mobile access via LibreChat.
3. **Cloud AI workflow** — patterns for Claude API, OpenAI, Gemini: prompt
   caching, batch API, multi-provider routing, eval harnesses, cost gates.
4. **Agent harnesses** — the connective tissue. Global AGENTS.md, opencode
   provider config, Claude Code settings, MCP server wiring.

## Who this is for

Me, primarily. Future-me when I forget why I made a decision. Other engineers
running similar setups who want a working reference instead of a blog post.

## How to use

- **Reading**: start with `docs/philosophy.md`, then the pillar that maps to
  your need.
- **Bootstrapping a new project**: `cp -r templates/new-project/ ~/Projects/<name>/`
  then edit `AGENTS.md` for project specifics.
- **Setting up the homelab stack**: `infra/observability/README.md` is the
  most templated and the easiest to deploy first.
- **Resuming after a break**: `docs/history/` is the continuity log. Latest
  entry has what's current.

## What this is not

- Not a curated "best practices" guide. Patterns rot. What's here works for me
  right now; if it stops working, I update it or delete it.
- Not a generic infrastructure-as-code repo. It assumes a single-operator
  homelab with one DGX-class box and one tailnet.
- Not a learning resource. If you don't already know what vLLM, MCP, or
  Tailscale are, this won't teach you.

## License

MIT — see [LICENSE](LICENSE). Same license I use across my projects.

## Repo conventions

See `AGENTS.md` for the global agent rules that govern any work in this repo.
For decisions that shape the repo itself, see `docs/adr/`.
