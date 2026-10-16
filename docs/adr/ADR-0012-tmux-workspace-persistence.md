# ADR-0012 — tmux workspace persistence: durable topology, ephemeral processes

**Status:** Accepted (2026-10-16)
**Date:** 2026-10-16

## Context

The Linux development workstation is operated as one tmux session per project, with
named windows (agent, server, terminal, stream windows) rooted in the project's
checkouts. An SSH disconnect is harmless because the tmux server keeps running; a
reboot, or the death of the tmux server, loses the whole cockpit. The X3's coming
storage migration ends in a reboot, and the repository is meant to rebuild a
workstation on other hardware too, so the answer has to be portable, not an X3 script.

What has to come back: sessions and their names, windows and their names, pane counts,
layouts, working directories, the active window and pane. What must not come back
automatically: whatever was running in the panes. Restarting an agent, a dev server or
a test runner because it was running before the reboot is a decision for the operator,
pane by pane.

Facts the decision rests on (2026-10-16, read from the source at the pinned commit and
tested in disposable servers):

- tmux-resurrect saves exactly that topology to a tab-separated text file, restores
  panes with `-c <saved path>` and windows with `select-layout`, and with
  `@resurrect-processes 'false'` restores no program at all (no `send-keys`). Its
  v4.0.0 release still has a shell-history feature that types into panes; upstream HEAD
  (`cff343c`, 2023) removed it.
- Resurrect always records each pane's full command line (`ps` arguments); there is a
  post-save hook that can rewrite the file.
- Resurrect restores the active pane through `switch-client`, which does nothing
  without an attached client; a saved directory that no longer exists silently becomes
  `$HOME`.
- tmux-continuum's autosave hook is injected into `status-right` only when no other
  `tmux` process is seen at load time; with the X3's real server running, it installed
  nothing in a second server. It also saves only while a client redraws the status
  line.
- Snapshot names have one-second resolution: a second save in the same second makes
  Resurrect delete the file its `last` link points to.

## Decision

1. **tmux-resurrect is the persistence format and mechanism**, pinned to an exact commit
   (`workstation/tmux/plugins.lock`), installed without a plugin manager.
2. **Policy** (`workstation/tmux/persistence.conf`, sourced from the end of the user's
   tmux config by one marked line, never replacing the distribution's config): no
   process restore, no pane contents, snapshots under
   `$HOME/.local/share/tmux/resurrect`, and a post-save hook that blanks saved command
   lines and makes snapshots `0600`.
3. **Periodic saves come from a systemd user timer** (`wb-tmux-save.timer`, every 15
   minutes) running Resurrect's own save script, not from tmux-continuum. Autosave is
   paused in a server that has not been restored or explicitly saved, so a fresh
   server cannot overwrite the snapshot that still has to be restored.
4. **No automatic restore.** Restore is one explicit command, `wb-tmux restore`, run
   after the storage it points into is verified. It refuses when saved directories are
   missing or saved sessions already exist, re-applies the active window/pane with
   explicit targets, and verifies the result.
5. **`wb-tmux` adds validation, not a second format:** `save`/`verify` compare the
   snapshot with the live server and flag panes that cannot be restored faithfully;
   `plan` prints plain tmux commands to rebuild the shells without the plugin.
6. **Portable first.** Nothing knows the project list, the hardware, Omarchy or the X3;
   the X3 storage runbook is where the X3-specific ordering lives (final save and
   verify before quiescing; restore after mount acceptance).

## Consequences

**Positive.** The cockpit survives reboots and server crashes; nothing restarts
behind the operator's back; snapshots hold no command lines and no scrollback; a broken
plugin or snapshot costs only the cockpit, never the boot.

**Negative.** Agent and server state is not resumed: each program is restarted by
hand. The layout is restored at the saved window size and then follows the attaching
client's size. Grouped sessions follow Resurrect's own handling and are not checked by
`wb-tmux verify`. Paths containing whitespace are flagged rather than supported.

**Neutral.** The snapshot is optional private recovery state: reproducible
configuration lives in the public repo; the snapshot (paths and names, no secrets) can
go into the encrypted recovery bundle; running processes are never backed up.

## Alternatives considered

- **tmux-continuum** for autosave and auto-restore: rejected for the reasons above
  (process-count guard, status-line dependency, restore before storage is verified).
- **TPM** (plugin manager): not needed for one pinned plugin; it would add an unpinned
  update path.
- **`@resurrect-processes` with a curated list** (editors only, say): rejected; any
  list makes the restore start programs, and the requirement is that none start.
- **A Workbench-native format** (tmuxp/teamocil-style YAML, or our own): rejected while
  Resurrect already solves the generic problem; a canonical per-project layout can
  later be generated from the Workbench conventions for the total-loss case.
- **tmux auto-restore at server start**: rejected for the X3 migration; it could run
  before `/work` is verified. Can be revisited for machines without that constraint.

## References

- [`workstation/tmux/README.md`](https://github.com/chipi/agentic-ai-homelab/blob/main/workstation/tmux/README.md) — commands, state, recovery, restore modes
- [X3 storage separation runbook](../recipes/x3-storage-separation.md) — gate (F), final save (G), restore and reboot acceptance (Q)
- [ADR-0011](ADR-0011-workstation-storage-subvolumes.md) — the storage layout the restore waits for
