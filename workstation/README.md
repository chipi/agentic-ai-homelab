# workstation/ — global agent-config, restorable

This directory is the **source of truth** for the operator's machine-global agent
configuration. Home locations symlink *into* here (dotfiles pattern — the same
convention this repo already uses for scripts, where `~/bin/foo` symlinks into
`infra/dgx/bin/foo.sh`). A fresh machine is restored with:

```bash
git clone <this repo>
./workstation/install.sh --dry-run   # ALWAYS preview first — read the BACK/LINK lines
./workstation/install.sh             # then run for real
```

> ⚠️ **`install.sh` runs for real with no confirm prompt** — it backs up each
> live file to `*.bak.<ts>` and replaces it with a symlink into this repo.
> **Always `--dry-run` first** (or `DRY=1 ./workstation/install.sh`) to preview.
> It is lossless + reversible (the `*.bak.<ts>` copies), but preview so you know
> exactly which files move. Backups of skill *directories* land next to the live
> skills — after you've confirmed the symlinks resolve, delete the
> `~/.claude/skills/*.bak.*` dirs so they don't show up as duplicate skills.

Full step-by-step for a clean machine (macOS or Omarchy/Arch Linux):
[`setup-new-computer.md`](setup-new-computer.md). On the Mac laptop, after every
full **restart** (not sleep), validate the machine came back with
[`post-reboot-checklist.md`](post-reboot-checklist.md) (macOS-only).

## Platforms

`install.sh` detects the platform from `uname` (override with
`WS_OS=macos|linux`, e.g. to dry-run the other platform's plan). Everything in
the map below marked **both** is shared agent config and links identically on
each. Only the OS-specific block differs:

- **macOS** — also installs the [workbench](workbench/README.md): one
  persistent tmux session with a window per project, started by a LaunchAgent.
- **Linux** — nothing extra. One tmux session per project; no `~/.tmux.conf`,
  which would shadow Omarchy's `~/.config/tmux/tmux.conf`.

## Home ↔ repo map

| Home location | Tracked here | OS | How install.sh handles it |
|---|---|---|---|
| `~/.config/AGENTS.md` | `config/AGENTS.md` | both | symlink |
| `~/.config/lean-ctx/config.toml` | `config/lean-ctx/config.toml` | both | symlink |
| `~/.config/ponytail/config.json` | `config/ponytail/config.json` | both | symlink |
| `~/.claude/CLAUDE.md` | `claude/CLAUDE.md` | both | symlink |
| `~/.claude/skills/*/` | `claude/skills/*/` | both | symlink per skill (dir) |
| `~/.claude/agents/*.md` | `claude/agents/*.md` | both | symlink per subagent |
| `~/.claude/hooks/*` | `claude/hooks/*` | both | symlink per hook script |
| `~/.claude/workflows/*` | `claude/workflows/*` | both | symlink per workflow |
| `~/bin/wb`, `~/bin/wb-session.sh` | `workbench/wb`, `workbench/wb-session.sh` | macOS | symlink |
| `~/.tmux.conf` | `workbench/tmux.conf` | macOS | symlink |
| `~/Library/LaunchAgents/com.chipi.workbench.plist` | `workbench/com.chipi.workbench.plist` | macOS | symlink + one-off `launchctl bootstrap` |
| `~/.config/opencode/opencode.json` | `config/opencode/opencode.json.example` | both | **template** — copy + fill |
| `~/.claude/settings.json` | `claude/settings.json.example` | both | **template** — copy + fill |

Both templates call `lean-ctx` by bare name, resolved through the agent's
`PATH` (`/opt/homebrew/bin` on macOS, `~/.local/bin` on Linux), so the same
template works on either platform.

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

Installed and on `PATH`: `claude` (Homebrew on macOS, mise on Linux),
`opencode`, `lean-ctx` (`/opt/homebrew/bin` on macOS, `~/.local/bin` on Linux),
`lsof` (Linux: `pacman -S lsof`; the session hooks need it), `rtk` (optional — manual-only per D-0010), `gh`, `node`, the `ponytail` and `oh-my-openagent`
plugins. Versions and install commands are in
[`setup-new-computer.md`](setup-new-computer.md).
