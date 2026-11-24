# ADR-0013 — A prod Docker engine on the X3 for robotics-lab, behind a wall agents cannot cross

**Status:** Proposed (2026-11-24). The files are written and tested as a normal user; nothing
is installed. The operator runs the one root step ([recipe](../recipes/x3-prod-engine.md)).
Image builds on the new engine wait for the X3 maintenance window (the containerd content-store
fault, `docs/wip/NEXT_STEPS.md`).
**Date:** 2026-11-24

## Context

robotics-lab's deployed stack (the Observatory and Mission Control) runs on the X3, on the one
Docker engine everything else uses: Docker 29.7.2, the system `dockerd` on the system
`containerd` (v2.3.5), data in `@docker` and `@containerd` (ADR-0011). The `default` and `dev`
contexts both point at that socket. Test stacks, the eval harness and every session's ad-hoc
containers share it, so a `compose down`, a prune or a rebuild under a reused tag from any
session lands on prod. Nothing separates prod from test except a project name.

Two facts shaped the decision:

- **Docker 29 keeps images in containerd's content store.** A second `dockerd` on the shared
  containerd, even in its own namespace, would not separate images. It would also share the
  X3's open containerd fault (fs-verity read errors in the content store).
- **Every agent on the X3 runs as the operator's uid** (`marko`, in `docker` and `wheel`). A
  socket or a folder the operator owns keeps no agent out.

robotics-lab's proposal (`mission-control/docs/wip/PROD-ON-X3.md` in chipi/robotics-lab) set
out four options. On 2026-11-24 the operator chose A, a second rootful engine, with its own
containerd and a wall, after the homelab's review.

## Decision

1. **Prod gets its own containerd and dockerd** as system units, `containerd-prod.service`
   and `docker-prod.service` (`infra/x3/prod-engine/`). Every path differs from the system
   engine's:

   | | System engine | Prod engine |
   | --- | --- | --- |
   | containerd root, state, socket | `/var/lib/containerd`, `/run/containerd` | `/var/lib/docker-prod/containerd`, `/run/containerd-prod` |
   | dockerd data root, exec root | `/var/lib/docker`, `/run/docker` | `/var/lib/docker-prod/docker`, `/run/docker-prod` |
   | Socket | `/run/docker.sock`, `root:docker` | `/run/docker-prod.sock`, `root:robotics 0660` |
   | Config | `/etc/docker/daemon.json` (`bip`, `dns`) | `/etc/docker-prod/daemon.json`, `/etc/containerd-prod/config.toml` |

   The prod `dockerd` runs with `bridge: none`, `iptables: false`, `ip6tables: false`,
   `ip-forward: false` and `ip-masq: false`. robotics-lab runs every prod service with
   `network_mode: host` on 127.0.0.1, so the engine needs no bridge and no NAT. It never writes
   a firewall rule, so two daemons never fight over iptables. CRI is disabled in the prod
   containerd.

