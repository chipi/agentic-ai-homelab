# AGENTS.md — agentic-ai-homelab (repo-scoped)

Repo-scoped rules for any agent working in this codebase. `AGENTS.md` is
a convention multiple harnesses follow — Claude Code picks this up via
[`CLAUDE.md`](CLAUDE.md), Cursor and Codex read it natively, and the
operator's chosen harness (opencode) does too. This file is harness-
agnostic; nothing in this repo depends on which harness you run.

This file captures conventions that apply *repo-wide*. Folder-specific
rules live in scoped `AGENTS.md` files (see the table below) — this root
file points to them and never duplicates them. The operator's broader
cross-repo rules (collab style, safety floor, comm defaults) layer
underneath — when those exist as a separate file (e.g.
`~/.config/<harness>/AGENTS.md`), this file builds on top, never
duplicates or contradicts.

## Repo-wide conventions

- **`.env` belongs in `.gitignore`, never in git.** Always. Reasserted
  here because this repo has many compose stacks and the temptation to
  commit "just the example values" comes up regularly. Compose stacks
  read the repo-root `.env` directly (see [`infra/AGENTS.md`](infra/AGENTS.md)).

## Scoped AGENTS.md in this repo

Folder-specific rules live next to the code they govern. More-specific
folder wins (e.g. `infra/dgx/` over `infra/` over root).

| Path | Scope |
|---|---|
| [`docs/AGENTS.md`](docs/AGENTS.md) | Docs workflow — mkdocs strict gate, doc hygiene, NEXT_STEPS punch list, history arcs |
| [`infra/AGENTS.md`](infra/AGENTS.md) | Infra stacks — run composes in place, symlink operator scripts |
| [`infra/dgx/AGENTS.md`](infra/dgx/AGENTS.md) | DGX-host work, GPU mode coordination |
| [`infra/vllm/AGENTS.md`](infra/vllm/AGENTS.md) | Local vLLM stacks — ports, dummy key, GPU sizing |
| [`provider-bakeoff/AGENTS.md`](provider-bakeoff/AGENTS.md) | provider-bakeoff sub-project |

Templates (not active rules — copy-out artifacts; see pillar 4 for context):
- `templates/new-project/AGENTS.md` — bootstrap for fresh project repos
- `templates/opencode/AGENTS.md` — the operator's personal cross-repo
  default, kept here as a drop-in for `~/.config/opencode/` only because
  that's the harness the operator runs. Not a dependency of this repo.

## What overrides this file

Direct chat instruction > persistent memory > scoped AGENTS.md (e.g.
`infra/dgx/AGENTS.md`) > this file > any harness-global rules the
operator carries cross-repo. More-specific layer wins.

<!-- lean-ctx -->
## lean-ctx

Prefer lean-ctx MCP tools over native equivalents for token savings:
`ctx_read` > Read/cat, `ctx_search` > Grep/rg, `ctx_shell` > bash, `ctx_tree` > ls/find.
Native Edit/Write/Glob stay as-is; use `ctx_edit` only when Edit needs an unavailable Read.
Full rules: LEAN-CTX.md (open on demand — do not auto-load).
<!-- /lean-ctx -->
