# The X3 prod engine (robotics-lab)

robotics-lab's prod stack runs on its own Docker engine on the X3, behind a wall: its own
containerd and dockerd, a socket only the service user `robotics` can open, and one
sudoers-allowed deploy script. Why: [ADR-0013](../adr/ADR-0013-x3-prod-docker-engine.md).

## For agents: the rules

- **Never touch prod except through `sudo -n robotics-prod-deploy …`.** There is no `prod`
  context for the operator's uid. The socket is `root:robotics 0660`, so `docker -H
  unix:///run/docker-prod.sock` fails, and it is meant to.
- **`status` and `smoke` are reads:** run them when you need to know what prod runs.
- **`up` and `rollback` change prod:** only with the operator's go for that deploy, after a
  green test stack on the dev engine (`default`/`dev` context).
- **Never write under `/srv/robotics-lab` or `/var/lib/docker-prod`,** and never point a test
  at prod's data. Test stacks keep their own folders (`~/.cache/robotics-lab-tests`).
- **Don't build images on the prod engine before the X3 maintenance window** (the containerd
  fault, `docs/wip/NEXT_STEPS.md`). The first `up` builds, so it waits too.

## The deploy script's interface

`/usr/local/libexec/robotics-prod-deploy`, root-owned, allowed for `marko` by
`/etc/sudoers.d/robotics-prod`:

| Call | What it does |
| --- | --- |
| `sudo robotics-prod-deploy up` | deploy the head of GitHub's `main` |
| `sudo robotics-prod-deploy up <40-hex sha>` | deploy that commit; refused unless it is on GitHub's `main` |
| `sudo robotics-prod-deploy rollback` | deploy the commit recorded before the current one |
| `sudo robotics-prod-deploy smoke` | the smoke, without the browser |
| `sudo robotics-prod-deploy status` | what is recorded, what runs |

Anything else exits 2 with a usage line. Each call takes a lock and is logged to the journal
(`journalctl -t robotics-prod-deploy`).

What it runs, which is what robotics-lab's `scripts/deploy.py` has to accept:

```text
cd /srv/robotics-lab/home
runuser -u robotics -- env -i HOME=/srv/robotics-lab/home PATH=/usr/local/bin:/usr/bin \
  LANG=C.UTF-8 TMPDIR=/srv/robotics-lab/home/tmp DOCKER_CONTEXT=prod PYTHONDONTWRITEBYTECODE=1 \
  GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=safe.directory GIT_CONFIG_VALUE_0=/srv/robotics-lab/checkout \
  python3 /srv/robotics-lab/checkout/scripts/deploy.py <verb> --context prod \
    --data /srv/robotics-lab/data \
    --viewer-state /srv/robotics-lab/state/observatory \
    --control-state /srv/robotics-lab/state/mission-control \
    --deploy-state /srv/robotics-lab/state/deploy \
    --installation /etc/robotics-prod/installation.json \
    [--commit <sha>]  [--no-browser]   # --commit for up; --no-browser for up, rollback, smoke
```

- `/srv/robotics-lab/checkout` is a root-owned clone of `https://github.com/chipi/robotics-lab`,
  fetched on every call and checked out at `origin/main`, so the `deploy.py` that runs is
  always main's. It exports the commit it deploys with `git archive`.
- The `prod` context exists in `robotics`'s Docker config and points at
  `unix:///run/docker-prod.sock`. `DOCKER_CONTEXT=prod` is set as well as `--context prod`.
- The containers run as `robotics` (`deploy.py` uses its own UID), which owns `data`,
  `data-archive` and `state`. `data-archive` is created; nothing passes it yet.
- `/etc/robotics-prod/installation.json` is robotics-lab's to supply (`root:robotics 0640`;
  the operator puts it there).
- The browser part of the smoke: run it as the operator against 127.0.0.1, as robotics-lab's
  own target. It needs no engine access.

## For the operator: the one root step

On the X3, from the deploy checkout (`git -C ~/deploy/agentic-ai-homelab pull --ff-only` first):

```bash
sudo bash ~/deploy/agentic-ai-homelab/infra/x3/x3-prod-engine-setup.sh
```

The first run creates `@docker-prod` and `@robotics-prod` and stops with exit 3, printing two
fstab lines (from `wb-storage fstab --prod`; the script never edits `/etc/fstab`). Add them by
hand, then:

```bash
sudo mkdir -p /var/lib/docker-prod /srv/robotics-lab
sudo systemctl daemon-reload
sudo mount /var/lib/docker-prod && sudo mount /srv/robotics-lab
sudo bash ~/deploy/agentic-ai-homelab/infra/x3/x3-prod-engine-setup.sh
```

The second run creates the `robotics` user and the folders, installs the config, units, script
and sudoers rule (validated with `visudo -cf`), starts both units and checks:

- both units active;
- the prod engine's data root is `/var/lib/docker-prod/docker`, with the containerd image store;
- `ctr -a /run/containerd-prod/containerd.sock namespaces ls` shows `moby`;
- the socket is `root:robotics 660`, and the operator's uid cannot open it;
- prod has no bridge network (`host`, `none` only);
- the iptables rules did not change when the engine started;
- the system engine's data root is still `/var/lib/docker`.

It ends with `== done: PASS` or `FAIL`. Undo: the script's header lists what to remove.

## Not covered

- None of this has run as root: the files were tested as a normal user only
  (`infra/x3/prod-engine/prod-engine.test.sh`, the daemons' own config validation,
  `systemd-analyze verify`, `visudo -cf`). How the two containerds behave side by side under load
  has not been measured.
- `deploy.py --context prod` does not exist yet (robotics-lab's change). Until it does, every
  verb fails at argument parsing.
- A robot's gate socket that the installation file names has to be reachable by `robotics`
  (its UID runs Mission Control). If the gate's socket is the operator's, mode 0600, the
  container cannot connect. That is robotics-lab's to settle with the installation file.
- `robotics-lichtblick` stays on the system engine.
- No `command-ask-guard` pattern holds `up` and `rollback` yet; the rule above does.
- Backups of `/srv/robotics-lab` are not set up (the backup proposal is parked for the operator).