2. **Two new subvolumes**, top-level siblings of `@` like ADR-0011's, outside Snapper's root
   rollback domain:
   - `@docker-prod` → `/var/lib/docker-prod` (prod's images, containers, volumes);
   - `@robotics-prod` → `/srv/robotics-lab` (prod's `data`, `data-archive`, `state`, the
     service user's home and the deploy checkout).

   `wb-storage fstab --prod` prints their entries. `wb-storage status` does not ask for them:
   they belong only on a machine that runs the prod engine. Both units have
   `RequiresMountsFor=` on them, so the engine never starts against an empty folder on `@`.
   `/srv` was chosen over the proposal's `~/prod`: a service user owns the data, and `@home` is
   the operator's.

3. **The wall.** A system user `robotics` (no login, not in `docker` or `wheel`) owns prod's
   data and is the only non-root account that can open the prod socket. The operator's uid
   reaches prod through one script, `/usr/local/libexec/robotics-prod-deploy` (root, 755),
   allowed by `/etc/sudoers.d/robotics-prod` with four verbs: `up [<40-hex commit>]`,
   `rollback`, `smoke`, `status`. The script:
   - fetches `https://github.com/chipi/robotics-lab` (public) into a **root-owned** checkout,
     `/srv/robotics-lab/checkout`. The proposal named `~/deploy/robotics-lab`, but that
     checkout is writable by every agent, and root would then run whatever an agent wrote into
     it. Only commits on GitHub's `main` can be deployed: `up` refuses a commit that is not an
     ancestor of `origin/main`;
   - runs `scripts/deploy.py <verb> --context prod` from that checkout **as `robotics`**,
     with the environment cleared. `deploy.py` gives the containers its own UID, so prod's
     containers run as `robotics`, not as root and not as the operator;
   - passes prod's paths itself (`--data`, `--viewer-state`, `--control-state`,
     `--deploy-state`, `--installation /etc/robotics-prod/installation.json`) and
     `--no-browser`. The browser part of the smoke needs no engine access and runs as the
     operator against 127.0.0.1;
   - holds a lock (one deploy at a time) and logs each call with the sudo user to the journal
     (`journalctl -t robotics-prod-deploy`).

4. **The X3's "user units only" rule gets one written exception**: these two system units, the
   script and the sudoers rule (`infra/x3/AGENTS.md`). The setup script
   (`infra/x3/x3-prod-engine-setup.sh`) is the operator's to run as root, like the mini's
   `mini-dev-engine-setup.sh`.

## Consequences

- A prune, `compose down`, rebuild or port clash on the system engine cannot touch prod's
  images, containers or volumes, and the X3's containerd fault stays on the system store.
- Agents can read prod only through the script's `status` and `smoke`. They cannot open the
  socket or write prod's data. With `NOPASSWD`, any agent can also run `up` or `rollback`. The
  rule "prod changes only with the operator's go" is held by the agents' rules (the recipe)
  and, if the operator wants it, a `command-ask-guard` pattern for those two verbs.
- Membership in `robotics`, or the prod socket, is root-equivalent, as with any Docker socket.
  That is why the group has one member, a user nobody logs in as. It also means a commit on
  robotics-lab's `main` is code that runs with root's reach on the X3, so the wall is only as
  strong as who may push to that `main`.
- About 1 GB of duplicated images (the prod builds), on `@docker-prod`.
- `deploy.py` needs `--context prod` (robotics-lab's change); the script's interface is in
  the recipe.
- Rollback of this decision: stop and disable the two units, remove the installed files
  (the setup script's header lists them). Prod's data stays on `@robotics-prod` until the
  operator removes it.

## Alternatives considered

- **A second `dockerd` on the shared containerd, in its own namespace** (the proposal's first
  draft). Rejected: Docker 29's images live in containerd's content store, so they would not
  be separated, and prod would share the content-store fault.
- **Rootless Docker for prod.** Fits "user units only", but needs a new package, and rootless
  "host" networking is rootlesskit's namespace: the navigator on the host's 127.0.0.1 would
  need a code change.
- **No engine: user units from `~/deploy` venvs.** Fits the X3 rules exactly, but rewrites the
  deploy and loses the pinned image; a user unit runs as the operator, so no wall.
- **Same engine, rules only.** No cost and no protection.
- **The deploy script running from `~/deploy/robotics-lab`.** Rejected inside A: a root
  script must not run code from a tree the operator's uid can write.

## References

- [ADR-0009](ADR-0009-on-demand-dev-docker-engine.md) (the mini's split, which this mirrors
  the other way round: there dev got the new engine), [ADR-0011](ADR-0011-workstation-storage-subvolumes.md)
  (the subvolume layout).
- [Recipe: the X3 prod engine](../recipes/x3-prod-engine.md).
- `infra/x3/prod-engine/` and `infra/x3/x3-prod-engine-setup.sh`; tests:
  `infra/x3/prod-engine/prod-engine.test.sh`, `workstation/storage/wb-storage.test.sh`.
