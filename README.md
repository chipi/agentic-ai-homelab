# agentic-ai-homelab

How I work with agentic AI, end-to-end: cloud LLM APIs, local self-hosted
models, project scaffolding, and the connective tissue between them.

Not a tutorial. Not best practices. **This is what I run.** Patterns here
have been used in real projects; configs here are the actual templates I
deploy (with secrets stripped). Take what's useful, leave the rest.

## Status

**v0.2 — all four pillars are real.** Templates bootstrap; infra
composes deploy; cloud workflow examples run; agent harness configs
drop in. Plus a top-level `provider-bakeoff/` that compares 10 LLM
providers across 4 countries on the same tasks with real cost numbers.

What's still open: ops items that need live access (Grafana Cloud
creds, image-tag pinning post-boot), Claude Code `settings.json`
extraction, and existing project AGENTS.md dedup. See
[`docs/wip/NEXT_STEPS.md`](docs/wip/NEXT_STEPS.md).

Continuity log: [`docs/history/`](docs/history/) — `0001-genesis.md`
is the founding session, `0003-v0.2-arc.md` is the arc that brought
the four pillars to real.

## What's here

```
.
├── AGENTS.md                 — global agent rules (drop into any project)
├── LICENSE                   — MIT
├── docs/                     — narrative + recipes + history (MkDocs site)
│   ├── philosophy.md         — the underlying "how I work" 1-pager
│   ├── project-setup.md      — pillar 1: scaffolding for new projects
│   ├── local-ai-infra.md     — pillar 2: self-hosted LLM stack (vLLM + Ollama + observability)
│   ├── cloud-ai-workflow.md  — pillar 3: working with Claude / OpenAI / Gemini APIs
│   ├── agent-harnesses.md    — pillar 4: opencode / Claude Code / MCP registry
│   ├── recipes/              — operator-facing recipes (DGX dashboard, GPU mode-swap, ...)
│   ├── adr/                  — architecture decision records for this repo
│   ├── rfc/                  — open proposals not yet decided
│   ├── wip/                  — work-in-progress notes, next-steps plans
│   └── history/              — session-by-session continuity log
├── templates/
│   ├── new-project/          — copy this dir to bootstrap a new repo
│   └── opencode/             — drop into ~/.config/opencode/
├── infra/
│   ├── vllm/                 — hardened vLLM compose template (Qwen3-Coder-Next-FP8)
│   └── observability/        — Grafana Alloy + DCGM + cAdvisor + Ollama metrics
├── examples/                 — small concrete code samples (cloud + local)
│   ├── claude-api-with-caching/  — prompt-cache discipline demo
│   ├── mcp-tool-template/        — FastMCP skeleton with 3 tool shapes
│   └── eval-harness/             — provider-agnostic 4-op harness
└── provider-bakeoff/         — top-level lift-able: 10 providers × 2 tasks
```

## Four pillars

1. **Project setup** — how I scaffold a new repo. AGENTS.md template, ADR
   convention, docs/wip/ pattern, layered Makefile gates (`docs-*` /
   `lint` / `test-*` / `ci-fast` / `ci`), PR template, GH Pages docs site
   workflow, pre-commit baseline.
   → [Pillar 1](docs/project-setup.md) · `templates/new-project/`
2. **Local AI infra** — DGX homelab stack: hardened vLLM compose, Ollama
   for catalog + smaller models, observability layer (Alloy → Grafana
   Cloud). Three recipes (terminal dashboard, GPU mode-swap,
   observability boot) cover daily operation.
   → [Pillar 2](docs/local-ai-infra.md) · `infra/vllm/` + `infra/observability/`
3. **Cloud AI workflow** — patterns for Claude API, OpenAI, Gemini:
   prompt caching as discipline, batch API, multi-provider routing, eval
   harnesses, cost gates.
   → [Pillar 3](docs/cloud-ai-workflow.md) · `examples/claude-api-with-caching/`,
   `examples/mcp-tool-template/`, `examples/eval-harness/`
4. **Agent harnesses** — the connective tissue. Global AGENTS.md,
   opencode provider config, MCP server registry pattern. Two recipes
   (lean-ctx + RTK token management, Chrome DevTools MCP agent loop)
   cover the daily-driver tooling.
   → [Pillar 4](docs/agent-harnesses.md) · `templates/opencode/`

## Plus: `provider-bakeoff/`

A self-contained mini-project (designed to lift into its own GH repo)
that compares **10 LLM providers across 4 countries** — Claude, GPT,
Gemini, Grok (🇺🇸) · Mistral, Hugging Face (🇫🇷) · DeepSeek, Qwen,
Kimi (🇨🇳) · local vLLM (🏠) — on the same tasks, with real cost
numbers, in one command.

```bash
cd provider-bakeoff
cp .env.example .env       # fill in whichever keys you have
make bakeoff               # ~$2-5 for a full sweep
```

## Who this is for

Me, primarily. Future-me when I forget why I made a decision. Other
engineers running similar setups who want a working reference instead of a
blog post.

## How to use

- **Reading**: start with [`docs/philosophy.md`](docs/philosophy.md), then the pillar that maps to
  your need.
- **Bootstrapping a new project**: `cp -r templates/new-project/ ~/Projects/<name>/`
  then sed-substitute the placeholders (`<project-name>`, `<owner>`,
  `<project-description>`).
- **Setting up the homelab stack**: start with [`docs/recipes/observability-boot.md`](docs/recipes/observability-boot.md)
  (lightest deploy, zero ACL change) → then [`infra/vllm/README.md`](infra/vllm/README.md)
  → then the operator tools per [`docs/recipes/dgx-terminal-dashboard.md`](docs/recipes/dgx-terminal-dashboard.md).
- **Comparing LLM providers**: `provider-bakeoff/` (see above).
- **Resuming after a break**: [`docs/history/`](docs/history/) is the
  continuity log. Latest entry has what's current.

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

See [`AGENTS.md`](AGENTS.md) for the global agent rules that govern any
work in this repo. For decisions that shape the repo itself, see
[`docs/adr/`](docs/adr/).

Site: <https://chipi.github.io/agentic-ai-homelab/>.
