# Pillar 4 — Agent harnesses

The connective tissue: opencode, Claude Code, Cursor configs, MCP server
wiring. The per-operator layer that ties cloud + local + project setup
together.

> **Status: v0.2.** opencode template is real (config + AGENTS.md +
> lean-ctx rules). MCP server registry pattern documented inline below.
> Claude Code `settings.json` skeleton deferred — too operator-specific
> to sanitize cleanly; see global `~/.claude/settings.json` for shape.

## Why this pillar exists

Every harness (opencode, Claude Code, Cursor, raw MCP clients) has its
own config format. Without a layer of shared discipline, three things
rot:

1. **Rules duplicate.** The same "never push without approval" rule
   ends up restated four times in four config files, slightly
   differently. Drift kills the value.
2. **MCP servers fragment.** lean-ctx in one harness, chrome-devtools
   in another, no registry of what's installed where. Adding a new
   server becomes a quarter-hour of "where do I put this again?"
3. **Provider keys leak.** Every harness wants `apiKey`. Without a
   discipline, they end up hardcoded in checked-in configs.

The fix is small and boring:

- **One** source-of-truth `AGENTS.md` — global at `~/.config/<harness>/`,
  layered per-project at the repo root. Each harness reads it. No
  duplication.
- **One** MCP registry pattern (below) — global servers in the harness
  config, per-project servers in `.mcp.json` or per-project `mcpServers`.
- **`{env:NAME}` references** for every `apiKey` — keys live in shell rc,
  never in tracked config.

## What's in this pillar

### `templates/opencode/` — opencode global config *(v0.2, real)*

Drop-in for `~/.config/opencode/`. See
[`templates/opencode/README.md`](https://github.com/chipi/agentic-ai-homelab/blob/main/templates/opencode/README.md)
for the install walkthrough.

| File | Purpose |
|---|---|
| `AGENTS.md` | 34-rule global agent rules. Same as repo root `AGENTS.md`. |
| `rules/lean-ctx.md` | lean-ctx MCP usage rules (tool preference, read modes). |
| `opencode.json.example` | Provider + MCP config — local vLLM live, Anthropic/OpenAI/Google add-on snippets in README. |

### `templates/claude-code/` *(deferred)*

The operator's Claude Code config (`~/.claude/`) carries the RTK hook,
the lean-ctx MCP wiring, a per-project permission allowlist, and an
extensively-tuned hooks block. Templating the *shape* is doable; the
sanitization cost is high (127K of `~/.claude/settings.json` with
project-specific permissions). Deferred until a clean minimum-viable
extraction can be authored — until then, the operative pieces live in:

- [`recipes/token-management-lean-ctx-rtk.md`](recipes/token-management-lean-ctx-rtk.md)
  — RTK hook install + lean-ctx MCP setup
- [`recipes/chrome-devtools-mcp-agent-loop.md`](recipes/chrome-devtools-mcp-agent-loop.md)
  — chrome-devtools MCP per-project install

Combined, those cover the load-bearing parts of `~/.claude/settings.json`
and `~/.claude.json` without lifting the whole file.

### `templates/cursor/` *(out of scope)*

Cursor stays in the rotation but isn't a daily driver. No template — if
you want the AGENTS.md rules to bind cursor too, point `.cursorrules` at
the global file with a one-line include. Not worth a template directory.

## How the harnesses divide work

The agent landscape changes fast. Today's split:

| Harness | Strength | I use it for |
|---|---|---|
| **Claude Code** (CLI) | Most polished agentic harness. Cloud-model-strong, multimodal-native, RTK hook integration, deep MCP support. | The bulk of project work — "do significant work, verify, ship" sessions. |
| **opencode** (CLI) | Local-model-first; native vLLM via OpenAI-compatible provider. Lean configuration. | Quick interactive sessions where I want zero cloud cost or zero latency. |
| **Cursor** (IDE) | In-editor "edit this file" + chat. | Less now that Claude Code in terminal is better. Occasional. |
| **Chatbox** (mobile / desktop) | OpenAI-compatible client, no deploy. | Phone access to local vLLM or any cloud provider. |

This is a snapshot. Update when the picture changes.

---

## MCP server registry pattern

The pattern for keeping MCP servers organized as they accumulate.

### Two scopes

| Scope | Where it lives | When to use |
|---|---|---|
| **Global** (every session, every project) | Top-level `mcpServers` in `~/.claude.json` (Claude Code) or `mcp` block in `~/.config/opencode/opencode.json` (opencode) | Tools that are useful in any project: lean-ctx, generic search MCPs, GitHub MCP |
| **Per-project** | `.mcp.json` at project root, or `projects.<path>.mcpServers` block in `~/.claude.json` | Tools tied to one project's surface: chrome-devtools for a web app, a project-specific FastMCP, etc. |

Rule of thumb: **start per-project, promote to global only when you've
used it in three different projects.** Global MCP servers cost startup
time even when unused, so don't pollute the global namespace casually.

### What's globally registered today

In `~/.claude.json` top-level `mcpServers`:

- **lean-ctx** — context compression for every read/shell/grep. See
  [`recipes/token-management-lean-ctx-rtk.md`](recipes/token-management-lean-ctx-rtk.md).

In `~/.config/opencode/opencode.json` `mcp` block:

- **lean-ctx** — same binary, same purpose, opencode-side.

That's it globally. Everything else is per-project.

### What's per-project today

In project-specific `mcpServers` blocks (e.g. `~/.claude.json` under
`projects.<path>`):

- **chrome-devtools** (orrery, podcast_scraper-infra, any repo with a
  browser-visible surface). See
  [`recipes/chrome-devtools-mcp-agent-loop.md`](recipes/chrome-devtools-mcp-agent-loop.md).

### Adding a new MCP server — checklist

1. **Scope it.** Global or per-project? Default per-project.
2. **Register.** Drop the JSON block in the right place.
3. **Restart the harness.** MCP servers load at session start, not on
   config edit.
4. **Verify.** `/mcp` in Claude Code, `mcp` slash in opencode. The new
   server should appear connected.
5. **Document the install.** If non-obvious (npx download, auth, env
   vars), write a recipe in `docs/recipes/`. The two existing MCP
   recipes are the shape.
6. **Add `Bash(<server> *)` to the allowlist** if the harness prompts
   for permission on every tool call. Saves friction.

### When an MCP server doesn't earn its keep

Remove it. MCP servers cost startup time and (worse) cognitive overhead
— every available tool is a tool the agent might wastefully reach for.
Pruning is as load-bearing as adding.

---

## Recipes that operate this pillar

| Recipe | Covers |
|---|---|
| [Token management (lean-ctx + RTK)](recipes/token-management-lean-ctx-rtk.md) | Install, configure, verify the two daily-driver token-compression tools |
| [Chrome DevTools MCP agent loop](recipes/chrome-devtools-mcp-agent-loop.md) | Per-project MCP for UI work; headless vs visible modes; three loop patterns |

---

## Open in v0.2 → v0.3

- [ ] If Claude Code `settings.json` sanitization becomes viable, ship
      `templates/claude-code/settings.json` + a `CLAUDE.md` skeleton that
      thin-points to AGENTS.md.
- [ ] Promote any per-project MCP server to global once it's earned its
      keep across 3+ projects.
