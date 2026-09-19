# ~/.claude/hooks — Claude Code hooks (global, all projects)

These scripts are wired into Claude Code via `~/.claude/settings.json` and run
for **every session in every project**. They are global machine infrastructure,
not part of any repo. This README is the reference; the load-bearing summary that
teaches each agent lives in `~/.config/AGENTS.md` (imported by `~/.claude/CLAUDE.md`,
and read by opencode via its symlink) — a README alone is never auto-loaded, so
that pointer is what makes any of this discoverable.

| Hook | Event | What it does |
|---|---|---|
| `session-reap.sh`        | SessionEnd  | Reaps this session's tool processes + sweeps runaway `gh run` poll loops in the project family (↓ documented in full). |
| `secrets-guard.sh`       | PreToolUse  | Blocks writes/commits that would leak secrets. |
| `block-opus-subagents.mjs` | PreToolUse | Rejects subagent spawns that inherit Opus (cost guard); logs to `opus-subagent-blocks.log`. |
| `lean-ctx-*`             | Pre/Post    | lean-ctx tool redirect/rewrite shims. |

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

### Gotchas fixed here — do NOT reintroduce

- **Worktree `.git` is a FILE, not a dir.** `[ -d "$dir/.git" ]` is false for a
  worktree → the main reap silently no-ops. (Left as-is on purpose per the limitation
  box above; the sweep runs before this gate so orphans are still caught.)
- **`ps etime` zero-pads → octal.** Fields like `08`/`09` break bash arithmetic
  (`value too great for base`). `etime_secs()` prefixes every field with `10#`.

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
`SessionStart` `".*"` matcher in `~/.claude/settings.json`:

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
