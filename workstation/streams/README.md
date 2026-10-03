# streams — parallel work with Worktrunk (Linux workstation)

How the Linux workstation runs parallel implementation streams next to a
project's primary work. [Worktrunk](https://worktrunk.dev) (`wt`) owns the Git
worktree lifecycle; this directory only adds the layout and one thin command
for humans.

| File | Installed to | Purpose |
|---|---|---|
| `wb-stream` | `~/.local/bin/wb-stream` | Open a stream: Worktrunk worktree + a tmux window in the project session. |
| `wb-stream.test.sh` | — | Tests (scratch repos, isolated tmux server; never touches `/work`). |
| `../config/worktrunk/config.toml` | `~/.config/worktrunk/config.toml` | Model-B worktree path template. |

`workstation/install.sh` links both and adds Worktrunk's bash integration to
`~/.bashrc`. The `worktrunk` package itself is a manual step
(`sudo pacman -S --needed worktrunk`; validated with 0.68.0).

## Model-B layout

```
/work/<project>/main                 primary checkout — permanent, on ANY branch
/work/<project>/worktrees/<stream>   parallel streams — hours/days, then merged or dropped
```

- `main` is a directory name, not a branch name: the primary checkout may be on
  any branch. That branch is the **primary branch** (the primary working line).
- The user config sends `wt`'s worktrees to `/work/<project>/worktrees/<branch>`
  only for repos rooted exactly at `/work/<project>/main`. Worktrunk resolves
  `repo_path` to the primary checkout even when run inside a linked worktree,
  so streams never nest. Every other repo keeps Worktrunk's default
  `<repo>.<branch>` sibling layout.
- **tmux:** one session per project, named after the project. Primary work
  stays in its persistent windows. A stream a human opens gets its own window
  in that same session. Never one session per worktree.

## ⚠️ Model-B safety rule: explicit base on create, explicit target on merge

Worktrunk defaults both ends of a stream's life to the repository's **default
branch**. In Model-B the primary branch is often a different branch, so both
defaults are unsafe here:

| Step | Worktrunk default | Model-B rule |
|---|---|---|
| **Create** | `wt switch --create <stream>` branches from the default branch | Always pass a base: `--base @` from the primary checkout, or `--base <primary-branch>` |
| **Merge** | `wt merge` merges into the default branch (and removes the worktree) | Always name the target: `wt merge <primary-branch>` |

```bash
git -C /work/<project>/main branch --show-current            # the primary branch, e.g. map-redesign
wt switch --create <stream> --base map-redesign --no-cd      # create (agents, or by hand)
wt merge map-redesign                                        # integrate, from the stream's worktree
```

`wb-stream` always creates with `--base @` and prints the matching
`wt merge <primary-branch>` line.

## Opening a stream (humans): `wb-stream`

From the primary checkout, in the project's tmux session:

```bash
cd /work/orrery/main
wb-stream map-fix
```

1. Checks it runs in `/work/<project>/main` itself (not a linked worktree), on
   a branch (not a detached HEAD).
2. Checks the request is unambiguous **before creating anything**: valid,
   unused branch name; free `/work/<project>/worktrees/<name>`; tmux session
   `<project>` exists; no window `<name>` in it yet.
3. Runs `wt switch --create <name> --base @ --no-cd --format json`: Worktrunk
   creates branch `<name>` from the primary branch and its worktree. Project
   hooks and approvals behave as usual.
4. Confirms Worktrunk put it at `/work/<project>/worktrees/<name>`, then opens
   tmux window `<name>` in session `<project>`, rooted there. From inside that
   session the new window gets focus; otherwise it opens in the background.

Your primary shell stays in `main` (`--no-cd`): the stream lives in its own
window. A `/` in the name becomes `-` in the directory and window name
(`fix/map` → `worktrees/fix-map`), exactly like Worktrunk's `sanitize`.

It doesn't use `--execute` (moving to a program-plus-arguments model in
Worktrunk 0.68) or Worktrunk hooks. Hooks stay free for the environment,
dependency, runtime, test and cleanup lifecycle.

**If a step fails after Worktrunk ran**, `wb-stream` never rolls back. Hooks may
already have run, and the stream is valid work. Instead it reports what
actually exists (branch, worktree, location) and prints the exact commands to
open the worktree in the project session, or to discard it with
`wt remove <name>`. That command keeps a branch with unmerged work.

## Agents: plain Worktrunk

Autonomous agents use `wt` directly (with the rule above) and never touch
tmux. The same layout applies:

```bash
wt switch --create <stream> --base <primary-branch> --no-cd   # → /work/<project>/worktrees/<stream>
wt list
wt merge <primary-branch>
```

## Assumptions and failure behaviour

- `/work` is the intentional Model-B root, set in both the config template and
  `wb-stream`. `WB_WORK_ROOT` exists only for the tests.
- The project's tmux session is named exactly after the project directory.
- The template's non-Model-B branch copies Worktrunk 0.68's default layout; a
  later upstream default change won't reach it.
- The config is a symlink to this repo: an explicit `wt config update` or
  `wt config create` would rewrite the tracked file. Normal use doesn't.
- Drift fails closed: a template Worktrunk can no longer render makes `wt`
  refuse to create, and a worktree outside the expected path makes `wb-stream`
  stop before opening a window.

## Not covered yet

Out of scope for this slice: per-stream Docker/Compose ports, databases,
`.env` files, dependency seeding or copy-on-write, runtime cleanup, and
project-specific hooks. No Worktrunk LLM commit generation and no
Claude/Codex/OpenCode Worktrunk plugins are configured.
