# tmux — workspace persistence (Linux workstation)

**Workspace topology is durable; process execution is ephemeral.** After a reboot, or a
crash of the tmux server, the cockpit comes back: every session with its name, its
windows and their names, the panes with their layouts and working directories, and the
active window and pane. Nothing that was running in a pane is started again: not
agents (Claude, Codex, OpenCode), dev servers, test runners, Compose or editors. Each
restored pane is a plain shell where it was, and the operator chooses what to start.

Decision and alternatives: [ADR-0012](../../docs/adr/ADR-0012-tmux-workspace-persistence.md).
The X3 is the first reference machine; nothing here depends on it, on Omarchy, or on a
list of projects. The snapshot is whatever the running tmux server holds.

## Pieces

| Piece | Where it lives | Installed by `install.sh` as |
|---|---|---|
| [tmux-resurrect](https://github.com/tmux-plugins/tmux-resurrect), pinned in `plugins.lock` | upstream git | a detached checkout in `~/.local/share/tmux/plugins/tmux-resurrect` |
| `persistence.conf`: the policy | this directory | `~/.config/tmux/workstation-persistence.conf` (symlink) |
| one source line | — | a marked block appended to the user's tmux config (`~/.tmux.conf` if it exists, else `~/.config/tmux/tmux.conf`); the distro's config is never replaced |
| `wb-tmux`: save, verify, show, plan, restore | this directory | `~/.local/bin/wb-tmux` (symlink) |
| `systemd/wb-tmux-save.{service,timer}` | this directory | `~/.config/systemd/user/` (symlinks), timer enabled |

The installer never touches a running tmux server. A server picks the policy up when it
starts, or with `tmux source-file ~/.config/tmux/tmux.conf` (on Omarchy that is what
`omarchy-restart-tmux` runs). Omarchy's `omarchy-refresh-tmux` overwrites the user
config and drops the block; re-run `install.sh` afterwards (`wb-tmux status` shows it).

## The policy (`persistence.conf`)

- `@resurrect-processes 'false'`: Resurrect restores no program at all; every pane gets
  the default shell in its saved directory. No process list is configured.
- `@resurrect-capture-pane-contents 'off'`: scrollback is never written to disk.
- `@resurrect-hook-post-save-layout 'wb-tmux scrub'`: Resurrect records each pane's
  full command line (`ps` arguments, which can hold tokens); the hook blanks it right
  after every save and makes the snapshot `0600` in a `0700` directory. The bare
  program name stays, for the "not restarted" list.
- `@resurrect-dir '$HOME/.local/share/tmux/resurrect'`: durable user state.

## Commands

```
wb-tmux status                 plugin pin, policy loaded in the server, timer, latest snapshot
wb-tmux save [--auto]          save with Resurrect, then compare the snapshot with the live server
wb-tmux verify [file]          compare a snapshot (default: the latest) with the live server
wb-tmux show [file]            the snapshot's topology, and the programs that will not be restarted
wb-tmux plan [file]            plain tmux commands that rebuild the shells by hand (no plugin needed)
wb-tmux restore [--allow-missing] [file]
```

- **verify / save** exit `0` when the snapshot matches the live server exactly
  (sessions, window names and indices, pane counts, layout geometry, active window and
  pane, zoom, every cwd), `1` on a mismatch, `3` when it matches but some pane cannot
  be restored faithfully, `2` when there is nothing to compare. Each exit-3 pane has a
  `FLAG` line: cwd on ephemeral storage (`/tmp`, `/var/tmp`, `/run`, `/dev/shm`), cwd
  deleted while the pane sat in it, or a cwd with whitespace or a backslash (Resurrect
  stores paths in a tab-separated file and escapes only the first space).
- **restore** refuses, changing nothing, when a saved working directory is missing
  (for example the filesystem holding it is not mounted yet; `--allow-missing` opens
  such panes in `$HOME` instead), when a saved session already exists in the server,
  or when the snapshot is malformed. With no server running it starts one, restores,
  and removes its bootstrap session. It then re-applies the saved active window, pane
  and zoom with explicit targets (Resurrect does that through `switch-client`, which
  needs an attached client) and verifies the result against the snapshot.
- **save --auto** is the timer's mode. It does nothing without a server, and it stays
  paused in a server that has not been restored or explicitly saved yet, so a fresh
  post-boot server can never replace the snapshot that is still waiting to be restored.
  `wb-tmux save` and a successful `wb-tmux restore` arm it.
- Resurrect's own keys (prefix + `Ctrl-s` save, prefix + `Ctrl-r` restore) still work
  and follow the same policy; `wb-tmux` adds the checks.

## State and where it lives

`~/.local/share/tmux/resurrect/`: `tmux_resurrect_<timestamp>.txt` snapshots and a
`last` symlink. A new file is written only when the topology changed; Resurrect deletes
snapshots older than 30 days but keeps the newest five. It survives SSH disconnects,
tmux server death and reboots, and on the X3 it is on `@home`, untouched by root
rollbacks and by the storage migration. It is not a backup: it lives on the same disk.

Format (tab-separated; `wb-tmux show` reads it for you):

```
pane    <session> <window> <window_active> :<window_flags> <pane> <title> :<cwd> <pane_active> <program> :
window  <session> <window> :<name> <active> :<flags> <layout> <automatic-rename>
state   <client_session> <client_last_session>
```

Paths are stored as pathnames, not inode or subvolume identity: a pane saved in
`/work/orrery/main` restores to `/work/orrery/main` on whatever filesystem is mounted
there (tested by replacing the backing directory under the same path).

## What is where (disaster recovery)

| Class | What | Source of truth |
|---|---|---|
| **Reproducible from this public repo** | the plugin and its pin, the policy, `wb-tmux`, the timer, the installer behaviour, the Workbench conventions (one session per project, named after its directory; `wb-stream` windows) | `workstation/` |
| **Optional private recovery state** | the latest Resurrect snapshot (`~/.local/share/tmux/resurrect/`): session/window names, layouts, working directories. No secrets by construction (no command lines, no pane contents), but it does reveal project paths and names, so it belongs in the encrypted recovery bundle if kept at all | the machine |
| **Ephemeral, never backed up as process state** | running agents, servers, test runners, editors, the shells themselves, the tmux server process | — |

## Restore modes

**A. Normal reboot (same machine, home survives).** Boot, unlock, log in, then
`wb-tmux restore` and `tmux attach -t <session>`. If the machine has storage that must
be mounted first (the X3's `@work`), restore only after that is verified; `restore`
refuses while saved directories are missing.

**B. Total machine loss (fresh Linux machine).** Clone this repo, run
`workstation/install.sh` (it fetches the pinned plugin and installs the policy, the
command and the timer), authenticate the external services, restore the small
encrypted bundle, clone the projects into the same paths (Model-B: `/work/<project>/main`).
Then either copy a snapshot from the bundle into `~/.local/share/tmux/resurrect/`
(and point `last` at it) and run `wb-tmux restore`, or, without one, open the
canonical workspace per project: `tmux new -s <project> -c /work/<project>/main`. A
snapshot never depends on the old machine beyond its paths; panes whose paths do not
exist are refused, not silently moved.

## Recovery

| Problem | What to do |
|---|---|
| no snapshot (`no snapshot: …/last`) | start sessions by hand (`tmux new -s <project> -c <dir>`); then `wb-tmux save` |
| snapshot incomplete or malformed | `wb-tmux restore <older file>` from the same directory, or `wb-tmux plan <file>` and edit |
| a saved cwd no longer exists | create or restore it, or `wb-tmux restore --allow-missing` (those panes open in `$HOME`) |
| `/work` (or another filesystem) not mounted yet | mount and verify it first; `restore` refuses until the paths exist |
| plugin missing or at the wrong commit (`wb-tmux status`) | re-run `workstation/install.sh`; without network, `wb-tmux plan` needs no plugin |
| policy not loaded in the server | `tmux source-file ~/.config/tmux/tmux.conf`; if the block is gone (e.g. after `omarchy-refresh-tmux`), re-run `install.sh` |
| restore exits 1 (only some sessions came back, or something differs) | read the `MISMATCH` lines; the missing parts can be rebuilt from `wb-tmux plan` output, line by line |
| restore refused because sessions already exist | it never merges; either use those sessions, or `tmux kill-session -t <name>` for each one you do not need and restore again |

Booting never depends on any of this; the worst case is rebuilding the cockpit by hand.

## Why not tmux-continuum

Continuum (periodic save + optional auto-restore) was the intended scheduler. Tested on
the X3 in a disposable server (2026-10-16): it injects its save hook into
`status-right` only when it sees no other tmux process at load time (it counts
processes named `tmux`), and with the real server running it silently installed
nothing. Its saves also run only while a client is attached and redraws the status
line, the hook is lost whenever a later config line sets `status-right`, and the
pinned-candidate HEAD has a stray `set -x` and calls `systemctl --user disable
tmux.service` on every load. The systemd timer runs Resurrect's own save script
instead: same snapshot format, no status-line dependency. Automatic restore at server
start is deliberately not used: a restore has to wait until the storage it points into
is verified.

## Tests

- `bash workstation/tmux/wb-tmux.test.sh`: an isolated tmux server (own
  `TMUX_TMPDIR`, `-L` socket, `HOME`, config and snapshot directory) with three
  sessions, five windows, nine panes, a zoomed window, non-default active panes and
  five foreground marker programs. It saves, kills only that server, swaps the backing
  directory under one saved path, restores, and requires identical topology, no
  restarted marker and plain shells; plus the autosave guard, drift and FLAG
  detection, refusals, the `plan` fallback, scrubbing, and the X3 runbook's ordering.
  It reads the real server only to prove it is unchanged.
- `bash workstation/install.test.sh`: policy and pin checks, install idempotence,
  config placement next to Omarchy's file, timer enable, no project names.
