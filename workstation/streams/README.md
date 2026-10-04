# streams — parallel work with Worktrunk (Linux workstation)

How the Linux workstation runs parallel implementation streams next to a
project's primary work. [Worktrunk](https://worktrunk.dev) (`wt`) owns the Git
worktree lifecycle; this directory only adds the layout and thin wrappers
around it.

| File | Installed to | Purpose |
|---|---|---|
| `wb-stream` | `~/.local/bin/wb-stream` | Open a stream: Worktrunk worktree + a tmux window in the project session. |
| `wb-stream.test.sh` | — | Tests (scratch repos, isolated tmux server; never touches `/work`). |
| `wb-workspace` | `~/.local/bin/wb-workspace` | Workspace identity, deterministic ports, and dispatch to a project's own setup/teardown. |
| `wb-workspace.test.sh` | — | Tests (scratch repos and Worktrunk config; never touches `/work`). |
| `wb-integrate` | `~/.local/bin/wb-integrate` | Integrate a stream into the primary branch (`wt merge <primary-branch> --stage tracked`, with preconditions and outcome classification). |
| `wb-integrate.test.sh` | — | Tests (scratch repos, real Worktrunk + stub; never touches `/work`). |
| `../config/worktrunk/config.toml` | `~/.config/worktrunk/config.toml` | Model-B worktree path template + the two workspace hooks. |

`workstation/install.sh` links the config and the three commands, and adds Worktrunk's bash integration to
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
| **Create** | `wt switch --create <stream>` branches from the default branch | Always pass a base: `--base @` from the primary checkout (`wb-stream` does this), or `--base <primary-branch>` |
| **Integrate** | bare `wt merge` merges into the default branch (and removes the worktree) | Use `wb-integrate`: it derives the target from the primary checkout and runs `wt merge <primary-branch> --stage tracked`. Never bare `wt merge`. |

Bare `wt merge` from a stream rebases onto the default branch and
fast-forwards it with a squash that includes the primary branch's own
unmerged work, and it exits 0 (verified with 0.68.0). `wb-integrate`
removes that footgun because no target can be passed to it.

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
Worktrunk 0.68). The workspace hooks (below) run as part of its
`wt switch --create`, like for any other worktree.

**If a step fails after Worktrunk ran**, `wb-stream` never rolls back. Hooks may
already have run, and the stream is valid work. Instead it reports what
actually exists (branch, worktree, location) and prints the exact commands to
open the worktree in the project session, or to discard it with
`wt remove <name>`. That command keeps a branch with unmerged work.

## Integrating a stream: `wb-integrate`

From the stream's worktree (no arguments):

```bash
cd /work/orrery/worktrees/map-fix
wb-integrate
```

**Refuses before invoking Worktrunk** (exit 2) unless all of these hold:
- it runs in an exact Model-B side worktree `/work/<project>/worktrees/<stream>`;
- `/work/<project>/main` exists and is the same repository's primary checkout;
- the primary checkout is on a branch (not detached). That branch is the
  target, from `git -C /work/<project>/main branch --show-current`;
- neither checkout is in an interrupted rebase, merge, cherry-pick, revert or
  bisect;
- **the primary checkout is completely clean**: no tracked changes and no
  untracked, unignored files. Worktrunk could stash and restore
  non-overlapping changes there, but `wb-integrate` never touches a human's or
  another agent's working state;
- **the stream has no untracked, unignored files.** They're listed, and you
  commit, delete or ignore them. Uncommitted *tracked* edits are fine:
  `--stage tracked` includes them. Ignored files never block and are never
  committed;
- there is something to integrate (commits or tracked edits beyond the target).

Then it runs `wt merge <primary-branch> --stage tracked`. Worktrunk does
everything else:
- squash (when more than one commit or there are tracked edits; a squash with
  edits leaves `refs/wt-backup/<branch>`);
- rebase onto the target if needed;
- fast-forward the target and update the primary checkout;
- `pre-remove` (`wb-workspace teardown`, while the worktree still exists);
- remove the worktree and branch.

**Outcome, classified from Git state, not from Worktrunk's exit code.**
"Integrated" means the target branch advanced as a fast-forward of its old
tip:

