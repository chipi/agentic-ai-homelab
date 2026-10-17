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
| `lean-ctx-*`             | Pre/Post    | lean-ctx tool redirect/rewrite shims. |

## Wiring into settings.json

`install.sh` only symlinks these scripts; Claude Code runs them only once
`~/.claude/settings.json` references them. The entries are defined once, in
`workstation/claude/settings.json.example`:

| Event | Matcher | Hook | Timeout |
|---|---|---|---|
| `PreToolUse` | `Bash\|bash` | `$HOME/.claude/hooks/secrets-guard.sh` | default (600 s) |
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
