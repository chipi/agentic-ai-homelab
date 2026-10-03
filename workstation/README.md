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
- **Linux** — enables the persistent [SSH agent](#ssh-agent-linux) and sets up
  [Worktrunk streams](#worktrunk-streams-linux). No workbench: one tmux session
  per project; no `~/.tmux.conf`, which would shadow Omarchy's
  `~/.config/tmux/tmux.conf`.

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
| systemd user `ssh-agent.socket` | — (distro unit) | Linux | `systemctl --user enable --now` if not already |
| `~/.bashrc` | — | Linux | appends an `SSH_AUTH_SOCK` block and a Worktrunk shell-integration block, each once, unless already set |
| `~/.config/worktrunk/config.toml` | `config/worktrunk/config.toml` | Linux | symlink |
| `~/.local/bin/wb-stream` | `streams/wb-stream` | Linux | symlink |
| `~/.config/opencode/opencode.json` | `config/opencode/opencode.json.example` | both | **template** — copy + fill |
| `~/.claude/settings.json` | `claude/settings.json.example` | both | **template** — copy + fill |

Both templates call `lean-ctx` by bare name, resolved through the agent's
`PATH` (`/opt/homebrew/bin` on macOS, `~/.local/bin` on Linux), so the same
template works on either platform.

**OpenCode (current limitation, OpenCode 2.0.22).** OpenCode loads its own
global `~/.config/opencode/AGENTS.md` plus project `AGENTS.md` files, but does
not currently load the workstation `~/.config/AGENTS.md`. `~/.config/opencode/AGENTS.md`
is a regular file owned by lean-ctx (shared `rules_injection` mode, its default),
which is the setup that currently delivers lean-ctx's rules to OpenCode; don't
symlink it to `~/.config/AGENTS.md`, or lean-ctx's rule sync writes into this
repo. OpenCode 2.0.22 accepts `instructions[]` in `opencode.json` but doesn't
load those files (checked 2026-10-02); revisit `instructions[]` when our OpenCode
version supports it.

## SSH agent (Linux)

One agent per user, run by systemd, at a stable socket. Keys are never unlocked
automatically.

- **Agent.** `install.sh` enables the distro's `ssh-agent.socket` user unit
  (`systemctl --user enable --now ssh-agent.socket`). systemd listens on
  `$XDG_RUNTIME_DIR/ssh-agent.socket` and starts `ssh-agent.service` on first
  use. The installer never starts an agent itself (`ssh-agent -s`).
- **Shells.** `install.sh` appends one marked block to `~/.bashrc`, after
  Omarchy's interactive-only guard: `export
  SSH_AUTH_SOCK="$XDG_RUNTIME_DIR/ssh-agent.socket"`. Login shells, including
  SSH sessions, get it through `~/.bash_profile`, which sources `~/.bashrc`. If
  that exact line is already there (marked or not), nothing changes. If
  `~/.bashrc` sets `SSH_AUTH_SOCK` to something else, the installer warns and
  leaves it alone.
- **Unlocking.** After each boot the agent is empty, by design. Unlock once:
  `ssh-add ~/.ssh/id_ed25519` (it asks for the passphrase). Every process that
  uses the socket can then use the key until logout or reboot. The installer
  never runs `ssh-add`, stores a passphrase, or touches key files, and doesn't
  enable agent forwarding.
- **tmux.** tmux's default `update-environment` includes `SSH_AUTH_SOCK` and
  Omarchy's `tmux.conf` keeps it, so new windows get the configured socket.
  Shells that were already open before `SSH_AUTH_SOCK` was configured keep
  their old environment: open a new window, or run
  `export SSH_AUTH_SOCK="$XDG_RUNTIME_DIR/ssh-agent.socket"` in them.
- **Check:** `ssh-add -l` lists the unlocked key (or "The agent has no
  identities." before `ssh-add`); `ssh -T git@github.com` authenticates.
- **macOS:** unchanged; the system's launchd agent provides `SSH_AUTH_SOCK`.

## Worktrunk streams (Linux)

Parallel implementation streams use [Worktrunk](https://worktrunk.dev) (`wt`).
Full layout, lifecycle, assumptions and command reference:
[`streams/README.md`](streams/README.md).

- **Layout (Model-B):** `/work/<project>/main` is the permanent primary
  checkout, on any branch; streams live in `/work/<project>/worktrees/<stream>`.
  Other repos keep Worktrunk's default layout.
- **tmux:** one session per project. `wb-stream <name>`, run from the primary
  checkout, creates the stream and opens a window for it in that session.
  Agents use plain `wt` and don't touch tmux.
- **⚠️ Model-B safety rule: explicit base on create, explicit target on
  merge.** Worktrunk defaults both to the repository's default branch:
  - create with `wt switch --create <stream> --base @` (from the primary
    checkout) or `--base <primary-branch>`;
  - integrate with `wt merge <primary-branch>`, never bare `wt merge`.
- **Provisioning:** `sudo pacman -S --needed worktrunk` by hand. `install.sh`
  links the config and `wb-stream`, and adds Worktrunk's bash integration to
  `~/.bashrc` once.
- **Tests:** `bash workstation/install.test.sh` and
  `bash workstation/streams/wb-stream.test.sh` (scratch dirs only).

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

- **TODO — symlinked agent rule files let lean-ctx edit this repo (Mac).** On
  the Mac, `~/.config/opencode/AGENTS.md` is a symlink to `~/.config/AGENTS.md`
  (→ `config/AGENTS.md`), and `~/.claude/CLAUDE.md` links to `claude/CLAUDE.md`.
  In shared mode lean-ctx keeps marked rule blocks in both files, so its updates
  modify tracked source (e.g. `6f8cd66`). Needs a separate migration once agents
  reliably load dedicated instruction files (lean-ctx `rules_injection =
  "dedicated"`).
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
`lsof` (Linux: `pacman -S lsof`; the session hooks need it), `jq`
(`install.sh` uses it to wire the Claude hooks into `settings.json`), `rtk` (optional — manual-only per D-0010), `gh`, `node`, the `ponytail` and `oh-my-openagent`
plugins. Versions and install commands are in
[`setup-new-computer.md`](setup-new-computer.md).
