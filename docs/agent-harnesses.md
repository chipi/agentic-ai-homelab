# Pillar 4 — Agent harnesses

The connective tissue: opencode, Claude Code, Cursor configs, MCP server
wiring. The per-operator layer that ties cloud + local + project setup
together.

> **Status: v0.1 partial.** opencode template ships v0.1
> (`templates/opencode/`). Claude Code and Cursor configs are v0.3.

## What's in this pillar

### `templates/opencode/` — opencode global config *(v0.1, real)*

Drop-in for `~/.config/opencode/`:

- `AGENTS.md` — the 34-rule global agent rules (same as repo root
  `AGENTS.md`).
- `rules/lean-ctx.md` — the lean-ctx MCP usage rules.
- `opencode.json.example` — provider config template *(v0.3)*.

See `templates/opencode/README.md` for drop-in instructions.

### `templates/claude-code/` *(v0.3)*

- `settings.json` skeleton — hooks, env vars, permissions.
- `CLAUDE.md` template (thin pointer to AGENTS.md).
- `commands/` directory pattern for custom slash commands.

### `templates/cursor/` *(v0.3, maybe)*

- `.cursorrules` template (thin pointer to AGENTS.md).
- Only if cursor stays in the operator's regular rotation.

### MCP server registry pattern *(v0.3)*

When MCP servers proliferate (lean-ctx, project-specific tools, GitHub
MCP, etc.) you need a discipline:

- Global servers in `~/.config/<harness>/`: lean-ctx, GitHub MCP, etc.
- Project-specific servers in project's `.mcp/` dir.
- Documented in `~/.config/<harness>/MCP_REGISTRY.md` (or per-project
  AGENTS.md).

## How the harnesses divide work

The agent landscape changes fast. Today:

| Harness | Strength | I use it for |
|---|---|---|
| **Claude Code** (CLI) | Most polished agentic harness. Best for "do significant work, verify, ship" sessions. | The bulk of project work. |
| **opencode** (CLI) | Local-model-first; great with vLLM. | Quick interactive sessions where I want zero cloud cost or zero latency. |
| **Cursor** (IDE) | In-editor "edit this file" + chat. | Less now that Claude Code in terminal is better. Occasional. |
| **Chatbox** (mobile / desktop) | OpenAI-compatible client, no deploy. | Phone access to local vLLM or any cloud provider. |

This is a snapshot. Update when the picture changes.

## Open in v0.1

- [ ] `templates/opencode/opencode.json.example` — provider config with
      placeholders for vLLM custom + Claude + OpenAI + multi-model swap.
- [ ] Claude Code `settings.json` skeleton (v0.3).
- [ ] `templates/claude-code/CLAUDE.md` skeleton (v0.3).
- [ ] MCP registry doc (v0.3).
