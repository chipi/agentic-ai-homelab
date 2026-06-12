# agentic-ai-homelab

How I work with agentic AI, end-to-end: cloud LLM APIs, local self-hosted
models, project scaffolding, and the connective tissue between them.

Not a tutorial. Not best practices. **This is what I run.** Patterns here
have been used in real projects; configs here are the actual templates I
deploy (with secrets stripped). Take what's useful, leave the rest.

## Where to start

- **First time here?** Read [Philosophy](philosophy.md) — the underlying
  "how I work" 1-pager.
- **Resuming after a break?** [History](history/README.md) is the
  session-by-session continuity log. The most recent entry is current state.
- **Looking for what's next?** [In progress → Next steps](wip/NEXT_STEPS.md).

## The four pillars

1. [**Project setup**](project-setup.md) — scaffolding a new repo: AGENTS.md
   template, ADR convention, `docs/wip/` pattern, layered Makefile gates,
   PR template.
2. [**Local AI infra**](local-ai-infra.md) — DGX homelab stack: hardened vLLM
   compose, Ollama for catalog + smaller models, observability layer
   (Alloy → Grafana Cloud).
3. [**Cloud AI workflow**](cloud-ai-workflow.md) — patterns for Claude,
   OpenAI, Gemini APIs: prompt caching, batch API, multi-provider routing,
   eval harnesses, cost gates.
4. [**Agent harnesses**](agent-harnesses.md) — connective tissue: global
   AGENTS.md, opencode provider config, Claude Code settings, MCP wiring.

## Status

**v0.1 — initial scaffold.** Most pillars are placeholders. Real content
lands incrementally per [NEXT_STEPS](wip/NEXT_STEPS.md). The session that
produced v0.1 is captured in [0001 — Genesis](history/0001-genesis.md) —
the place to start if you (or a future agent session) need full context.

## Who this is for

Me, primarily. Future-me when I forget why I made a decision. Other
engineers running similar setups who want a working reference instead of a
blog post.

---

Source on GitHub: [chipi/agentic-ai-homelab](https://github.com/chipi/agentic-ai-homelab).
