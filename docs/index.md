# agentic-ai-homelab

How I work with agentic AI, end-to-end: cloud LLM APIs, local self-hosted
models, project scaffolding, and the connective tissue between them.

Not a tutorial. Not best practices. **This is what I run.** Patterns here
have been used in real projects; configs here are the actual templates I
deploy (with secrets stripped). Take what's useful, leave the rest.

## Where to start

- **First time here?** Read [Philosophy](philosophy.md) — the underlying
  "how I work" 1-pager.
- **Looking for a specific operational walkthrough?** Browse the
  [Recipes](recipes/dgx-terminal-dashboard.md) — five concrete
  walkthroughs covering daily ops (terminal dashboard, GPU mode-swap,
  observability boot, token-management tooling, Chrome DevTools MCP
  agent loop).
- **Resuming after a break?** [History](history/README.md) is the
  session-by-session continuity log. The most recent entry is current
  state — `0003-v0.2-arc.md` covers the arc that brought all four
  pillars to real.
- **What's left to do?** [In progress → Next steps](wip/NEXT_STEPS.md).

## The four pillars

1. [**Project setup**](project-setup.md) — `templates/new-project/` is
   bootstrap-ready: AGENTS.md layered on global, layered Makefile gates,
   GH Pages docs site workflow, pre-commit baseline, PR template.
2. [**Local AI infra**](local-ai-infra.md) — hardened vLLM compose
   (`infra/vllm/`), Grafana Alloy observability stack
   (`infra/observability/`), Ollama supporting role, three recipes for
   daily ops.
3. [**Cloud AI workflow**](cloud-ai-workflow.md) — prompt-caching
   discipline, cost gates, three example skeletons
   (`claude-api-with-caching/`, `mcp-tool-template/`, `eval-harness/`).
4. [**Agent harnesses**](agent-harnesses.md) — opencode global config
   drop-in (`templates/opencode/`), MCP server registry pattern, two
   recipes for the daily-driver tooling (token management, Chrome
   DevTools MCP).

## Plus: provider bake-off

A self-contained mini-project at the repo root (`provider-bakeoff/`,
designed to lift into its own GH repo) that compares 10 LLM providers
across 4 countries — 🇺🇸 Claude, GPT, Gemini, Grok · 🇫🇷 Mistral,
Hugging Face · 🇨🇳 DeepSeek, Qwen, Kimi · 🏠 local vLLM — on the same
tasks, with real cost numbers.

```bash
cd provider-bakeoff
cp .env.example .env       # fill in whichever keys you have
make bakeoff               # ~$2-5 for a full sweep
```

## Status

**v0.2 — all four pillars are real.** Templates bootstrap; infra
composes deploy; cloud examples run; agent harness configs drop in.
What's still open: ops items that need live access (Grafana Cloud
creds, image-tag pinning), Claude Code `settings.json` extraction (too
operator-specific to sanitize cleanly), and project AGENTS.md dedup.
See [NEXT_STEPS](wip/NEXT_STEPS.md).

## Who this is for

Me, primarily. Future-me when I forget why I made a decision. Other
engineers running similar setups who want a working reference instead
of a blog post.

---

Source on GitHub: [chipi/agentic-ai-homelab](https://github.com/chipi/agentic-ai-homelab).
