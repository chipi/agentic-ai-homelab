# ~/.claude/hooks — Claude Code hooks (global, all projects)

These scripts are wired into Claude Code via `~/.claude/settings.json` and run
for **every session in every project**. They are global machine infrastructure,
not part of any repo. This README is the reference; the load-bearing summary that
teaches each agent lives in `~/.config/AGENTS.md` (imported by `~/.claude/CLAUDE.md`;
OpenCode 2.0.22 doesn't load it yet — see `workstation/README.md`) — a README
alone is never auto-loaded, so that pointer is what makes any of this discoverable.

| Hook | Event | What it does |
|---|---|---|
| `session-reap.sh`        | SessionEnd  | Reaps this session's tool processes + sweeps runaway `gh run` poll loops and orphaned `tail -f … \| grep` watchers in the project family (↓ documented in full). |
| `session-orphan-report.sh` | SessionStart | Reports (never kills) long-running CPU-heavy processes in the project family (↓ documented in full). |
| `secrets-guard.sh`       | PreToolUse  | Blocks writes/commits that would leak secrets. |
| `subagent-model-guard.sh` | PreToolUse | No subagent on Opus; fable for the advisor only (operator, 2026-11-19). Denies on `Agent`/`Task`: a fork (it always runs on the main model, Opus), a call that names no `model` (it would run on the fallback: `CLAUDE_CODE_SUBAGENT_MODEL`, else the main model), and a model naming `opus` or `fable` (any case, full ids, `opusplan`) unless `subagent_type` is `advisor`. On `Workflow` it reads the script (inline, `scriptPath`, or a saved workflow by `name`) and denies an `opus`/`fable` model literal or a fork; a model name built at runtime is not seen. `SUBAGENT_MODEL_GUARD=off` passes everything; it is the operator's only, agents never set it unless the operator explicitly says so (AGENTS.md). Fail-open on its own errors. Tests: `bash subagent-model-guard.test.sh` (37). |
| `lean-ctx-*`             | Pre/Post    | lean-ctx tool redirect/rewrite shims. |

## Wiring into settings.json

`install.sh` only symlinks these scripts; Claude Code runs them only once
`~/.claude/settings.json` references them. The entries are defined once, in
`workstation/claude/settings.json.example`:

| Event | Matcher | Hook | Timeout |
|---|---|---|---|
| `PreToolUse` | `Bash\|bash` | `$HOME/.claude/hooks/secrets-guard.sh` | default (600 s) |
| `PreToolUse` | `Agent\|Task\|Workflow` | `$HOME/.claude/hooks/subagent-model-guard.sh` | 5 s |
| `SessionStart` | `.*` | `$HOME/.claude/hooks/session-orphan-report.sh` | 20 s |
| `SessionEnd` | `.*` | `$HOME/.claude/hooks/session-reap.sh` | 30 s |

`SessionEnd` hooks share a 1.5-second budget unless a hook sets a longer
`timeout` (Claude Code raises the budget to match, up to 60 s), so
`session-reap.sh` carries an explicit one.

On a fresh machine, copying the template is enough. When `~/.claude/settings.json`
already exists (for example written by `lean-ctx setup`, with its own hooks and
status line), `workstation/install.sh` merges these entries into it: it adds
only template hooks whose command isn't already present, backs the file up as
`*.bak.<ts>` first, and leaves everything else unchanged (`HOOK` line in its
output; `OK    hooks already wired` once done; nothing written under
`--dry-run`). It needs `jq` on `PATH` (a prerequisite, see
[`setup-new-computer.md`](../../setup-new-computer.md) step 1). A missing `jq`
or an existing `settings.json` that isn't a valid JSON object stops the
installer before it changes anything (exit 1, also under `--dry-run`); a missing
`settings.json` is only a warning. Re-run it if a tool later rewrites
`settings.json` without these entries.

Restart Claude Code afterwards; it reads hooks at session start.

---

## session-reap.sh — SessionEnd cleanup + stale-loop sweep

**Purpose.** Return the machine to its pre-session state when a session ends, and
sweep runaway CI-watch loops that leaked from *dead* sessions. It is BOTH:

- **Automatic** — the `SessionEnd` hook in `settings.json` (`matcher: ".*"`) runs it
  at the end of every session, with `CLAUDE_PROJECT_DIR` as the project dir.
- **Manual** — run it by hand anytime. **Always dry-run first:**
  ```bash
  SESSION_REAP_DRY_RUN=1 bash ~/.claude/hooks/session-reap.sh <project-dir>   # preview, kills nothing
  bash ~/.claude/hooks/session-reap.sh <project-dir>                          # live
  ```
  `<project-dir>` decides the family (see below). Every candidate is logged to
  `~/.claude/hooks/session-reap.log`.

### Two things it reaps

**1. This session's tool processes** (the per-worktree main reap). Kills processes
whose **CWD is under the project dir** AND that are session tools (`python`,
`playwright`, `ffmpeg`, `uvicorn`, `vite`, `mkdocs serve`, …) — plus never editors,
shells, MCP servers, `claude`, or `lean-ctx`. Two ANDs (CWD **and** tool), never one.

> **KNOWN LIMITATION (intentional):** the project-validity gate uses `[ -d .git ]`,
> but a git **worktree's `.git` is a FILE**, so this main reap is a **no-op for
> worktree sessions** and only runs for regular clones. Flipping to `-e` would let
> it kill dev servers (`vite`/`preview`) in worktrees on session end — including a
> persistent one you rely on — so it's left off until a dev-server exclusion exists.
> The **stale-loop sweep below runs regardless** of this gate.

**2. Runaway `gh run` poll loops** (the stale-loop sweep — the reason this file grew).
Agents sometimes background a `while true; do gh run …; sleep; done` CI-watcher and
**leak it when the session dies** before this hook fires. Orphaned, it polls the
GitHub API forever. Found in the wild: 3 such loops surviving **8–14 days**. The
sweep reaps them by a **stack of gates**, never a bare pattern:

- **same project family** as the invoking dir (see below), AND
- command line contains `gh run`, AND
- it's an **unbounded loop** (`while true` / `until `), AND
- **age ≥ `MAX_LOOP_AGE`** (default 2h — a live watch exits in minutes).

A live watch, an MCP server, and any *other project* can never match all four. A
runaway loop's `lean-ctx` wrapper *does* (its command line carries the whole loop
body), so wrapper + shell both die.

