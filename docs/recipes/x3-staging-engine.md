# The X3 staging engine (robotics-lab)

robotics-lab's staging stack runs on its own Docker engine on the X3: its own containerd and
dockerd, a socket only the service user `robotics` can open, and one sudoers-allowed deploy
script. Why: [ADR-0013](../adr/ADR-0013-x3-staging-docker-engine.md).

The separation stops accidents: a prune, a `down`, a rebuild or a port clash on the system
engine. It is not a security boundary while the operator's uid is in `docker`, because
`docker run -v /:/host` on the system socket is root. The rules below are what keep agents off
staging (ADR-0013, Consequences).

## For agents: the rules

- **Never touch staging except through `sudo -n robotics-staging-deploy …`.** There is no `staging`
  context for the operator's uid. The socket is `root:robotics 0660`, so `docker -H
  unix:///run/docker-staging.sock` fails, and it is meant to.
- **`status` and `smoke` are reads:** run them when you need to know what staging runs.
- **`up`, `rollback` and `stop` change staging:** only with the operator's go for that deploy,
  after a green test stack on the dev engine (`default`/`dev` context).
- **Never write under `/srv/robotics-lab` or `/var/lib/docker-staging`,** and never point a test
  at staging's data. The one exception is the host's recorders, which write runs into
  `/srv/robotics-lab/data` through the group `robotics-data`. An agent never deletes or rewrites
  a run there. Test stacks keep their own folders (`~/.cache/robotics-lab-tests`).
- **Don't build images on the staging engine before the X3 maintenance window** (the containerd
  fault, `docs/wip/NEXT_STEPS.md`). The first `up` builds, so it waits too.

## The deploy script's interface

`/usr/local/libexec/robotics-staging-deploy`, root-owned, allowed for `marko` by
`/etc/sudoers.d/robotics-staging`:

| Call | What it does |
| --- | --- |
| `sudo robotics-staging-deploy up` | deploy the head of GitHub's `main` |
| `sudo robotics-staging-deploy up <40-hex sha>` | deploy that commit; refused unless it is on GitHub's `main` |
| `sudo robotics-staging-deploy rollback` | deploy the commit recorded before the current one |
| `sudo robotics-staging-deploy smoke` | the smoke, without the browser |
| `sudo robotics-staging-deploy status` | what is recorded, what runs |
| `sudo robotics-staging-deploy stop` | stop the stack, keep its containers (frees the host's ports for a rollback to the shared engine) |

Anything else exits 2 with a usage line. Each call takes a lock and is logged to the journal
(`journalctl -t robotics-staging-deploy`).

What it runs, which is what robotics-lab's `scripts/deploy.py` has to accept:

```text
cd /srv/robotics-lab/home
runuser -u robotics -- env -i HOME=/srv/robotics-lab/home PATH=/usr/local/bin:/usr/bin \
  LANG=C.UTF-8 TMPDIR=/srv/robotics-lab/home/tmp DOCKER_CONTEXT=staging PYTHONDONTWRITEBYTECODE=1 \
  GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=safe.directory GIT_CONFIG_VALUE_0=/srv/robotics-lab/checkout \
  python3 /srv/robotics-lab/checkout/scripts/deploy.py <verb> --context staging \
    --data /srv/robotics-lab/data \
    --viewer-state /srv/robotics-lab/state/observatory \
    --control-state /srv/robotics-lab/state/mission-control \
    --deploy-state /srv/robotics-lab/state/deploy \
    --installation /etc/robotics-staging/installation.json \
    [--commit <sha>] [--robots-dir /srv/robotics-lab/robots] [--no-browser]
    # --commit: up; --robots-dir: up, rollback; --no-browser: up, rollback, smoke
```

- `/srv/robotics-lab/checkout` is a root-owned clone of `https://github.com/chipi/robotics-lab`,
  fetched by `up` and checked out at `origin/main`, so the `deploy.py` that runs is main's as
  of the last `up`. It exports the commit it deploys with `git archive`.
- The `staging` context exists in `robotics`'s Docker config and points at
  `unix:///run/docker-staging.sock`. `DOCKER_CONTEXT=staging` is set as well as `--context staging`.
- The containers run as `robotics` (`deploy.py` uses its own UID), which owns `robots` and
  `state`. `data` and `data-archive` are `robotics:robotics-data` 2770 (setgid), with default
  ACLs that keep new files group-writable: the host's recorders write runs there as the operator,
  who is in `robotics-data` (never in `robotics`). `data-archive` is created; nothing passes it
  yet. Content copied in from elsewhere needs `chgrp -R robotics-data`, `chmod -R g+rwX`, and
  `setfacl -R -d -m g::rwx` on its folders. `cp -a` keeps the old group and modes.
- `/srv/robotics-lab/robots` is the robots folder the Observatory mounts (`--robots-dir`):
  `robots/` plus the generated meshes, which are not in git, so the clone has none.
  robotics-lab's cut-over fills it.
- `/etc/robotics-staging/installation.json` is robotics-lab's to supply (`root:robotics 0640`;
  the operator puts it there).
