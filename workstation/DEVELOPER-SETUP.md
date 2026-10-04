# Developer workstation — architecture and operating model

> **Living document, work in progress.** It describes the operating model as
> implemented today on the Linux development workstation (Omarchy/Arch). It
> will change as the next stages land: Worktrunk Slice 3+, multi-agent stress
> testing, generalizing to a second project, persistence and ops decisions,
> and possibly a control plane if daily use proves one is needed. Anything not
> implemented is labelled as such.

Day-to-day commands: [`DEVELOPER-GUIDE.md`](DEVELOPER-GUIDE.md). Command
contracts and Worktrunk details: [`streams/README.md`](streams/README.md).
Installing a machine: [`setup-new-computer.md`](setup-new-computer.md).

## Purpose

An always-on Linux machine for several independent software projects, with
several coding agents working at once. Each concern has exactly one owner:

| Concern | Owner |
|---|---|
| Graphical cockpit, human navigation | Omarchy / Hyprland |
| Remote access | OpenSSH over Tailscale |
| Persistent interactive project sessions | tmux, one session per project |
| Code isolation and worktree lifecycle | Git worktrees, managed by [Worktrunk](https://worktrunk.dev) (`wt`) |
| Creating a Model-B side stream plus its tmux window | `wb-stream` (workstation orchestration) |
| Integrating a side stream into the primary branch | `wb-integrate` (thin safety wrapper around `wt merge`) |
| Workspace identity, deterministic ports, project lifecycle delegation | `wb-workspace` (generic) |
| Project runtime and tool versions | mise |
| Runtime and service isolation | Docker Compose project namespaces, on one shared daemon |
| Application-specific workspace behaviour | the project's own `.config/workspace/*` scripts |
| Machine-level persistent infrastructure | systemd units, Docker restart policies |
| Agent policy and context layer (not product source) | LeanCTX |

Keep these separate:
- tmux doesn't own worktrees;
- Worktrunk doesn't own tmux;
- `wb-workspace` doesn't know any product;
- Docker only runs services;
- project behaviour lives in the project.

## Workspace layout

```
/work/<project>/
├── main/              primary working checkout (permanent)
└── worktrees/
    ├── <stream-a>/    parallel implementation stream (temporary)
    └── <stream-b>/
```

- **`main/` is the permanent primary working checkout. It may be on any Git
  branch.** The directory name doesn't mean the checkout is on branch `main`.
  The branch it's on is the **primary branch** (the primary working line).
- **`worktrees/<stream>`** holds temporary parallel streams. A stream normally
  lives hours or days (occasionally longer), then is integrated or discarded.
- **No nested worktrees.** Worktrunk resolves the repo path to the primary
  checkout even from inside a stream, so a stream created from a stream still
  lands in `worktrees/`.
- `/work` is the intentional Model-B root, hard-coded in the Worktrunk config,
  `wb-stream` and `wb-workspace`.

## Model-B development model

- One permanent primary checkout per project, normally carrying one main line
  of work.
- Create a side worktree only for **genuinely parallel implementation**.
- Research, reading, review and subagent work that doesn't modify code needs
  no worktree.
- Independent code modification needs its own worktree.
- Independent code **and** runtime needs a worktree plus runtime isolation (see
  [wb-workspace](#wb-workspace) and [Docker](#docker-model)).

**Why:** concurrent agents must not step on each other's Git state, installed
dependencies, generated files, running services, ports or other runtime
resources.

## tmux model

The convention: **one tmux session per project, with several windows**, named
exactly after the project directory. The prefix is Omarchy's **Ctrl+Space**.

```
tmux: orrery
├── claude        ┐
├── server        │ primary windows, long-lived
├── terminal      ┘
└── feature-x       side-stream window, temporary
```

- tmux provides persistent interactive sessions and UI only. It doesn't own
  the worktree lifecycle (Worktrunk does) or the runtime lifecycle (the
  project's Compose setup does).
- `wb-stream` adds a stream window to the existing project session. It never
  creates a session per worktree.
- **Removing a worktree (`wt remove`) doesn't close its tmux window.** Kill
  stale windows by hand.
- No Worktrunk hook touches tmux, by design.

## Worktrunk

Worktrunk is the generic Git worktree lifecycle: create, list, merge, remove.
The workstation configures it through one tracked user config,
[`config/worktrunk/config.toml`](config/worktrunk/config.toml), linked to
`~/.config/worktrunk/config.toml`.

**Worktree path.** For a repo rooted exactly at `/work/<project>/main`, new
worktrees go to `/work/<project>/worktrees/<branch | sanitize>`. Every other
repo keeps Worktrunk 0.68's default sibling layout (`<repo>.<branch>`). If an
upgrade breaks the template, `wt` refuses to create anything.

### ⚠️ Model-B rule: base on the primary checkout, integrate into an explicit target

Worktrunk defaults both ends of a stream's life to the repository's **default
branch**. In Model-B the primary checkout is often on a different branch, so
both defaults are wrong here:

| Step | Worktrunk default | Model-B rule |
|---|---|---|
| Create | `wt switch --create <stream>` branches from the default branch | Base the stream on the **current primary checkout**: `--base @` run from `main/` (`wb-stream` does this), or `--base <primary-branch>` |
| Integrate | bare `wt merge` merges into the default branch (and removes the worktree) | Integrate into the **intended primary working branch** with [`wb-integrate`](#wb-integrate), which derives it from `main/` and runs `wt merge <primary-branch> --stage tracked`. Never bare `wt merge`. |

The repository's default branch is not assumed to be the integration target.
Agents may use plain `wt` to create and inspect streams, but integrate with
`wb-integrate`.

## wb-stream

Workstation orchestration for opening a Model-B side stream
([`streams/wb-stream`](streams/wb-stream)):

```bash
cd /work/orrery/main
wb-stream feature-x
```

It:

1. validates that it runs in the Model-B primary checkout, on a branch;
2. checks the request is unambiguous before creating anything (valid unused
   branch name, free target directory, the `orrery` tmux session exists, no
   window of that name yet);
3. runs `wt switch --create feature-x --base @ --no-cd --format json`, which
   creates branch `feature-x` from the current primary branch and the worktree
   `/work/orrery/worktrees/feature-x`, and runs Worktrunk's pre-start hooks
   (workspace setup);
4. verifies the worktree is at the expected path, then opens window
   `feature-x` in the existing `orrery` session, rooted in the worktree.

It doesn't create another tmux session and doesn't move your primary shell
(`--no-cd`).

**Names:** `/` becomes `-` for the directory and window name, exactly like
Worktrunk's `sanitize` (`fix/map` → `worktrees/fix-map`, window `fix-map`).
The Git branch keeps its slash.

**Partial failure:** once Worktrunk has run, `wb-stream` never rolls back.
Created Git state is preserved. It reports what actually exists (branch,
worktree, location) and prints the exact commands to open the worktree in the
project session or to discard it with `wt remove`.

## wb-integrate

The safe Model-B integration path ([`streams/wb-integrate`](streams/wb-integrate)),
run from the stream's worktree with no arguments:

```bash
cd /work/orrery/worktrees/feature-x
wb-integrate
```

**The target is never an argument.** It's always the branch checked out in
`/work/<project>/main`, so the default-branch footgun can't happen. All the work
is Worktrunk's: `wt merge <primary-branch> --stage tracked` squashes, rebases,
fast-forwards the target, runs the pre-remove teardown, and removes the
worktree and branch. `wb-integrate` adds three things.

**1. Conservative preconditions** (refuses before invoking Worktrunk):
- the primary checkout is on a branch and **completely clean**. Worktrunk could
  stash and restore non-overlapping changes there, but `wb-integrate` won't
  touch a human's or another agent's working state;
- the stream has **no untracked, unignored files**. `--stage all`, Worktrunk's
  default, would silently commit them. Uncommitted tracked edits are included
  through `--stage tracked`;
- no interrupted Git operation in either checkout.

**2. Outcome classification from Git state.** "Integrated" means the target
branch advanced as a fast-forward of its old tip, so Worktrunk's exit code
alone is never trusted:

| Exit | Outcome |
|---|---|
| 0 | Complete: target advanced, worktree and branch removed |
| 3 | Integrated, but cleanup failed: target advanced, stream left in place. Typically teardown failed. Worktrunk itself exits 1 here, even though the merge landed. |
| 4 | Conflict: rebase stopped in the stream, target not integrated |
| 2 | Refused: a precondition failed, Worktrunk not invoked |
| 5 | Unknown: reported as observed, nothing touched |

**3. Verified recovery guidance:**
- **Conflict:** `git rebase --abort`, or resolve, `git add`,
  `git rebase --continue`, and rerun. For a multi-commit stream, Worktrunk
  squashes *before* rebasing, so an abort returns to the squash commit; the
  original commits stay in the reflog.
- **Cleanup failed:** don't rerun. Fix the cause, run `wt remove`, then delete
  the branch with an ancestry check against the primary branch
  (`git branch -d`). Worktrunk judges "merged" against the repository default
  branch and may keep it.

It never stashes, force-deletes (`-D`), cleans `refs/wt-backup`, or touches
tmux. The stream's tmux window stays open and is closed by hand.

## wb-workspace

The generic layer for workspace identity, deterministic ports and project
lifecycle delegation ([`streams/wb-workspace`](streams/wb-workspace)):

| Command | Does |
|---|---|
| `wb-workspace env` | Print this checkout's identity |
| `wb-workspace setup [args]` | Export the identity and run the project's `.config/workspace/setup`, if any |
| `wb-workspace teardown [args]` | Same for `.config/workspace/teardown` |
| `wb-workspace port [--require-free] <slot>...` | One deterministic port per slot |

**Identity**, derived from the checkout path alone:

| Variable | Primary (`/work/orrery/main`) | Side (`/work/orrery/worktrees/feature-x`) |
|---|---|---|
| `WORKSPACE_PROJECT` | `orrery` | `orrery` |
| `WORKSPACE_STREAM` | `main` | `feature-x` |
| `WORKSPACE_ID` | `orrery-main` | `orrery-feature-x` |
| `WORKSPACE_PRIMARY` | `/work/orrery/main` | `/work/orrery/main` |
| `WORKSPACE_PATH` | `/work/orrery/main` | `/work/orrery/worktrees/feature-x` |
| `COMPOSE_PROJECT_NAME` | `orrery-main` | `orrery-feature-x` |

(`WORKSPACE_STREAM=main` names the primary checkout, whatever branch it's on.)

**Ports.** `port <slot>` returns `hash_port("<project>/<stream>/<slot>")`,
evaluated by the installed Worktrunk (range 10000–19999). The same checkout
always gets the same ports.

- **Detected collisions:** with another requested slot of the same checkout,
  or with the same slot names of any other Model-B checkout under `/work`. It
  fails (exit 3, naming both owners) and never silently picks another port.
- **Not guaranteed:** collisions involving *differently named* slots of other
  projects can't be detected without state. A service started with a strict
  port still fails fast in that case.
- **Host listeners:** a port that already has a listener is reported; with
  `--require-free` that fails (exit 4).

**Resolving a conflict** (this is the whole policy today):
- a stale or unwanted host listener: stop that listener;
- a genuine deterministic allocation collision: stop and resolve it
  explicitly.

`wb-workspace` deliberately never selects a different port silently. No more
sophisticated collision-resolution policy has been defined yet.

**Stateless.** Every answer is derived from the path and `hash_port`, and
nothing is recorded. `wb-workspace` knows nothing about npm, Vite, any
product, secrets or Compose services. It never installs dependencies, copies
`.env` files, runs Docker or touches tmux. Outside Model-B, `setup` and
`teardown` do nothing.

## Project-specific workspace integration

| Layer | Lives in | Knows |
|---|---|---|
| Generic workstation | `workstation/streams/wb-workspace` | Layout, identity, ports, dispatch |
| Project | `<project>/.config/workspace/setup`, `<project>/.config/workspace/teardown` | That project's runtime: env files, Compose accommodations, the ports it needs |

Worktrunk's user hooks call `wb-workspace`. `wb-workspace` delegates to the
project scripts when they exist and are executable. Generic policy stays out
of product repos, and product details stay out of the workstation.

The filesystem layout itself comes from the `/work` convention and the
Worktrunk/`wb-stream` lifecycle, not from `wb-workspace`. A project without
`.config/workspace/setup` or `teardown` can still use `wb-workspace`'s generic
identity and deterministic-port facilities. Lifecycle setup and teardown just
have nothing project-specific to delegate to.

The primary checkout is never created by Worktrunk, so no hook runs there. Run
`wb-workspace setup` once by hand in `/work/<project>/main`.

### Example: Orrery (first acceptance project, project-specific)

Orrery is the first project integrated with this model. Its accommodations
below are Orrery's own, not workstation behaviour. Its contract is
`orrery/.config/workspace/README.md`.

**Primary** (`/work/orrery/main`):
- `COMPOSE_PROJECT_NAME=orrery-main`;
- existing default host ports are unchanged (Docker web on **8080**; Vite
  5273, E2E 4173, Lab API 8093, MCP 8091).

**Side stream** (e.g. `/work/orrery/worktrees/feature-x`):
- `COMPOSE_PROJECT_NAME=orrery-feature-x`;
- setup derives isolated ports with
  `wb-workspace port web e2e docker-web lab-api mcp` (Vite dev, E2E, Docker
  web, Lab API, MCP).

**Generated files** (both checkouts):
- `.env.workspace` holds runtime defaults: identity, ports, URLs, never
  secrets.
- `docker-compose.override.yml` holds the Compose project name and, for a
  side stream, its Docker web host port.
- Both are git-ignored and regenerated idempotently. Setup only overwrites
  files it generated itself.

**Secrets:** never copied. `wb-workspace setup --link-env` explicitly symlinks
the primary's `.env` into a side stream when needed.

**Build artifacts:** each checkout owns its own. Run `npm run build` in a
checkout before starting its Docker `web` service. The Compose bind mount for
`build/` uses `create_host_path: false`, so a missing build fails loudly
instead of Docker silently creating an empty root-owned `build/`.

**Teardown:**
- stops only this checkout's Compose project (`docker compose -p <name> down --remove-orphans`);
- keeps volumes, except volumes the Compose file explicitly labels disposable,
  and then only for side streams.

**Runtime:** Node 20, declared in the tracked root `mise.toml`
([below](#project-runtimes-mise)).

**Known Orrery issue (under investigation):** `@capacitor/cli` 8.4.1 declares
Node `>=22` while Orrery is pinned to Node 20. That's an Orrery dependency
compatibility question, not a workstation runtime gap.

## Docker model

- One shared host Docker daemon.
- Isolation comes from **Compose project namespaces** (`COMPOSE_PROJECT_NAME`),
  not from a daemon per project or worktree.
- A primary checkout and its side streams can run their services at the same
  time.

**Recorded acceptance result** (Orrery):

| Compose project | Service | Host port |
|---|---|---|
| `orrery-main` | web | 8080 (primary default) |
| `orrery-x3-runtime-smoke` | web | 17573 (derived by `wb-workspace port` for that stream) |

What it showed:
- both ran simultaneously and both served HTTP 200;
- recreating the primary didn't affect the side stream;
- removing the side stream tore down only its Compose project and network,
  while the primary kept serving.

17573 was a generated value for that stream name, not a configured port.

### Docker safety rules

- **Never** run host-global destructive cleanup from project or agent
  workflows, such as `docker system prune -a`, `docker volume prune`, or
  anything equivalent that reaches other projects' resources.
- Teardown is scoped to the current Compose project.
- No fixed `container_name` for worktree-aware services.
- No globally named volumes where Compose-scoped ones fit.
- No generic `down -v`, unless the project explicitly defines that data as
  disposable and scoped to the checkout.

## Worktrunk lifecycle hooks

The user config carries exactly two hooks:

```toml
[pre-start]
workspace = "wb-workspace setup"      # blocking, in the new worktree
[pre-remove]
workspace = "wb-workspace teardown"   # blocking, while the worktree still exists
```

- **pre-start fails:** the new worktree and branch are kept (no rollback) and
  `wt` exits non-zero.
- **pre-remove fails:** the removal stops. Project teardown runs while the
  worktree still exists, so a failed teardown never leaves an orphaned runtime
  behind a deleted checkout. The escape hatch is
  `wt remove --no-hooks <branch>`, used only once the leftover runtime state is
  understood.

Both behaviours are intentional safety behaviour.

## Project runtimes (mise)

| What | Managed by |
|---|---|
| OS packages | `pacman` |
| Development runtime and tool versions (Node, CLIs) | mise, the workstation's runtime and version manager |
| Project dependencies | the project's package manager (npm, …) |

**The contract:**
- Projects declare their runtime versions in tracked mise configuration (a
  root `mise.toml`), so every checkout, including a fresh worktree, carries
  the declaration.
- Correctly initialized interactive workstation shells (Omarchy's bash setup
  runs `mise activate`) honour that declaration when you enter the checkout.
- The workstation-wide mise default applies only where a project declares
  nothing.

**Orrery:** its tracked root `mise.toml` declares Node 20.

**Acceptance-tested** in a fresh Worktrunk side stream:
- plain `node` resolved to Node 20.20.2;
- plain `npm ci` succeeded.

**Caveat:** a long-lived or non-interactive process with a previously fixed
`PATH` may not reflect a later directory change. When diagnosing such a
process, compare `node --version` with `mise current node`.

## SSH and remote operation

- The machine is on a Tailscale network. Remote access is normal OpenSSH over
  Tailscale with key authentication only: password and keyboard-interactive
  authentication are disabled, and root login is disabled.
- **Outbound GitHub access** uses a passphrase-protected key held by one
  systemd user ssh-agent (`ssh-agent.socket`) at a stable `SSH_AUTH_SOCK`. It
  is unlocked manually once per boot with `ssh-add ~/.ssh/id_ed25519`. Details:
  [README → SSH agent](README.md#ssh-agent-linux).
- **tmux sessions** survive SSH disconnects, but not a reboot.
- **Full-disk LUKS:** after a cold boot or power loss, the disk must be
  unlocked physically or manually before the machine is reachable remotely.

## Agent security and privilege model

- Coding agents run as the normal workstation user and are **highly
  privileged**.
- That user is in the `docker` group, which is effectively root-equivalent.
- This setup prioritises autonomous development productivity. **It is not a
  strong agent sandbox.** Safety rests on agents following scoped-operation
  rules: Model-B worktrees, Compose-scoped Docker operations, and no
  host-global destructive commands.

## LeanCTX

- The agent policy and context layer, shared across projects; workstation
  configuration, not product source code. Its config is tracked here
  (`config/lean-ctx/config.toml`).
- Its executable allowlist includes the workstation helpers `wt`, `wb-stream`,
  `wb-workspace` and `wb-integrate`.
- Don't put LeanCTX-specific state into product repositories unless it's
  intentionally required.

## What belongs where

| Place | Owns |
|---|---|
| `agentic-ai-homelab/workstation` | Generic workstation policy, installer, Worktrunk config, `wb-stream`, `wb-workspace`, `wb-integrate`, shared agent configuration |
| Project repository | Runtime declaration (e.g. `mise.toml`), package dependencies, `.config/workspace/{setup,teardown}`, project-specific Compose accommodations, rules for generated runtime config |
| tmux | Interactive sessions and UI organisation only |
| Docker (Compose) | Service runtime only, namespaced per checkout |
| Git + Worktrunk | Source checkout lifecycle |
| systemd / Docker restart policy | Machine-level persistent infrastructure |

## Known limitations and follow-ups

- **`wt remove` and `wb-integrate` don't close the stream's tmux window.**
- **`refs/wt-backup/<branch>` refs** that Worktrunk leaves after squashing
  tracked edits are kept; nothing cleans them yet.
- **Port allocation is deterministic and stateless.** A detected collision
  stops the operation and must be resolved explicitly (see
  [wb-workspace](#wb-workspace)); ports are never changed silently. No
  collision-resolution policy beyond that exists yet. Detection isn't
  guaranteed across differently named slots of other projects.
- **A reboot destroys all tmux sessions.**
- **LUKS needs a manual unlock** before the machine and its remote services
  are reachable.
- **cmux remote-tmux integration** is optional and beta; nothing here depends
  on it.
- **No dashboard or control plane exists.** It's deferred, a possible later
  layer only if real daily use proves the need.