**3. Orphaned follow-watchers** (the orphan-watcher sweep, Linux only — it reads
`/proc`). A backgrounded `tail -f <task-output> | grep 'FAIL|error|…'` outlives the
session that started it: the session's scratch file is deleted, the pipeline is
reparented to init, and it waits forever. Found on the X3: one surviving **14 days**
(following a deleted `scratchpad/push.log`). Gates, all of them:

- a `tail` with a follow flag (`-f`, `-F`, inside a short cluster such as `-nf`, or
  `--follow`), AND
- **orphaned**: its parent is pid 1 or a `systemd` manager (the session is gone), AND
- **every file it follows is deleted** (it is watching nothing), AND
- **age ≥ `MAX_WATCH_AGE`** (default 2h), AND
- CWD in the **same project family**.

Its pipeline partners go with it: members of the same process group that are also
orphaned and are not a shell, agent, editor or MCP server. Nothing outside that group
is touched. A watch with a live parent, or on a file that still exists, never matches.

### Model-B layout (`/work/<project>/…`)

On the Linux workstation projects live in `/work/<project>/main` and
`/work/<project>/worktrees/<stream>` — outside `$HOME`, which the original family rule
did not understand: it returned no family, so **both sweeps silently skipped
themselves on the X3** (log line `family=none`). `family_prefix` now maps any
`/work/<project>/…` path to `/work/<project>/`; the trailing slash is the boundary, so
`/work/orrery/` never matches `/work/orrery2`. `WB_WORK_ROOT` overrides `/work`, as for
the `wb-*` tools. `session-orphan-report.sh` uses the identical rule.

### Family scoping (why it never touches another project)

The sweep is scoped to the **project family** derived from the invoking dir, so an
`orrery` session reaps only `orrery`-family loops, a `podcast` session only
`podcast`-family loops — never across projects.

`family_prefix(path)` = `$HOME/<container>/<base>`, where `<base>` is the instance
directory name up to its first `-`:

```
~/.treehouse/orrery-311982/1/orrery        -> ~/.treehouse/orrery
~/.treehouse/orrery-fixes-311982/1/...      -> ~/.treehouse/orrery   (same family)
~/Projects/podcast_scraper-ai-ml-improvements -> ~/Projects/podcast_scraper
```