| Exit | Outcome | What you see |
|---|---|---|
| 0 | **Complete** | Target advanced; worktree and branch removed (it waits for Worktrunk's background removal) |
| 3 | **Integrated, cleanup failed** | Target advanced, but the worktree or branch is still there; typically teardown failed (Worktrunk exits 1 here even though the merge landed). **Don't rerun.** Fix the cause, then `wt -C /work/<project>/main remove <branch>`. If Worktrunk keeps the branch as "unmerged" (it compares against the repository default branch), use `git -C /work/<project>/main merge-base --is-ancestor <branch> <target> && git -C /work/<project>/main branch -d <branch>`. |
| 4 | **Conflict** | The rebase stopped in the stream; the target was **not** integrated. Abort with `git -C <stream> rebase --abort`, or resolve, `git add`, `git rebase --continue`, and rerun `wb-integrate`. For a multi-commit stream, Worktrunk squashes before rebasing, so an abort returns to the squash commit; the original commits stay in `git reflog show <branch>`. |
| 2 | **Refused** | A precondition failed; Worktrunk wasn't invoked. The message says what to fix. |
| 5 | **Unknown** | Anything else. It reports Worktrunk's exit code and the observable state, and changes nothing; inspect by hand. |

It never stashes, force-deletes branches (`-D`), cleans `refs/wt-backup`, or
touches tmux. The stream's tmux window stays open; close it yourself. Run from
inside the stream, your shell is left in a removed directory afterwards:
`cd /work/<project>/main`.

## Agents: plain Worktrunk

Autonomous agents use `wt` directly (with the rule above) and never touch
tmux. They integrate with `wb-integrate` too. The same layout applies:

```bash
wt switch --create <stream> --base <primary-branch> --no-cd   # → /work/<project>/worktrees/<stream>
wt list
wb-integrate                                                  # from the stream's worktree
```

## Workspaces: identity, ports, project setup/teardown

Worktrunk owns the lifecycle; `wb-workspace` adds a **stateless** workspace
identity and hands everything runtime-specific to the project. The user config
carries exactly two hooks:

```toml
[pre-start]
workspace = "wb-workspace setup"      # blocking, in the new worktree
[pre-remove]
workspace = "wb-workspace teardown"   # blocking, while the worktree still exists
```

| Command | Does |
|---|---|
| `wb-workspace env` | Print the identity below (fails outside Model-B). |
| `wb-workspace setup [args]` | Export the identity, then `exec` the project's `.config/workspace/setup` (from the worktree root, stdin passed through). |
| `wb-workspace teardown [args]` | Same for `.config/workspace/teardown`. |
| `wb-workspace port [--require-free] <slot>...` | One port per slot, in order. |

**Identity** (exported to the project scripts), from the path alone:

| Variable | `/work/orrery/main` | `/work/orrery/worktrees/fix-map` |
|---|---|---|
| `WORKSPACE_PROJECT` | `orrery` | `orrery` |
| `WORKSPACE_STREAM` | `main` | `fix-map` |
| `WORKSPACE_ID` | `orrery-main` | `orrery-fix-map` |
| `WORKSPACE_PRIMARY` | `/work/orrery/main` | `/work/orrery/main` |
| `WORKSPACE_PATH` | `/work/orrery/main` | `/work/orrery/worktrees/fix-map` |
| `COMPOSE_PROJECT_NAME` | `orrery-main` | `orrery-fix-map` |

`COMPOSE_PROJECT_NAME` is `WORKSPACE_ID` lowercased, with anything outside
`[a-z0-9_-]` turned into `-`. A worktree only counts if its Git common dir is
the primary's. Project and stream names must match `^[A-Za-z0-9][A-Za-z0-9._-]*$`;
anything else under `/work` fails closed. `setup` refuses when another checkout
on the host would derive the same Compose name.

**Ports**: `hash_port("<project>/<stream>/<slot>")`, evaluated by the installed
Worktrunk (`wt step eval`), range 10000–19999. Nothing is recorded: collisions
are checked on every call against the same slots of every Model-B checkout
under `/work`. A collision exits 3 and names both owners; it never moves to
another port. A port that already has a host listener is reported on stderr;
with `--require-free` that exits 4. Collisions with a *different* project's
slot names can't be seen statelessly; a dev server started with a strict port
still fails fast there.

**Resolving a conflict** (the whole policy today):
- a stale or unwanted host listener: stop that listener;
- a genuine deterministic allocation collision: stop and resolve it
  explicitly.

`wb-workspace` never silently selects a different port, and no more
sophisticated collision-resolution policy is defined yet.

**Outside Model-B** (Worktrunk runs user hooks in every repo) `setup` and
`teardown` do nothing and exit 0. Inside, a missing project script is a no-op;
one that exists but isn't executable fails; a project script's exit code is
`wb-workspace`'s.

**Failure behaviour (Worktrunk 0.68, verified):** a failing `setup` leaves the
worktree in place and makes `wt` exit non-zero. A failing `teardown` stops
`wt remove`; bypass with `wt remove --no-hooks <branch>` once the cause is
understood. Project scripts should fail only when continuing is unsafe.

**The primary checkout** is never created by Worktrunk, so no hook runs there:
run `wb-workspace setup` once by hand in `/work/<project>/main`.

**What `wb-workspace` never does:** install dependencies, copy `.env` files or
secrets, run Docker or Compose, delete volumes, or touch tmux. Those belong to
the project's scripts, each project deciding for itself.

**Project scripts** (`.config/workspace/setup`, `.config/workspace/teardown`):
executable, idempotent, run from the worktree root with the identity exported
and Worktrunk's hook JSON on stdin (a terminal or nothing when run by hand).
Worktrunk reads *project hooks* from the checkout `wt` runs in, but these
scripts come from the new worktree itself.

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

Generic layer, deliberately: dependency seeding or copy-on-write, databases,
`.env`/secret propagation, Worktrunk project hooks. Per-project runtime
isolation lives in each project's `.config/workspace/` scripts. No Worktrunk LLM commit generation and no
Claude/Codex/OpenCode Worktrunk plugins are configured.