- The browser part of the smoke: run it as the operator against 127.0.0.1, as robotics-lab's
  own target. It needs no engine access.

## For the operator: the one root step

On the X3, one block, pasted into a terminal (sudo asks for the password once):

```bash
D=~/deploy/agentic-ai-homelab
git -C "$D" pull --ff-only
sudo bash "$D/infra/x3/x3-staging-engine-setup.sh"            # 1st run: creates the subvolumes, exits 3
"$D/workstation/storage/wb-storage" fstab --staging           # read the two lines it adds
sudo cp -a /etc/fstab /etc/fstab.pre-staging-engine
"$D/workstation/storage/wb-storage" fstab --staging | grep -v '^#' | sudo tee -a /etc/fstab >/dev/null
sudo mkdir -p /var/lib/docker-staging /srv/robotics-lab
sudo systemctl daemon-reload
sudo mount /var/lib/docker-staging && sudo mount /srv/robotics-lab
findmnt /var/lib/docker-staging /srv/robotics-lab             # SOURCE ends in [/@docker-staging], [/@robotics-staging]
sudo bash "$D/infra/x3/x3-staging-engine-setup.sh"            # 2nd run: must end "== done: PASS"
```

The script itself never edits `/etc/fstab`; the `tee -a` line in this block is yours (as in
the [storage runbook](x3-storage-separation.md)). The fstab rollback is `sudo cp -a
/etc/fstab.pre-staging-engine /etc/fstab`.

The second run creates the `robotics` user and the folders, installs the config, units, script
and sudoers rule (validated with `visudo -cf`), starts both units and checks:

- both units active;
- the staging engine's data root is `/var/lib/docker-staging/docker`, with the containerd image store;
- the staging containerd answers on its own socket (`ctr -a /run/containerd-staging/containerd.sock version`);
- the socket is `root:robotics 660`, and the operator's uid gets "permission denied" on it;
- staging's content store has btrfs compression off;
- staging has no bridge network (`host`, `none` only);
- the iptables rules did not change when the engine started;
- the system engine's data root is still `/var/lib/docker`;
- `data` and `data-archive` are `robotics:robotics-data` 2770 with a group-writable default ACL;
- the operator is in `robotics-data` and not in `robotics` (the new group counts from a new login).

It ends with `== done: PASS` or `FAIL`. Undo: the script's header lists what to remove.

## Not covered

- The engine ran its setup checks on the X3 (2026-11-24) but has run no stack yet. How the two
  containerds behave side by side under load has not been measured.
- A robot's gate socket that the installation file names has to be reachable by `robotics`
  (its UID runs Mission Control). If the gate's socket is the operator's, mode 0600, the
  container cannot connect. That is robotics-lab's to settle with the installation file.
- `robotics-lichtblick` stays on the system engine.
- Whether the two containerds share the shim and runc folders (`/run/containerd/s`,
  `/run/containerd/runc/moby`). No collision is expected: container ids are unique and the shim's
  socket name hashes the containerd address. After the first start, `sudo ls /run/containerd/s
  /run/containerd-staging` shows which one they use.
- `rollback`, `smoke` and `status` use the checkout as last fetched; only `up` fetches. So a
  rollback works during a GitHub outage, but runs main's `deploy.py` as of the last `up`.
- No `command-ask-guard` pattern holds `up` and `rollback` yet; the rule above does.
- Backups of `/srv/robotics-lab` are not set up yet: the operator chose an age-encrypted nightly
  of the state plus restic off-site for the data, on the Hetzner Storage Box (2026-11-24; plan in
  `docs/wip/NEXT_STEPS.md`).