A loop is in-family iff its CWD is prefixed by that value. Derivation is generic
(any `$HOME/<container>/<instance>/…` layout — not treehouse-specific); if the path
is too shallow to name a family, the sweep is **skipped** (fail-safe).

### Env knobs

| Var | Default | Effect |
|---|---|---|
| `SESSION_REAP_DRY_RUN`       | `0`    | `1` = log + print targets, kill nothing. |
| `SESSION_REAP_MAX_LOOP_AGE`  | `7200` | Stale-loop age floor, seconds. |
| `SESSION_REAP_NO_LOOP_SWEEP` | `0`    | `1` = skip the stale-loop sweep entirely. |
| `SESSION_REAP_MAX_WATCH_AGE` | `7200` | Orphan-watcher age floor, seconds. |
| `SESSION_REAP_NO_WATCH_SWEEP` | `0`   | `1` = skip the orphan-watcher sweep entirely. |

Tests: `bash workstation/claude/hooks/session-reap.test.sh` — scratch work root and
`HOME`, real orphaned pipelines it starts itself: dry-run, age floor, live run, and the
negatives (live parent, file still there, other family, prefix-sharing project).

### Gotchas fixed here — do NOT reintroduce

- **Worktree `.git` is a FILE, not a dir.** `[ -d "$dir/.git" ]` is false for a
  worktree → the main reap silently no-ops. (Left as-is on purpose per the limitation
  box above; the sweep runs before this gate so orphans are still caught.)
- **`ps etime` zero-pads → octal.** Fields like `08`/`09` break bash arithmetic
  (`value too great for base`). `etime_secs()` prefixes every field with `10#`.

---

## Agent temp files off /tmp (Linux): session-tmpdir.sh, CLAUDE_CODE_TMPDIR, tmp-sweep.sh

The workstation's `/tmp` is a 63 G tmpfs with a fixed 1,048,576 inodes shared by every session. On
2026-11-11 it reached 97 %; on 2026-11-19 ~17:50 CET it reached 100 % (with 35 G free) and every
session's commands failed with "No space left on device". The bulk was test runs: ~60,000
`/tmp/tmp*` folders (Python `tempfile`), `/tmp/pytest-of-<user>` (pytest's default basetemp, named
after the Linux user), repo copies and hand-picked folders in session scratchpads. Since
2026-11-19 nothing an agent writes by default lands in `/tmp`:

- **Each session's own `TMPDIR`.** The SessionStart hook `session-tmpdir.sh` makes
  `~/.cache/agent-tmp/<session id>` (mode 700, the home disk, outside any git worktree) and exports
  `TMPDIR` to it through `CLAUDE_ENV_FILE`, so every command the session runs gets it. Python's
  `tempfile`, `mktemp` and pytest's default basetemp follow it. A tool that hardcodes `/tmp` does not.
- **Claude Code's own scratchpads.** `CLAUDE_CODE_TMPDIR=$HOME/.cache/claude-tmp` in the settings
  `env` block (the template; `install.sh` writes the machine's real home, since settings env values
  are not shell-expanded) moves `claude-<uid>/<project>/<id>` there. Sessions started before keep
  `/tmp/claude-<uid>` until they restart.
- **pytest's folder name.** Even under a session `TMPDIR`, pytest names its default folder
  `pytest-of-<user>`. To keep the operator's name out, a test script passes its own
  `--basetemp`, a fresh folder per run (pytest wipes a reused one at start).

**Cleanup**, by `tmp-sweep.sh` (log `~/.claude/hooks/tmp-sweep.log`):

- **At SessionEnd**, `session-reap.sh` reads `session_id` from the hook's stdin JSON and runs
  `tmp-sweep.sh --session <id>`: that session's scratchpad (under `/tmp/claude-<uid>` and under
  `$CLAUDE_CODE_TMPDIR/claude-<uid>`) and its `~/.cache/agent-tmp/<id>` go.
  `SESSION_REAP_NO_TMP_SWEEP=1` keeps them.
- **Daily**, the user timer `claude-tmp-sweep.timer` (`workstation/claude/systemd/`, installed by
  `install.sh` on Linux) runs `tmp-sweep.sh --daily`. It removes anything older than
  `TMP_SWEEP_MAX_AGE_H` (48 h): old `pytest-N` folders (never the 3 newest or `pytest-current`),
  `/tmp/*-tests-*` folders, `/tmp/tmpXXXXXXXX` (Python) and `/tmp/tmp.XXXXXXXXXX` (mktemp)
  leftovers, scratchpads and session `TMPDIR`s of sessions that ended without the hook, and loose
  files directly in either `claude-<uid>` folder.

