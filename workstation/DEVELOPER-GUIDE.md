# Developer guide — day to day on the workstation

> **Living document, work in progress.** It reflects the current operating
> model and evolves with it. Why things work this way:
> [`DEVELOPER-SETUP.md`](DEVELOPER-SETUP.md). Command details:
> [`streams/README.md`](streams/README.md).

## Mental model

```
one project
├── /work/<project>/main                primary checkout, permanent, on the primary branch (ANY branch)
├── /work/<project>/worktrees/<stream>  optional temporary parallel streams
└── tmux session <project>              one session per project, one window per stream
```

- One primary line of work.
- Open a stream only for genuinely parallel code changes.
- **Streams start from the current primary checkout and integrate back into
  the primary branch, always named explicitly.**

## Start work on a project

```bash
ssh omarchy                 # your SSH alias for the workstation (over Tailscale)
tmux attach -t orrery
```

Only if the project's session really doesn't exist yet (for example after a
reboot), create it, named exactly after the project:

```bash
tmux new -s orrery -c /work/orrery/main
```

One session per project; don't create more.

## Primary checkout

```bash
cd /work/orrery/main
git status
git branch --show-current   # the primary branch: what streams start from and merge into
```

`main/` is the permanent primary checkout. It may be on any branch; the
directory name doesn't mean Git branch `main`.

## Create a parallel stream

```bash
cd /work/orrery/main
wb-stream feature-x
cd /work/orrery/worktrees/feature-x   # or switch to the new tmux window "feature-x"
```

- Branch `feature-x` starts from the current primary branch (`--base @`).
- A window `feature-x` opens in the `orrery` session.
- Your primary shell stays where it was.
- `fix/map` becomes directory and window `fix-map`; the branch keeps the slash.

Agents without tmux: `wt switch --create <stream> --base @ --no-cd`, run from
`main/`. Never omit `--base`, which defaults to the repository's default
branch.

## Inspect workspace identity

```bash
wb-workspace env      # WORKSPACE_PROJECT/STREAM/ID/PRIMARY/PATH, COMPOSE_PROJECT_NAME
```

## Project setup

New streams get it automatically: Worktrunk's pre-start hook runs
`wb-workspace setup`.
- Rerun it only to refresh the generated config deliberately.
- In a primary checkout, run it once by hand (no hook runs there).

Orrery's generated files (Orrery-specific):

```bash
cat .env.workspace               # identity + this checkout's ports and URLs (no secrets)
cat docker-compose.override.yml  # Compose project name (+ side-stream web port)
wb-workspace setup --link-env    # side stream only, if it needs the primary's .env secrets
```

## Dependencies and runtime

Projects declare their runtime in tracked mise config, and workstation shells
honour it when you enter the checkout. Orrery declares Node 20 in its root
`mise.toml`, so in any Orrery checkout or worktree:

```bash
node --version        # v20.x
npm ci
npm run build
```

Diagnosing a long-lived or non-interactive process that started with a fixed
`PATH` elsewhere? Compare `node --version` with `mise current node`.

## Run Docker services

```bash
docker compose up -d
docker compose ps
```

In an integrated project like Orrery, Compose picks up the generated project
name and override from the checkout automatically. Don't set
`COMPOSE_PROJECT_NAME` by hand.

Orrery: run `npm run build` in this checkout before starting `web`.

## Ports

```bash
wb-workspace port <slot>                  # deterministic port for this checkout
wb-workspace port --require-free <slot>   # fail if something already listens there
grep PORT .env.workspace                  # Orrery: the ports this checkout actually uses
```

- **Orrery primary:** keeps its defaults (web on 8080).
- **Side streams:** get their own derived ports. Read them from
  `.env.workspace`; don't memorise them.

## Several streams at once

- The primary checkout and its side streams can run at the same time.
- Containers talk to each other by Compose **service name**.
- Host `localhost` ports differ per stream; never assume another stream's port.

## Integrate side work

**⚠️ Never use bare `wt merge` here. It merges into the repository's default
branch, which is not necessarily the branch the primary checkout is on.**
Always name the intended primary working branch:

```bash
git -C /work/orrery/main branch --show-current   # the primary branch, e.g. map-redesign
cd /work/orrery/worktrees/feature-x
wt merge map-redesign                            # explicit target = the primary branch
```

By default `wt merge` squashes, rebases, and removes the worktree afterwards.
`wt merge --help` lists `--no-squash`, `--no-remove`, and the others.

## Remove a side stream

```bash
cd /work/orrery/main
wt remove feature-x                         # branch name; pre-remove runs the project teardown
tmux kill-window -t '=orrery:feature-x'     # if its window is still open (wt doesn't close it)
```

Never `rm -rf` a worktree directory.

## Docker safety

| Safe, in the current checkout | Never |
|---|---|
| `docker compose ps` | `docker system prune -a` |
| `docker compose logs` | `docker volume prune` |
| `docker compose up -d` | any global cleanup that reaches other projects or agents |
| `docker compose down` | |

## SSH agent after a reboot

Once after each boot, after the LUKS unlock and your first login:

```bash
ssh-add ~/.ssh/id_ed25519     # asks for the key's passphrase
ssh-add -l                    # check
```

## tmux keys

The prefix is **Ctrl+Space** (Omarchy).

| Keys | Action |
|---|---|
| Ctrl+Space `c` | new window (in the current directory) |
| Ctrl+Space `,` | rename window |
| Ctrl+Space `n` / `p` | next / previous window |
| Ctrl+Space `d` | detach (the session keeps running) |

## Recovery

| Situation | Do |
|---|---|
| `wb-stream` created the worktree but tmux failed | Keep it. Run the recovery command `wb-stream` printed (open the window, or `wt remove` it). |
| Setup hook failed | The worktree is kept on purpose. Fix the cause and rerun `wb-workspace setup` in it, or remove it with `wt remove`. |
| Teardown hook failed | Removal is blocked on purpose. Fix the teardown. Use `wt remove --no-hooks <branch>` only when you understand what runtime state is left behind. |
| Port in use / collision | Stale or unwanted host listener: stop it. Genuine allocation collision: stop and resolve it explicitly. Don't pick a different port behind `wb-workspace`'s back; it never does that itself, and no further resolution policy is defined yet. |
| Long-lived process shows an unexpected Node version | Compare `node --version` with `mise current node`; the process may have a fixed `PATH` from elsewhere. |
| Orrery Docker `web`: bind source path does not exist | Build that checkout first: `npm run build`. |
