# Token management — lean-ctx

**Date:** 2026-06-12 (updated 2026-07-01)
**Status:** v0.2 — lean-ctx live daily; RTK retired from the Claude Code path
**Reach:** local — runs on the operator's machine; no remote calls

!!! warning "RTK hook retired from Claude Code (2026-07-01)"
    This recipe originally paired lean-ctx with an **RTK** Bash hook. That hook
    was **removed** — it competed with lean-ctx's own Bash rewrite (both rewrote
    the same command; see decision **D-0010**). **lean-ctx now owns Bash
    rewriting as well as Read/MCP compression.** RTK is kept only as a manual
    terminal tool (`rtk git …`, `rtk gain`); nothing in the agent loop invokes
    it. The RTK-hook sections below are retained for historical context and for
    use in other harnesses.

How I keep token spend bounded across many sessions a day without thinking
about it. Two complementary tools, both Mac-installed via Homebrew, both
mostly invisible once configured.

| Tool | What it compresses | How |
|---|---|---|
| **lean-ctx** | File reads, shell command output, MCP tool output, directory listings | MCP server registered in Claude. Auto-selected via tool-preference rules in global CLAUDE.md (`ctx_read` over `Read`, `ctx_shell` over `Bash`, etc.). Caches file content per-project in `.lean-ctx/graph.db` — re-reads cost ~13 tokens instead of full content. |
| **RTK** *(retired from Claude; manual only)* | Bash / shell command output | Rust CLI proxy. **Previously** a Claude Code hook that rewrote commands transparently; that hook is removed (D-0010). Now invoked by hand (`rtk git status`) when you want its per-tool output. |

