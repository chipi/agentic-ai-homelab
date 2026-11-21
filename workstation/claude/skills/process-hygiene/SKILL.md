---
name: process-hygiene
description: Clean up after a killed build, a hung test, an OOMed job or a crashed session without touching anyone else's work — find and stop only your own processes and containers, run the session reaper's dry run, sweep stale `gh run` watch loops and orphaned `tail -f` watchers. Use after any abnormal termination, before re-running a crashed job, when a machine has leftover processes, or when a work block ends with background watchers still running.
---

# process-hygiene

Killed builds, hung tests and OOMed ML jobs leave orphan processes behind (on macOS especially). Clean them
up before re-running, and clean up only what is yours: on a shared workstation other checkouts, projects
and agents run the same `node`, `vite` and `playwright` binaries.

## What is yours

- A PID or process group you captured when you started it.
- A checkout-scoped mechanism: `docker compose` in that checkout, the repo's own cleaner.
- Never `pkill`, `killall` or `pkill -f <pattern>`.
- `pgrep -f <pattern>` also matches your own checking command (its command line contains the pattern).
  Confirm a PID with `ps -o pid,args -p <pid>` before calling it a leftover, or use a pattern that cannot
  match itself (`pgrep -f '[e]vh run'`).
- Docker: compose-project scoped only; never `docker system/volume/image prune`.

Full rules: `workstation/DEVELOPER-SETUP.md`, "Multi-agent safety rules".

## The session reaper

A global `SessionEnd` hook, `~/.claude/hooks/session-reap.sh`, runs when any session ends:

- It reaps that session's tool processes.
- It sweeps runaway `gh run` poll loops (`while true; do gh run …; done` CI watchers that leak when a
  session dies and poll the GitHub API for days).
- It sweeps orphaned `tail -f <file> | grep …` watchers whose session and file are gone.
- It is family-scoped by project-name prefix (on the Linux workstation, `/work/<project>/`): an `orrery`
  session never touches a `podcast` process.

Run it by hand, dry run first:

```bash
SESSION_REAP_DRY_RUN=1 bash ~/.claude/hooks/session-reap.sh <dir>   # what it would stop
bash ~/.claude/hooks/session-reap.sh <dir>                          # stop them
```

In a repo, `bash scripts/cleanup-worktree.sh [--stale-loops] [--dry-run]` is the per-repo cleaner.

## Habits that keep it clean

- Stop a background `tail -f` watcher by PID when you are done with it.
- Never background a `gh run` watch loop without a bound: `for i in $(seq …)`, not `while true`.
- At the end of a work block, check for your own leftovers.

Safety gates, env knobs (`SESSION_REAP_MAX_LOOP_AGE`, `SESSION_REAP_NO_LOOP_SWEEP`), the family rule and
known gotchas: `~/.claude/hooks/README.md`.
