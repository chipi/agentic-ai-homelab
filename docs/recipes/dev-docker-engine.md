# Dev Docker engine on the mini

## Why this exists

The mini's main Docker engine is **production** (observability, delivery, LiteLLM,
Langfuse, GlitchTip). Development work there preceded two production outages, so it
is closed to development ([ADR-0009](../adr/ADR-0009-on-demand-dev-docker-engine.md)).
Development gets its own engine: a separate VM that is **off unless someone needs
it**, because production shares this machine's 32 GiB.

## Quick reference

```sh
devengine start                  # ~1 min cold; refuses if the host is short of memory
docker --context dev ps          # or: docker context use dev
devengine status                 # running/stopped + what is in it
devengine stop                   # when you are done
```

| | Dev engine | Production engine |
|---|---|---|
| Socket | `/var/run/docker-dev.sock` (`root:staff 0660`) | `/var/run/docker.sock` (`root:admin 0660`) |
| Docker context | `dev` (created by `devengine start`) | none — not for development |
| VM | `_dockerdev`, vz + virtiofs, 4 CPU / 6 GiB / 60 GiB | `_dockerhost`, qemu, 20 GiB |
| Lifetime | on demand; stops itself after 30 min idle | always on |

## Which engine am I talking to?

Every `docker` command on the mini goes to production unless it names the dev engine. The CLI
picks the engine from, in this order: `-H`/`--host`, `DOCKER_HOST`, `--context`,
`DOCKER_CONTEXT`, then the current context (`docker context show`; on the operator's account it
is `default`, which is **production**).

| Check | Dev | Production |
|---|---|---|
| `docker context inspect <context> --format '{{.Endpoints.docker.Host}}'` | `unix:///var/run/docker-dev.sock` | `unix:///var/run/docker.sock` |
| `docker context show` | `dev` | `default` |
| in the command | `--context dev`, `DOCKER_CONTEXT=dev` | anything else, including nothing |

`docker info --format '{{.Name}}'` does not tell them apart: both VMs answer `colima`.

- **Name the engine in the command itself** (`docker --context dev …`, or `D="docker --context
  dev"; $D …`). Don't rely on `docker context use dev` from an earlier command: another session or
  a new shell is back on `default`.
- **The ask guard knows the difference** (`workstation/claude/hooks/command-ask-guard.sh`,
  2026-11-26). A `compose down -v` or `docker volume rm` that names only the dev engine runs
  without a prompt. The same command on production, or with any other `--context`,
  `DOCKER_HOST` or `-H` in it, asks the operator. Prunes ask on every engine.
- **Production's files are read by `_dockerhost`, not by you.** A bind mount from a mode-700
  folder of the operator's (`~/flotilla/config`, `~/.config/...`) is unreadable inside a
  production container, even with `--user $(id -u)`. Pass secrets on stdin instead (`… | docker
  run -i … sh -c 'cat > /s/token'`, or `tar -cf - … | docker run -i --tmpfs /w …`), as
  infra/second-brain and flotilla's `secrets.sh` do (2026-11-26).
- **A script pins its engine.** The backup dump of 2026-11-21 read "SKIP" for every database
  because its CLI fell back to another socket. Scripts that must reach production set
  `DOCKER_HOST=unix:///var/_dockerhost/.colima/default/docker.sock` and fail loudly if `docker ps`
  errors (`infra/backup/dump-observability-dbs.sh`).
- **Other hosts:** the X3's CI runners each have their own rootless engine
  (`docker@<repo>-<n>`, user `gh-runner`, ADR-0015), apart from the X3's system engine. The DGX
  has one engine, shared by prod vLLM and robotics: change it only through `gpu-mode-swap.sh`.

## The contract

1. **Use the `dev` context only.** Never the production socket, never `DOCKER_HOST`
   pointing at it.
2. **Cap memory on every container** (`--memory 2g`, or `mem_limit:` in compose).
   The whole engine has 6 GiB.
3. **One image build at a time.** Check `devengine status` first if others may be
   working.
4. **Name compose projects after your worktree** (`-p <worktree>`), and don't publish
   fixed host ports other agents may also use; prefer `127.0.0.1:0:<port>` or a
   per-worktree offset.
5. **Prefer named volumes** for large data. `/Users` is mounted (virtiofs) for bind
   mounts, but files keep their macOS owner: containers can read your worktree, and
   writing into it may fail.
6. **Tear down what you start** (`docker compose -p <worktree> down`). Volumes are
   yours to remove.
7. **The engine is disposable.** It may be stopped, pruned or recreated at any time.
   Nothing in it is backed up. Week-old containers, images and build cache are
   pruned when it idles out; volumes are not.
8. **Stop it when you are done** (`devengine stop`). The idle job is the backstop,
   not the plan.

## Steps

1. `devengine start`. The first start ever creates the VM (a few minutes).
2. Work with `docker --context dev …`.
3. `devengine stop`.

## Verification

- `devengine status` prints `dev engine: RUNNING` and the containers.
- `docker --context dev info --format '{{.Name}}'` answers (the VM's hostname).
- `docker --context dev run --rm alpine true` exits 0.

## Troubleshooting

- **`EOF` or `connection refused` on `--context dev`:** the engine is stopped.
  `devengine start`.
- **`NOT started — host memory free is N%`:** production needs the memory right now.
  Try later, or ask the operator.
- **`permission denied` on `/var/run/docker.sock`:** that is production; use
  `--context dev`.
- **`sudo: a password is required`:** the account is not in `staff`, or the sudoers
  rule is missing (`infra/mini-dev-engine-setup.sh`).
- **Logs:** `/tmp/devengine-idle.log` (idle stops), `/tmp/docker-dev-relay.log`
  (socket relay), `colima` output from `devengine start` itself.

## Operator notes

- Install or repair: `sudo bash infra/mini-dev-engine-setup.sh` (idempotent; the
  undo steps are in its header). It never touches the production engine.
- Resize: as `_dockerdev`, `colima stop`, edit `/var/_dockerdev/.colima/default/colima.yaml`,
  `colima start` — and update the spec in `infra/engine/dev/devengine-colima`.
- When development leaves the mini, repoint the context:
  `docker context create dev --docker host=ssh://<new host>`; the contract stays.