Reported savings: 60-90% on dev operations (per RTK's `rtk gain`),
60-99% on file reads (per lean-ctx's per-call savings stat).

> **Placeholder legend.**
>
> | Placeholder | What it stands for |
> |---|---|
> | `<project-dir>` | Directory of a project you want lean-ctx active in |

---

## Why this exists

A typical agent session opens 30-100 files, runs dozens of bash commands,
and inspects directory trees repeatedly. Without compression:

- A 500-line file = ~6k tokens, re-read = another ~6k tokens.
- `git status` on a busy repo = ~500 tokens per call.
- `ls -la` on a node_modules dir = thousands of tokens for paths you'll
  ignore.

Across a workday's worth of sessions that's tens of thousands of
unnecessary tokens. The lean-ctx + RTK pair shifts that to a small
fixed-cost cache hit + heavily-filtered output, without changing how the
agent (or operator) actually invokes commands.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│ Claude Code session                                         │
│                                                             │
│   Tool call: Read(file.py)                                  │
│        │                                                    │
│        │  Tool preference rules (global CLAUDE.md)          │
│        ▼                                                    │
│   ctx_read(file.py, mode=auto)  ← lean-ctx MCP              │
│        │                                                    │
│        │  Hit cache?  → ~13 tok response                    │
│        │  Miss?       → compress + cache, return            │
│        ▼                                                    │
│   Compressed file contents                                  │
│                                                             │
│                                                             │
│   Tool call: Bash("git status")                             │
│        │                                                    │
│        │  Pre-tool hook: "rtk hook claude"                  │
│        ▼                                                    │
│   rtk git status  ← Rust binary                             │
│        │                                                    │
│        │  Run real git status, apply 95+ patterns           │
│        ▼                                                    │
│   Compressed output (60-90% smaller)                        │
└─────────────────────────────────────────────────────────────┘
```

Originally the two were orthogonal — lean-ctx covered Read/MCP, RTK covered
Bash. As of 2026-07-01 (**D-0010**) lean-ctx covers Bash too (its `hook rewrite`
wraps commands, and `ctx_shell` compresses directly), so the RTK hook was
dropped to stop two rewriters competing. The `rtk hook claude` step in the
diagram above no longer runs.

---

## Installation

### 1. Install both binaries

```bash
brew install lean-ctx rtk
```

Verify:

```bash
which lean-ctx                 # → /opt/homebrew/bin/lean-ctx
which rtk                      # → /opt/homebrew/bin/rtk
rtk --version                  # → rtk X.Y.Z   (any non-empty line)
```

> ⚠ **Name collision watch.** A different tool called `rtk` exists
> (reachingforthejack/rtk — Rust Type Kit). If `rtk gain` errors with
> "command not found" or unrelated help, you've got the wrong binary.
> Resolve by re-installing from the correct tap or installing directly
> from the source repo.

### 2. Register lean-ctx as a global MCP server

Edit `~/.claude.json` (top-level, not under `projects`):

```json
{
  "mcpServers": {
    "lean-ctx": {
      "command": "/opt/homebrew/bin/lean-ctx",
      "env": {
        "LEAN_CTX_DATA_DIR": "/Users/<operator>/.config/lean-ctx"
      }
    }
  }
}
```

Then in any Claude Code session:

```
/mcp
```

Should list `lean-ctx` as connected. If it isn't, check
`~/.config/lean-ctx/` exists and is writeable.

### 3. Register the RTK hook

!!! note "Superseded (2026-07-01)"
    No longer used in Claude Code — the RTK hook was removed (D-0010); lean-ctx
    owns Bash rewriting. Keep this only for RTK use in a *different* harness.

In `~/.claude/settings.json` add a hook that runs `rtk hook claude`
before bash invocations. Exact JSON shape varies by Claude Code version,
but the entry looks like:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "rtk hook claude"
          }
        ]
      }
    ]
  }
}
```

(See [Claude Code hooks docs](https://docs.claude.com/en/docs/claude-code/hooks)
for the current schema.)

Also add `Bash(rtk grep *)`, `Bash(rtk git *)`, etc. to your `permissions.allow`
list so the RTK-rewritten commands don't trigger an approval prompt every
time.

### 4. Wire global tool preference

In `~/.claude/CLAUDE.md` (the global memory file Claude Code reads on every
session), reference the lean-ctx rules:

```markdown
## lean-ctx — Context Runtime

Always prefer lean-ctx MCP tools over native equivalents:
- `ctx_read` instead of `Read` / `cat` (cached, 10 modes, re-reads ~13 tokens)
- `ctx_shell` instead of `bash` / `Shell` (95+ compression patterns)
- `ctx_search` instead of `Grep` / `rg` (compact results)
- `ctx_tree` instead of `ls` / `find` (compact directory maps)

Full rules: @rules/lean-ctx.md
```

That `@rules/lean-ctx.md` import is the long-form rule file with all 10
read modes documented. Both files live in this repo at
`templates/opencode/rules/lean-ctx.md` (drop-in for opencode) and
analogously at `~/.claude/rules/lean-ctx.md` for Claude Code.

---

## Daily commands

### `rtk gain` — see how much you've saved

```bash
rtk gain                         # summary for the current day
rtk gain --history               # day-by-day breakdown with usage history
```

Output is a small table: commands × tokens-saved × percent-saved. Look at
this once a week to confirm RTK is actually engaged and to spot commands
that *aren't* being compressed (candidates for adding to RTK's pattern
list).

### `rtk discover` — find missed opportunities

```bash
rtk discover
```

Scans your Claude Code session transcripts for bash commands that ran
without RTK compression but matched no pattern. Output is a prioritized
list of "patterns I could be writing for you." Run when you notice your
`rtk gain` percentage is lower than expected.

### `rtk proxy <cmd>` — bypass RTK for debugging

```bash
rtk proxy git log -10            # run raw git log, no compression
```

Use when you need to see the unfiltered output of a command (verifying
that RTK's compression isn't dropping something important).

### lean-ctx mode selection (per-call)

```python
ctx_read("path/to/file.py", mode="auto")        # default — auto-select
ctx_read("path/to/file.py", mode="full")        # files you'll edit
ctx_read("path/to/file.py", mode="map")         # deps + exports only
ctx_read("path/to/file.py", mode="signatures")  # API surface only
ctx_read("path/to/file.py", mode="lines:50-100") # specific range
```

Rule of thumb (from `rules/lean-ctx.md`):
- Editing the file? → `full` first, then `diff` for re-reads.
- Need API surface only? → `map` or `signatures`.
- Large file, context only? → `entropy` or `aggressive`.

---

## Verification

After ~1 day of normal use:

```bash
rtk gain
```

Expect: at least 50% aggregate savings on bash commands you ran a lot
(`git status`, `git diff`, `npm run`, `ls`). If under 30%: the hook may
not be active.

For lean-ctx, look at any `ctx_*` tool output — every call includes a
trailing line like:

```
[2764 tok saved (100%)]
```

That's per-call. The 100% is for cached re-reads. If you never see
"100%" cache hits, lean-ctx isn't caching (data dir issue — see
troubleshooting).

---

## Per-project (optional)

Both tools work zero-config per-project. The only project-side artifact
is lean-ctx's cache:

```
<project-dir>/.lean-ctx/graph.db        # SQLite-ish, typically 50-200K
```

Always add this to `.gitignore`:

```
.lean-ctx/
```

The cache rebuilds automatically when missing. Committing it would
pollute history without benefit (it's machine-local state).

---

## Troubleshooting

### `rtk gain` says "command not found"

Either RTK isn't installed, or you've got the *other* `rtk` (Rust Type
Kit). Verify:

```bash
which rtk
rtk --version | head -1
```

The right RTK prints `rtk X.Y.Z`. The wrong one prints something Rust
Type Kit-ish.

### RTK shows 0% savings

Hook isn't running. Check:
1. `~/.claude/settings.json` has the `PreToolUse Bash` hook with
   `rtk hook claude` as the command.
2. Restart Claude Code (hooks load at session start, not on edit).
3. Run a bash command and check `rtk gain` — it should show at least one
   entry.

### lean-ctx not connecting (`/mcp` lists it as failed)

```bash
ls ~/.config/lean-ctx/                       # should exist, be writeable
/opt/homebrew/bin/lean-ctx --version         # should run cleanly
```

If the binary works standalone but `/mcp` shows it failed: the
`~/.claude.json` entry's `command` path may be wrong (must be absolute),
or the `LEAN_CTX_DATA_DIR` env var points somewhere unwritable.

### Cache misses on every read (no `100%` saved)

Data dir is being recreated each session (permissions, or `LEAN_CTX_DATA_DIR`
points into a tempdir). Verify:

```bash
ls -la ~/.config/lean-ctx/
# Should show a stable .db file growing across sessions.
```

### RTK ate output I needed

Use `rtk proxy <cmd>` for the unfiltered version, or pipe through
`tee /tmp/raw.log` and read the raw log.

### Big project, lean-ctx feels slow on first read

Initial cache population on a 500-file project takes a few seconds. After
that, re-reads are near-instant. To pre-warm:

```bash
# In Claude Code:
ctx_overview              # builds the project graph
ctx_preload <key-paths>   # pre-caches files you'll touch
```

(Or just let the cache fill organically as you work.)

---

## What's NOT covered

- **Prompt caching at the API layer** — Anthropic's prompt-cache feature
  is a separate mechanism (see Pillar 3 / `cloud-ai-workflow.md` once
  filled in). lean-ctx and RTK reduce *what you send*; prompt caching
  reduces *what you pay to re-send*. They compose, but they're different
  layers.
- **Context compaction** — when a session approaches its context window
  limit, Claude Code auto-compacts old turns. That's a Claude Code feature,
  not RTK / lean-ctx.

---

## Future improvements (not done)

- **Cross-project lean-ctx cache** — currently each project has its own
  `.lean-ctx/graph.db`. A shared cache for files outside any single
  project (e.g. dotfiles, system configs) would close a small leak.
- **RTK pattern contributions** — running `rtk discover` regularly across
  several projects builds up a list of missed-compression candidates.
  Contributing those upstream benefits everyone using the same toolchains.
- **`rtk gain` dashboard** — daily savings as a Grafana metric pushed
  alongside the observability stack (Pillar 2). Would let you see token
  spend trends without running the CLI.
- **Auto-CLAUDE.md baseline** — the `rules/lean-ctx.md` import pattern
  should be the default in every new project. Could be added to
  `templates/new-project/AGENTS.md` once a clean version is ready.

---

## References

- Operator's global tool-preference rule:
  [`templates/opencode/rules/lean-ctx.md`](https://github.com/chipi/agentic-ai-homelab/blob/main/templates/opencode/rules/lean-ctx.md)
  in this repo.
- RTK CLAUDE.md reference (the operator's private global instructions
  document RTK's full command set — not in this public repo).
- Both tools' source repos are linked from their `--help` output.

---

## Quick reference card

```
Install:           brew install lean-ctx rtk
Verify lean-ctx:   /mcp                       (in Claude Code)
Verify RTK:        rtk gain                   (after some bash use)
Daily check:       rtk gain --history
Missed patterns:   rtk discover
Bypass RTK:        rtk proxy <cmd>
Force lean-ctx mode: ctx_read(path, mode="full")
Re-read cached:    ctx_read(path, fresh=true) (force disk re-read)
```
