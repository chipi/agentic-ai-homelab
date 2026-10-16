# Developer workstation — architecture and operating model

> **Living document — the canonical description of the operating model** on the
> Linux development workstation (Omarchy/Arch). Slices 1–4 are done and
> validated with Orrery: layout, streams, workspace identity and ports, safe
> integration, and two independent Claude workers running concurrently
> ([evidence](#validation-evidence-slices-14)). Next: a second project
> (Slice 5, see the [adoption contract](#second-project-adoption-contract)),
> then multi-project concurrency, persistence and ops, and UX refinement.
> Anything not implemented is labelled as such; known gaps are in
> [Known limitations](#known-limitations-and-deferred-work).

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

**Isolation layers**, outermost concern first:

| Layer | Isolates | Provided by |
|---|---|---|
| Git worktree | source, index, installed dependencies, build output | Worktrunk + `wb-stream` |
| Workspace identity | project / stream / checkout name and its derived ports | `wb-workspace` (generic) |
| Compose project + allocated ports | containers, networks, volumes, host ports | the project's Compose file + generated override |
| tmux window | the persistent interactive session for a human or an independent agent | `wb-stream` (window), the human (starts the agent) |
| systemd / Docker restart policy | machine-level persistent infrastructure | the host |
| Project setup/teardown | project-specific runtime lifecycle (env files, ports, Compose cleanup) | `<project>/.config/workspace/*` |

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
- **Storage:** `/work`, `/var/lib/docker` and `/var/lib/containerd` belong in their
  own top-level Btrfs subvolumes (`@work`, `@docker`, `@containerd`), outside the
  root Snapper domain, so an OS rollback never rewinds project work or Docker state.
  The paths don't change. Layout, files and `wb-storage`:
  [`storage/README.md`](storage/README.md); why:
  [ADR-0011](../docs/adr/ADR-0011-workstation-storage-subvolumes.md). The X3 still
  has them as ordinary directories inside `@` until its one-time
  [migration](../docs/recipes/x3-storage-separation.md) runs.

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

**Independent workers.** An implementation stream is owned by its **own
`claude` process**, started by the human inside the stream's tmux window
(`cd` is already the worktree) and given only that stream's brief. Nothing
starts agents automatically: `wb-stream` opens the window, the human decides
whether an agent runs in it. The primary checkout's agent coordinates and
reviews; it doesn't implement the streams, and it doesn't hand them to
background subagents (those share the parent's process and session, so they
don't count as independent workers; Slice 4A vs 4B, see
[evidence](#validation-evidence-slices-14)).

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
- **Reboot persistence: topology is durable, processes are ephemeral.**
  tmux-resurrect snapshots every session, window, pane, layout and working
  directory (periodically, via `wb-tmux-save.timer`); after a reboot,
  `wb-tmux restore` brings the cockpit back with a plain shell in every pane and
  starts nothing (no agents, servers or test runners). Details, state location and
  recovery: [`tmux/README.md`](tmux/README.md); decision:
  [ADR-0012](../docs/adr/ADR-0012-tmux-workspace-persistence.md).

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

It doesn't create another tmux session, doesn't move your primary shell
(`--no-cd`), and **doesn't start any agent**: to run an independent worker,
switch to the new window and start `claude` there yourself.

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
fast-forwards the target, runs the pre-remove pipeline (live-check, then
teardown), and removes the worktree and branch. `wb-integrate` is **local
composition**, one of two ways a stream completes (see
[Completing and retiring a stream](#completing-and-retiring-a-stream)). It adds
three things.

**1. Conservative preconditions** (refuses before invoking Worktrunk):
- the primary checkout is on a branch and **completely clean**. Worktrunk could
  stash and restore non-overlapping changes there, but `wb-integrate` won't
  touch a human's or another agent's working state;
- the stream has **no untracked, unignored files**. `--stage all`, Worktrunk's
  default, would silently commit them. Uncommitted tracked edits are included
  through `--stage tracked`;
- no interrupted Git operation in either checkout;
- **nothing still running in the stream**: the stream-retirement invariant,
  checked by `wb-workspace live-check` (see
  [Completing and retiring a stream](#completing-and-retiring-a-stream)). Run
  here first so `wb-integrate` refuses before merging anything, rather than
  merging and then being stopped at removal.

**2. Outcome classification from Git state.** "Integrated" means the target
branch advanced as a fast-forward of its old tip, so Worktrunk's exit code
alone is never trusted:

| Exit | Classification | Meaning |
|---|---|---|
| 0 | **COMPLETE** | Target advanced, worktree and branch removed |
| 3 | **INTEGRATED, CLEANUP FAILED** | Target advanced, stream left in place. Typically teardown failed. Worktrunk itself exits 1 here, even though the merge landed. **Never rerun `wb-integrate`.** |
| 4 | **CONFLICT** | Rebase stopped in the stream, target not integrated |
| 2 | **REFUSED** | A precondition failed, Worktrunk not invoked |
| 5 | **UNKNOWN** | Reported as observed, nothing touched; never retried automatically |

**3. Verified recovery guidance:**
- **Conflict:** `git rebase --abort`, or resolve, `git add`,
  `git rebase --continue`, and rerun. For a multi-commit stream, Worktrunk
  squashes *before* rebasing, so an abort returns to the squash commit; the
  original commits stay in the reflog.
- **Cleanup failed:** don't rerun. Fix the cause, run `wt remove`, then delete
  the branch with an ancestry check against the primary branch
  (`git branch -d`). Worktrunk judges "merged" against the repository default
  branch and may keep it.

It never stashes, force-deletes (`-D`), cleans `refs/wt-backup`, cleans
anything globally, or touches tmux. The stream's tmux window stays open and is
closed by hand.

**Before running it, stop what runs in the stream:** exit the stream's agent
and stop any dev server or other process started from the worktree, by its
own PID or process group. That remains the normal procedure, now enforced at
every retirement.

## Completing and retiring a stream

**Invariant: a stream worktree is never removed while a process of yours still
has its working directory in it.** Live-process safety belongs to stream
*retirement*, not to one integration path. Earlier slices enforced it only as a
`wb-integrate` precondition, which left the remote-delivery path unprotected.

**One canonical check, two callers:**
- **`wb-workspace live-check`** is the only implementation: `/proc`-based,
  current user, cwd = the stream or below it. An idle shell only warns, and the
  check never stops anything. Rules:
  [streams/README.md](streams/README.md#completing-and-retiring-a-stream).
- **Step 1 of the Worktrunk `pre-remove` pipeline.** It runs before the project
  teardown (step 2) and before removal, for every Worktrunk retirement: direct
  `wt remove`, `wt merge`, `wb-integrate`. A refusal leaves the worktree, the
  branch and the project runtime untouched.
- **`wb-integrate`'s precondition,** run before it merges. The hook alone would
  catch the process only *after* the fast-forward (exit 3).

**Two first-class completion paths.** Which one depends on the project, the
change and its stage. Workbench prescribes neither and is repository-host
agnostic:

| Path | Flow | Retirement |
|---|---|---|
| Local composition | stream → `wb-integrate` → local primary branch → (push, or a PR from there, as the project does) | Part of `wb-integrate` |
| Remote delivery | stream → push → PR → merged on the host → sync the primary checkout → retire | `wt -C /work/<project>/main remove <branch>` |

- **Local composition only:** `wb-integrate` composes locally; it isn't
  universal delivery.
- **Don't integrate twice:** a stream the host already merged is never run
  through `wb-integrate`. Retire it.
- **Local branch:** Worktrunk deletes it when it sees the work integrated into
  the repository default branch (ancestry, tree or patch-id, so squash merges
  too). When the primary branch isn't the default, it keeps the branch as
  "unmerged", and deleting it is a deliberate human step.
- **Remote branch:** deleting it is outside Workbench, for the host or project
  tooling.

**Not protected:** `wt remove --no-hooks` (it also skips the project teardown;
never use it to get past a refusal) and plain `git worktree remove`.

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

**Generated client config:** `.env.workspace` `VITE_*` values (today only
`VITE_LAB_API_URL`) configure Orrery's local Vite **dev server** only. Builds
(including Docker and mobile) and Vitest never receive them. An Orrery
decision, found when two workers hit opposite halves of it in Slice 4B; not a
rule every project must share.

**Lab API state:** per-checkout `.lab-api-state/` (never shared); the allowlist
is read from the primary and is created by hand.

**Build artifacts and Docker:** each checkout owns its `build/`. Its `web`
container bind-mounts `build/`, and every build replaces that directory, so a
container started earlier keeps serving a deleted, empty directory (HTTP 500)
while still reporting healthy for a while. The canonical command is
`npm run docker:e2e` (build, recreate this checkout's `web`, smoke and version
check, Playwright); `npm run docker:e2e -- --skip-build --smoke-only` recovers
without building. A missing `build/` fails loudly (`create_host_path: false`).

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

Primary and stream Compose projects running side by side, and a stream's
teardown removing only its own containers and network, are validated (Orrery,
Slices 2 and 4B; see [evidence](#validation-evidence-slices-14)).

**Compose-file rules for worktree-aware projects:**
- no fixed `container_name`;
- no globally named volumes where Compose-scoped ones fit;
- no fixed host ports in a stream: they come from the project's generated
  override;
- teardown is scoped to the current Compose project;
- no generic `down -v`, unless the project explicitly defines that data as
  disposable and scoped to the checkout.

Operational Docker rules (no global cleanup) are in
[Multi-agent safety rules](#multi-agent-safety-rules).

**Storage.** Docker 29 runs with the containerd image store, so its persistent state
is split: `/var/lib/containerd` holds image content, layer snapshots and the BuildKit
cache data; `/var/lib/docker` holds Docker's metadata, BuildKit records, networks,
volumes and container logs. Both move to their own subvolumes together
([`storage/README.md`](storage/README.md)). Omarchy's `docker.service` has
`DefaultDependencies=no`, so the workstation's `RequiresMountsFor=` drop-ins keep
Docker and containerd from starting before those mounts exist. `docker.socket` is
enabled: any `docker` command starts the daemon.

## Worktrunk lifecycle hooks

The user config carries exactly these hooks:

```toml
[pre-start]
workspace = "wb-workspace setup"           # blocking, in the new worktree
[[pre-remove]]                             # a pipeline: steps run in order
live-check = "wb-workspace live-check"     # 1. retirement invariant
[[pre-remove]]
workspace = "wb-workspace teardown"        # 2. blocking, while the worktree still exists
```

Order at every retirement (`wt remove`, `wt merge`, `wb-integrate`), verified
with Worktrunk 0.68.0 and regression-tested in `streams/wb-workspace.test.sh`:
1. Worktrunk refuses a dirty worktree *before* any hook;
2. `live-check`;
3. project teardown;
4. removal.

- **pre-start fails:** the new worktree and branch are kept (no rollback) and
  `wt` exits non-zero.
- **A pre-remove step fails:** the remaining steps are skipped and the removal
  stops. A refusing `live-check` therefore stops the project teardown too.
  Teardown runs while the worktree still exists, so a failed teardown never
  leaves an orphaned runtime behind a deleted checkout.
- **Why a pipeline:** Worktrunk runs a `[pre-remove]` table's commands
  concurrently, which can't order the check before teardown. A mutation test
  proves the difference.
- **Escape hatch:** `wt remove --no-hooks <branch>` skips both steps. Use it
  only once the leftover runtime state is understood and no process is left in
  the stream.

All of this is intentional safety behaviour.

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
- **Project root = the invocation's own cwd** (its Git top-level: a worktree is
  its own root). A wrong root such as `/work/orrery/main` for an agent elsewhere
  came from LeanCTX's shared daemon, which checked hook-rewritten reads
  (`cat`/`sed`/`grep`/`ls` → `lean-ctx read|grep|ls`) against the cwd it was
  started in. Fixed by `export __LEAN_CTX_NO_DAEMON=1` in `~/.bashrc` (installed by
  `install.sh`; agents started afterwards pick it up). Cause, evidence,
  troubleshooting: [`config/lean-ctx/README.md`](config/lean-ctx/README.md).
- **Observed friction (not fixed):**
  - some commands and shell forms are blocked by policy: `node -e`,
    `python3 -c`, some subshell groupings, and earlier `ss`.
  The workaround is the agent's native read tool or a script file; never
  widen the allowlist to get past a single block.

## Multi-agent safety rules

The workstation is shared by the human, several projects and several agents
at once, all as the same highly privileged user. These rules are the
isolation boundary the tooling can't enforce.

**Git and worktrees**
- Never let two implementation agents modify the same checkout. Independent
  code change → its own worktree (`wb-stream`).
- Research-only work (reading, review, subagents that don't edit code) needs
  no worktree.
- Never remove, reset or edit another worker's worktree. Streams end through
  `wb-integrate` (or a deliberate `wt remove` by their owner), never `rm -rf`.

**Processes**
- Process ownership is an isolation boundary. Stop only processes you started,
  by captured PID, by captured process group (`setsid` …; `kill -- -<pgid>`),
  or through a project- or checkout-scoped mechanism (`docker compose` in that
  checkout, a server's own stop command).
- Never `pkill`, `killall` or `pkill -f <generic pattern>`: on this host a
  pattern like `vite`, `node` or `playwright` matches other checkouts', other
  projects' and other agents' processes.
- Diagnostic trap: `pgrep -f <pattern>` also matches the command line of the
  checking command itself. Before treating a hit as a leftover process,
  confirm the PID still exists and is what you think (`ps -o pid,args -p <pid>`).

**Docker**
- Never run host-global destructive operations: `docker system prune -a`,
  `docker volume prune`, `docker image prune -a`, or stopping or removing
  containers across projects.
- Use Compose operations scoped to the current checkout's project
  (`docker compose …` inside the checkout, or `-p <COMPOSE_PROJECT_NAME>`).

**Secrets**
- Workspace setup never silently copies secret files into side worktrees.
  A project may offer an explicit opt-in (Orrery: `wb-workspace setup --link-env`
  creates a symlink, never a copy).

## Validation evidence (Slices 1–4)

What has actually been demonstrated on this machine (Orrery as the test
project). Numbers are from the final runs, not targets.

**Slices 1–3:** Model-B layout and `wb-stream`; deterministic per-stream ports
and Compose project names (`wb-workspace`); scoped teardown; `wb-integrate`
preconditions and outcome classification (its own test suite); a primary and a
stream Compose stack serving at the same time.

**Slice 4A** (two parallel streams; workers were **background subagents of one
parent Claude**, so this did *not* prove independent workers):
- two concurrent worktrees from the same primary, distinct identities and
  ports, concurrent Node installs, tests and builds;
- primary stayed clean; ample memory headroom; no port, cache or lock
  collision;
- `wb-integrate` fast-forward path, and the stale-base **rebase** path (the
  second stream rebased onto the first);
- scoped teardown;
- found and fixed: per-checkout lab API state (it had defaulted to a shared,
  unwritable `/srv` path); found: Vitest picking up a stream's generated
  `VITE_*` values; LeanCTX root and path friction; the dependency duplication
  cost.

**Slice 4B** (the missing proof: two **independent `claude` processes**, each in
its own tmux window and worktree):
- independent `npm ci` bootstrap, concurrent implementation, concurrent
  tests and builds;
- a real Compose runtime in one stream next to the primary's (`orrery-main`
  on 8080, the stream on its derived port);
- human-approved scope expansion; the two workers independently found opposite
  halves of one configuration bug (generated `VITE_*` values reaching builds vs
  Vitest), reconciled into one design before integration;
- stream B integrated while stream A stayed alive and untouched; B's teardown
  scoped to B;
- A integrated on top of the advanced primary; its teardown stopped and removed
  only its own container and network;
- the new Orrery Docker command accepted in the primary checkout;
- normal pre-push hook and push; local `main` == `origin/main` at the end.

Final numbers: stream A's full Docker E2E: 730 passed, 4 flaky, 38 skipped,
exit 0 (the flakes are Orrery test issues, not workstation failures, and are
not fixed). Primary preflight: 5,662 tests passed; coverage stayed above the
repository's floors.

## What belongs where

| Place | Owns |
|---|---|
| `agentic-ai-homelab/workstation` | Generic workstation policy, installer, Worktrunk config, `wb-stream`, `wb-workspace`, `wb-integrate`, the storage layout (`storage/`: `wb-storage`, systemd drop-ins), shared agent configuration |
| Project repository | Runtime declaration (e.g. `mise.toml`), package dependencies, `.config/workspace/{setup,teardown}`, project-specific Compose accommodations, rules for generated runtime config |
| tmux | Interactive sessions and UI organisation only |
| Docker (Compose) | Service runtime only, namespaced per checkout |
| Git + Worktrunk | Source checkout lifecycle |
| systemd / Docker restart policy | Machine-level persistent infrastructure |

## Known limitations and deferred work

The one list of open workstation issues. Project-specific ones live in the
project (Orrery: `.config/workspace/README.md`, "Known limitations").

| Issue | Status | Notes |
|---|---|---|
| Live process at stream retirement | **Resolved** (retirement invariant) | Was: the worktree removed underneath a running `claude` or dev server (Slice 4B), and the remote-delivery path (`wt remove` after a PR merge) wasn't checked at all. Now `wb-workspace live-check` is step 1 of the `pre-remove` pipeline for every Worktrunk retirement, and also a `wb-integrate` precondition. Remaining gaps: only the cwd is checked (not open files); other users' and containers' processes are invisible; a process started between the check and the removal isn't caught; `wt remove --no-hooks` and `git worktree remove` bypass it. |
| Stream tmux windows stay open | Expected | `wt remove` / `wb-integrate` don't close windows; close them by hand. An idle pane shell in the stream only produces a warning at integration; it then sits in the deleted trash path. A UX concern, not an integration blocker. |
| LeanCTX project root | **Resolved** (per-invocation root) | Cause: hook-rewritten one-shot reads went through LeanCTX's shared daemon, rooted in the directory of whichever call started it (`/work/orrery/main` on the X3); MCP `ctx_*` tools were always rooted correctly, hence the inconsistency in 4A/4B. Fix: `__LEAN_CTX_NO_DAEMON=1` from `~/.bashrc`; running agents need a restart to pick it up ([`config/lean-ctx/README.md`](config/lean-ctx/README.md)). Command-policy friction remains (see [LeanCTX](#leanctx)). |
| Dependency duplication | Deferred | Each fresh worktree runs its own install (Orrery: about 1.2 GB `node_modules` per stream, plus about 2 GB checkout). Correct, not storage-efficient. |
| Compose image accumulation | Deferred | Scoped `docker compose down` removes containers and networks, not built images; per-stream images remain after teardown. Needs a scoped maintenance policy, never a global prune. |
| `refs/wt-backup/<branch>` | Deferred | Left by Worktrunk after squashing tracked edits; nothing cleans them. |
| Port allocation | By design | Deterministic and stateless; a collision stops the operation and is resolved explicitly; never changed silently. Collisions across differently named slots of other projects aren't detectable. |
| `session-reap.sh` family sweep under `/work` | Unverified | Its main reap is checkout-scoped (cwd under the session's directory), which suits Model-B. Its cross-worktree `gh run` loop sweep keys on a `$HOME/<container>/<base>` family prefix from the older layout; not verified for `/work/<project>/…`. |
| tmux sessions don't survive a reboot | **Resolved** (tmux persistence) | The topology comes back with `wb-tmux restore` ([`tmux/README.md`](tmux/README.md)); the programs that ran in the panes don't, by design. Without a snapshot: `tmux new -s <project> -c /work/<project>/main`. |
| LUKS manual unlock | Expected | Needed before the machine is reachable after a cold boot. |
| Storage | Codified; X3 migration pending | The layout (`@work`, `@docker`, `@containerd` outside the root rollback domain) is codified in `storage/` and [ADR-0011](../docs/adr/ADR-0011-workstation-storage-subvolumes.md); the X3 is migrated by hand with the [runbook](../docs/recipes/x3-storage-separation.md). The 2 TB disk is enough for now; a second encrypted NVMe can later take the three subvolumes by changing only their fstab lines. |
| cmux remote-tmux | Optional | Beta; nothing depends on it. |
| Dashboard / control plane | Deferred | Only if daily use proves the need. |

## Second-project adoption contract

What a new project (next: OceanCanvas, Slice 5) needs to run in Model-B,
ideally without changing any generic tooling. A generic change is justified
only for a capability every project would need, never for one project's
special case.

**The workstation provides (generic, unchanged per project):**
- the `/work/<project>/{main,worktrees/<stream>}` layout and Worktrunk lifecycle;
- `wb-stream`: a stream from the current primary (`--base @`) plus its tmux
  window in the project's session;
- `wb-workspace`: identity (`WORKSPACE_*`, `COMPOSE_PROJECT_NAME`),
  deterministic collision-checked ports (`wb-workspace port <slot>…`), and
  dispatch to the project's setup/teardown from the Worktrunk hooks;
- `wb-integrate`: safe integration into the primary branch with outcome
  classification;
- the safety rules above.

**The project provides (as needed):**
- a tracked runtime declaration (root `mise.toml`);
- `.config/workspace/setup` and `.config/workspace/teardown` (executable,
  idempotent, never overwriting user files): generate its own git-ignored
  runtime/env files, ask `wb-workspace port` for the slots it needs, and keep
  the primary's familiar defaults where practical;
- a Compose file that names nothing globally, plus a generated override for
  the project name and stream host ports;
- dependency bootstrap and validation commands, documented;
- its secrets policy (default: nothing copied into streams);
- a short contract README next to its workspace scripts.

**Done when:** the new project creates, runs, tests and integrates streams
through these hooks alone, while Orrery keeps working on the same machine
(the start of cross-project isolation testing).