**Gates, all of them:** owned by this user; no process has its cwd or an open file inside, except
the processes that called the sweep (at SessionEnd the ending Claude still holds its own files); a
session id of uuid shape; Claude Code's own folders (`bash-edit-diff`, `bundled-skills`) never
touched. A live Claude normally holds its scratchpad's `tasks/` open. One that holds none (4 of 18
on 2026-11-11) cannot be matched to a scratchpad, so every scratchpad of its project folder (its cwd
with each non-alphanumeric character as `-`) is kept. `TMP_SWEEP_DRY_RUN=1` lists without removing.

**Proven 2026-11-19** with the live settings: headless sessions' `tempfile.mkdtemp()` landed in
their own `~/.cache/agent-tmp/<id>/`, none in `/tmp`; the scratchpad was created under
`~/.cache/claude-tmp/claude-1000/`; at SessionEnd the log showed `REMOVE (session ended)` for the
scratchpad and `REMOVE (session ended, TMPDIR)` for the session folder.

**Not covered:** opencode (not done; whether it can give each session its own TMPDIR is not checked, so its sessions keep `/tmp`), and any tool
that writes to `/tmp` by hard-coded path.

Tests: `bash workstation/claude/hooks/tmp-sweep.test.sh` (40 checks in a scratch `/tmp` and home,
including an id like `../<project>`, a fake live `claude`, names that only start with `tmp`, and
both scratchpad roots) and `bash workstation/claude/hooks/session-tmpdir.test.sh` (10 checks).

---

## command-ask-guard.sh — ask the operator before a push, an issue, a destructive command or an install (PreToolUse)

Makes the "ask first" rules of the global `AGENTS.md` (section 1) deterministic. A shell command that
pushes, opens a GitHub issue, deletes or prunes destructively, or installs into a shared environment gets
`permissionDecision: "ask"`. In an interactive session Claude Code asks the operator; in a headless run
(`claude -p`) it is refused (`permission_denials`). The patterns and what they don't cover are at the top of
the script.

**Why a hook and not only `permissions.ask`:** `Bash(...)` permission rules match the native Bash tool
only, and the lean-ctx policy routes agents' commands through `mcp__lean-ctx__ctx_shell`. On 2026-11-21 a
headless `git push` went through `ctx_shell` while `Bash(git push:*)` was in `permissions.ask`. So the hook's
matcher names both: `Bash|bash|mcp__lean-ctx__ctx_shell|mcp__lean-ctx__shell|mcp__lean-ctx__ctx_execute`.
For the same reason, `secrets-guard.sh`'s matcher was widened to the same list; it parses
`tool_input.command`, which both tools send. The `permissions.ask` rules stay as a second layer for native
Bash.

**Proven 2026-11-21:**

- `command-ask-guard.test.sh` (first version): 40/40 cases (both tools, compound commands, near misses such as
  `git status`, `rm -f file`, `npm install`, `docker compose down`).
- Live, headless:
  - `git push` through Bash was refused;
  - `git push` through `ctx_shell` was refused with the guard's reason;
  - `git status` ran;
  - the throwaway remote never moved.

**Fixed 2026-11-22: text that only mentions a command no longer asks.** The first version matched its
patterns anywhere in the command's text, so the operator saw constant prompts in every session: the fleet
session's message draft (a heredoc writing a file that quoted `git push origin HEAD:main`) asked, as did
commit messages, echoes, comments, and the inline `rm -rf "$d"` of a command's own `mktemp -d` folder.
The guard now checks what the shell runs:

- It drops heredoc bodies, comments, and quoted strings containing whitespace. Every pattern spans a
  space, so a quoted word without one, such as `"$d"`, is kept.
- When the command hands text to a shell again (`bash -c`, `sh -c`, `ssh`, `eval`, `su`, a heredoc into
  `bash`, `| sh`), the whole command is checked as written. The first version missed
  `bash -c "rm -rf …"`, `eval "git push …"` and `sudo … sh -c '…'`, because the quote right before the
  command hid it.
- `rm -rf` passes when every target is the command's own `mktemp` folder, `/tmp/claude-<uid>/…`
  (`/private/tmp` on macOS), or under `CLAUDE_CODE_TMPDIR`, with no `..`.

