# workstation/ — global agent-config, restorable

This directory is the **source of truth** for the operator's machine-global agent
configuration. Home locations symlink *into* here (dotfiles pattern — the same
convention this repo already uses for scripts, where `~/bin/foo` symlinks into
`infra/dgx/bin/foo.sh`). A fresh machine is restored with:

```bash
git clone <this repo> && ./workstation/install.sh
```

Full step-by-step for a clean Mac: [`setup-new-computer.md`](setup-new-computer.md).

## Home ↔ repo map

| Home location | Tracked here | How install.sh handles it |
|---|---|---|
| `~/.config/AGENTS.md` | `config/AGENTS.md` | symlink |
| `~/.config/lean-ctx/config.toml` | `config/lean-ctx/config.toml` | symlink |
| `~/.config/ponytail/config.json` | `config/ponytail/config.json` | symlink |
| `~/.claude/CLAUDE.md` | `claude/CLAUDE.md` | symlink |
| `~/.claude/skills/*/` | `claude/skills/*/` | symlink per skill (dir) |
| `~/.claude/agents/*.md` | `claude/agents/*.md` | symlink per subagent |
| `~/.claude/hooks/*` | `claude/hooks/*` | symlink per hook script |
| `~/.claude/workflows/*` | `claude/workflows/*` | symlink per workflow |
| `~/.config/opencode/opencode.json` | `config/opencode/opencode.json.example` | **template** — copy + fill |
| `~/.claude/settings.json` | `claude/settings.json.example` | **template** — copy + fill |

`~/.config/opencode/AGENTS.md` is already a symlink to `~/.config/AGENTS.md`, so it
follows the canonical rules through the chain automatically — nothing to install.

## Secrets policy — this repo is public

Real credentials are **never** tracked here. Anything secret-bearing is a
sanitized `*.example` template with placeholders; `install.sh` prints where to
copy it and what to fill. Explicitly excluded (live only, never committed):
`~/.config/gcloud/*`, `~/.config/higgsfield/credentials.json`, `gh` auth tokens,
`sops/`, and the raw `~/.claude/settings.json`.

The OpenRouter fleet key lives in the **shell environment**
(`OPENROUTER_API_KEY`), never in `opencode.json` — the checked-in provider block
only points at the local DGX vLLM (whose `apiKey` is a throwaway).

## Known reconciliations / open items

- **`permissions.defaultMode` must be `auto`.** Setting it to `delegate`
  prevents Claude Code from starting on the current CLI build (tried
  2026-07-01, reverted). The template ships `auto` — do not "fix" it.
- **Bash-rewrite hook — lean-ctx owns it** (resolved 2026-07-01). `rtk hook
  claude` was removed from `PreToolUse`; it competed with `lean-ctx hook
  rewrite` (both rewrote the same command to different things). lean-ctx owns
  Bash rewriting; rtk stays available manually (`rtk <cmd>`, `rtk gain`).
- **`templates/opencode/AGENTS.md`** (207 lines) is a stale partial copy of the
  canonical `config/AGENTS.md` (326 lines). It should point at / be regenerated
  from the canonical file rather than drift as a third copy.
- **`permissions.allow`** (600+ entries) is machine-generated via
  `/fewer-permission-prompts` and full of local absolute paths — deliberately
  omitted from the template. It re-accrues on its own; or restore from a private
  backup.

## Prerequisites the config assumes

Installed and on `PATH`: `claude` (Homebrew), `opencode`, `lean-ctx`
(`/opt/homebrew/bin`), `rtk` (optional — manual-only per D-0010), `gh`, `node`, the `ponytail` and `oh-my-openagent`
plugins. Versions and install commands are in
[`setup-new-computer.md`](setup-new-computer.md).
