---
name: long-job
description: Run any command that may take more than ~10 minutes (a full e2e or translation run, a large build, a data pipeline, a migration) detached from the tool call, with a log ending in EXIT=, a PID file, and a lock so two jobs writing the same files can't run at once. Returns the exact Monitor command to watch it. Never hits the 30-minute background-tool timeout.
when_to_use: Use when about to run something in the background or anything long — "run this in the background", "this will take a while", "kick off the full run", a run_in_background Bash call, or a second long job that might touch the same files as one already running.
---

# long-job

Two failures this prevents (orrery, 2026-10-17):

- A background `Bash` run was **killed at the 30-minute default timeout** mid-run
  (5,100 of 6,953 fields). Nothing was corrupted, but the work had to be resumed.
- Two runs **wrote the same files at once**; each saved the document it had read
  earlier, so edits could be overwritten.

## How

```bash
J=~/.claude/skills/long-job/scripts/long-job.sh
$J start <name> [--lock <key>] [--cwd <dir>] -- <command …>
```

- The job runs under `setsid`, detached from the tool call: the tool returns at
  once and no tool timeout applies. Its log ends with `EXIT=<code>`.
- `--lock <key>`: jobs that write the same thing share a key (e.g. `orrery-i18n`).
  A second job with a held lock is **refused** (exit 2). A lock whose owner died
  is free, so a crash never blocks the next run.
- The output prints the Monitor command (GNU `tail --pid` ends with the job; a
  polling form on macOS) and a one-shot wait command. Arm the Monitor right away
  — watch it live (AGENTS.md rule 0.11), don't sleep.

Then:

```bash
$J status <name>   # running | finished EXIT=<n> | dead (killed or crashed)
$J tail <name> 40
$J stop <name>     # TERMs only this job's process group (pgid = pid), KILL after 10 s
$J list
```

State: `${LONG_JOB_DIR:-~/.local/state/long-job}/<name>.{log,pid,cmd}`, locks in `locks/`.

## Rules

- **Name the lock after what the job writes**, not after the job, when two
  different jobs could touch the same files (`orrery-i18n` for every translation
  run). Different files → different locks → they may run in parallel.
- **Resumable jobs**: write per unit (per file), so a stopped job leaves only whole
  units and can be resumed by building a manifest of what's left.
- **Cleanup**: jobs started from a project directory are tool processes under it,
  so the SessionEnd reaper (`~/.claude/hooks/session-reap.sh`) stops them when the
  session ends. Stop your own jobs with `stop` when done; never `pkill`.
- A Monitor expires after 30 minutes: re-arm it with the same command if the job
  is still running.

## Not covered

- Jobs that must outlive the session (use a systemd user unit or cron instead).
- Remote jobs (on the mini, the VPS): run the script there over ssh; the lock is
  per machine.
