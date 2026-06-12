# opencode — global config drop-in

Copy these files into `~/.config/opencode/` to bootstrap opencode with the
same rules and conventions as this repo.

## Files

- `AGENTS.md` — the 34-rule global agent rules. Same file as the repo
  root `AGENTS.md`. Loaded by opencode on every session, every directory.
- `rules/lean-ctx.md` — lean-ctx MCP usage rules. Loaded the same way.
- `opencode.json.example` — provider config template *(v0.3 — placeholder
  today)*.

## Quick start

```bash
mkdir -p ~/.config/opencode/rules

cp AGENTS.md ~/.config/opencode/AGENTS.md
cp rules/lean-ctx.md ~/.config/opencode/rules/lean-ctx.md

# Once v0.3 ships opencode.json.example:
# cp opencode.json.example ~/.config/opencode/opencode.json
# $EDITOR ~/.config/opencode/opencode.json    # fill in your providers + keys
```

Verify opencode picks them up: start an opencode session in any
directory. The AGENTS.md content should govern behavior immediately.

## Per-project overlays

Per-project `AGENTS.md` files at a repo's root *layer on top* of these
globals. Project rules take precedence when they contradict the globals
(and if they do, that's a signal to reconcile — see global rule "What
overrides this file").

## Lean-ctx MCP setup

`rules/lean-ctx.md` assumes the lean-ctx MCP server is installed. Install
it if you don't have it; the rules file does no good without the tools it
prefers. See lean-ctx upstream docs for installation.

## Open in v0.1

- [ ] `opencode.json.example` — template with placeholders for: vLLM
      custom endpoint (homelab), Anthropic, OpenAI, Google. With
      `apiKey` env var references rather than literals.
- [ ] Notes on the `model` and `small_model` field (use cases for
      identical vs different choices).