The tests now cover 63 cases, 23 of them new, and pass with GNU bash 5 on the X3 and macOS bash 3.2.57
with BSD awk on the mini. All 7 mutants of the fix failed the suite (`replay-proven-fix`'s `mutate.py`):
no re-run detection, any variable taken as a mktemp folder, `..` allowed, heredoc bodies kept, quoted
text kept, comments kept, every `rm -rf` allowed.

**2026-11-23: `bash file.sh` alone is not a re-run.** The first fix treated any `bash` as running text
again, so a `sed` edit whose quoted expression contained `git push`, followed by `bash cases.sh`, asked.
Now a shell counts as re-running text only:

- with `-c` or `-s` (`bash -lc`, `sh -ec` too);
- bare, reading stdin (a heredoc or `| bash`);
- running a file after this same command wrote a heredoc, because that file may be the heredoc.

There are now 68 cases, passing on the X3 and on the mini's bash 3.2. All 5 mutants of the detection
failed the suite.

**2026-11-23, later: two corrections.**

- **The heredoc-then-run rule is dropped (operator).** A test script written by a heredoc and run in the
  same command pushed to a throwaway local repo, and it asked. A script file was never checked when run
  on its own, so this rule only added prompts, not protection.
- **`lean-ctx -c '…'` is unwrapped.** That is lean-ctx's rewrite of a Bash command, including the
  `{ …; } && pwd -P >| <file>` form. The first fix dropped its quoted argument, so it allowed
  `lean-ctx -c 'rm -rf /work/t/x'`, which the first version had caught. Now the argument is checked as
  the command, and a `lean-ctx -c` of any other shape is checked as written.

There are now 77 cases, passing on the X3 and on the mini's bash 3.2. Both mutants of the unwrapping
(none, and no fallback) failed the suite.

**Escape hatch:** `COMMAND_ASK_GUARD=off`. It is the operator's alone; an agent never sets it.

---

## skill-nudge.py — tell the agent when a skill matches (UserPromptSubmit + PreToolUse Bash)

Skills load by description matching, which an agent deep in a task skips (orrery,
2026-10-17: `o11y-review`, `replay-proven-fix` and `secrets-scan` each fitted a step that
was done by hand, and a background run hit the 30-minute timeout that `long-job` avoids).
This hook adds a one-line context note — **never a permission decision** — when the
prompt or a Bash command matches a skill's `triggers.json`:

```json
{ "prompt": ["regex", …], "bash": ["regex", …], "background": true }
```

`background: true` matches any `run_in_background` Bash call that doesn't already go
through the skill's own script. Skills come from `~/.claude/skills/*` and the project's
`.claude/skills/*`. Each skill is nudged at most once per session per event type (state:
`~/.local/state/skill-nudge/<session>.json`). Any error → silent exit 0; a nudge can never
block work. Cost: ~12 ms per call (20 calls in 0.24 s).

To make a skill nudgeable, add `triggers.json` next to its `SKILL.md`; keep the patterns
specific (a nudge that fires on everything gets ignored).

---

## session-orphan-report.sh — SessionStart detector (REPORT ONLY, never kills)

Covers the one gap `session-reap.sh` structurally cannot: it fires on **SessionEnd**, so a job
started inside a session that simply *keeps going* is never reaped — and after a context
compaction the agent holds no record that it launched one.

**Incident 2026-09-19.** An enrichment CLI ran **4d 22h at 198% CPU** on the shared Mac —
**224.9 hours of CPU for zero bytes of output** — across several compactions. Nothing surfaced
it; the operator found it by hand. It had staged its input into `/tmp`, which macOS's reaper
deleted out from under the live process, so it span on data that no longer existed.

Wired to **SessionStart**, which fires on `startup`, `resume` **and `compact`** — precisely when
the agent's context is empty and it would otherwise have no way to know.

### Two gates, not one — age AND cpu-time

Age alone is useless: an idle MCP server sits at **20 days elapsed with 0m of CPU** and is
healthy infra. Reporting that every session is the noise that gets a check ignored — the same
way a crying-wolf alert becomes furniture. CPU-time is what separates *abandoned and eating the
machine* from *long-lived and idle*, and it filters by **behaviour rather than by name**, so a
server this list has never heard of is still correctly ignored.

Output reports `elapsed`, `cputime`, and `sustained=N core(s)` (cpu÷elapsed — `~2.0` means it
has pegged two cores its whole life, which is exactly what the runaway looked like).

### Why report-only

A long run is often legitimate (a real corpus pass, a model sweep), and SessionStart cannot
tell a wanted 30h job from an abandoned one. Surfacing it is enough — the entire failure was
that nobody was looking. It never signals anything.

### Env knobs

| var | default | meaning |
|---|---|---|
| `ORPHAN_REPORT_MIN_AGE` | `3600` (1h) | age floor |
| `ORPHAN_REPORT_MIN_CPU` | `600` (10m) | cpu-time floor — the load-bearing one |
| `ORPHAN_REPORT_OFF` | unset | `1` disables entirely |

Family-scoped exactly like `session-reap.sh` (shared `family_prefix`), so an orrery session
never reports a podcast process. Verified against a live CPU burner: `podcast_scraper-infra`
and its sibling `-FUTURE` both see it, `orrery` does not, and `$HOME` is refused outright.
Silent (exit 0, no output) when clean.

### Wiring

Installed as a symlink by `workstation/install.sh` like every other hook, then added to the
`SessionStart` `".*"` matcher in `~/.claude/settings.json` (see
[Wiring into settings.json](#wiring-into-settingsjson)):

```json
{ "type": "command", "command": "$HOME/.claude/hooks/session-orphan-report.sh", "timeout": 20 }
```

---

## cleanup-worktree.sh (per-repo manual cleaner — cross-ref)

A repo may ship its own `scripts/cleanup-worktree.sh` — the **manual** counterpart,
run when you finish a work block ("leave the machine quiet"). It kills this
worktree's dev/test processes + descendants, and with `--stale-loops` runs the same
family-scoped stale-loop sweep as above (scoped to the worktree's family, 2h floor
via `CLEANUP_MAX_LOOP_AGE`). See that repo's `AGENTS.md` §"Clean up after yourself".
(Orrery ships one; other repos may not — `session-reap.sh` is the global fallback,
runnable by hand anywhere.)

`session-reap.sh` is global (fires everywhere, automatically); `cleanup-worktree.sh`
is repo-local and on-demand. They share the stale-loop sweep logic and the 2h gate.

## 2026-11-23: build folders and remote Claude temp folders

The operator collected three prompts, all an `rm -rf` of something the session had made itself: an eval-harness
session's `rm -rf .build/f3-new` before each rebuild (twice), and this repo's session removing `/tmp/case3` on the
mini over ssh. `rm -rf` is now also allowed on:

- a relative path whose first part is a generated-output folder (`BUILD_DIRS` in the hook: `.build`, `build`,
  `dist`, `target`, the Python, JS and Gradle caches, `node_modules`, coverage output);
- `/tmp/claude-<anything>/<sub>`, so a work folder made on another host (use `/tmp/claude-work/` there) counts as a
  Claude temp area like the local `/tmp/claude-<uid>/`.

It still asks for `..`, a glob, `~`, `.`, `.git`, `.venv`, an absolute project path and any other relative path.
`/tmp/case3` itself still asks: agents use `/tmp/claude-work/` on remote hosts instead. Tests: 92 of 92 on the X3
(bash 5) and the mini (`/bin/bash` 3.2.57, BSD awk).

Later the same day: a folder made with `D=$(ssh host 'mktemp -d')` and removed there with `rm -rf "$D"` (or
`\"$D\"` inside an ssh "..." string) counts as the command's own mktemp folder; the guard now drops backslashes
before checking a target. Tests: 96 of 96 on the X3 and on the mini's bash 3.2.

## 2026-11-23: a feature-branch push needs no go

Operator's decision (option 1). `git push origin <feature-branch>` (also `-u`, `-q`, `--force-with-lease`,
`HEAD:refs/heads/<branch>`, `git -C dir push`) no longer asks. Still asks: a bare `git push` or one without a
branch, main, master, trunk, develop, production, prod, stable, release(/...), gh-pages, HEAD without a
destination, `--force`/`-f`, a `+refspec`, a `:branch` delete, `--all`, `--mirror`, `--tags`, `--delete`, any
other flag, and any push in text another shell re-runs (ssh, eval, `bash -c`, a pipe into sh).
`~/.config/AGENTS.md` section 1 and the `ship` skill say the same. Tests: 116 of 116 on the X3 and the mini's
bash 3.2; three mutants (no re-run check, no default-branch check, `+`/`:` refspecs let through) each fail it.
