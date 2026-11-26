# ci-runner: self-hosted GitHub Actions runners on the X3

The private repos' Actions jobs, on the X3 instead of GitHub's paid runners
([ADR-0015](../../../docs/adr/ADR-0015-x3-github-actions-runners.md)). They move to the CI mini PC
when it arrives.

| Piece | What it does |
|---|---|
| `../x3-ci-runner-setup.sh` | as root, once: the packages, the `gh-runner` user, the cap, its rootless engine, a smoke test |
| `docker@.service` | one rootless Docker engine per runner (user unit), e.g. `docker@closelistening-studio-1`; publishes no port on the X3 |
| `ci-runner@.service` | one runner container per instance (user unit), e.g. `ci-runner@closelistening-studio-1` |
| `Dockerfile` | the runner image: GitHub's `actions-runner` plus the tools GitHub's VMs have and it lacks (make, gcc, zstd …); each engine builds it on its first start |
| `entrypoint.sh` | inside the container: restore or make the registration, then run |
| `register.sh` | as root, per runner: write its settings, hand it a registration token, start it |
| `dockerd-rootless.sh` | Docker's own script, moby `docker-v29.7.2`, checksum-pinned in the setup |

## Install

```bash
# 1. once (from the deploy checkout, after it pulled main)
sudo bash ~/deploy/agentic-ai-homelab/infra/x3/x3-ci-runner-setup.sh        # ends SETUP PASS
# 2. per runner: an agent writes a registration token (valid one hour) to a mode-600 file
gh api -X POST repos/chipi/<repo>/actions/runners/registration-token -q .token > <file>
sudo bash ~/deploy/agentic-ai-homelab/infra/x3/ci-runner/register.sh <repo> 1 <file>   # ends REGISTER PASS
# 3. the repo's workflows: runs-on: [self-hosted, x3]
```

## Operate

- Status: `sudo systemctl --user -M gh-runner@ status 'ci-runner@*'`; the runner's log:
  `sudo -u gh-runner env XDG_RUNTIME_DIR=/run/user/$(id -u gh-runner) DOCKER_HOST=unix:///run/user/$(id -u gh-runner)/e-<instance>/docker.sock docker logs ci-runner-<instance>`.
- The cap: `systemctl show user-$(id -u gh-runner).slice -p CPUQuotaPerSecUSec -p MemoryMax`.
- A new runner image: change the `FROM` in `Dockerfile` and the tag in `IMAGE` (`ci-runner@.service`), then
  rerun the setup; it restarts the instances and each engine builds the new tag on its next start. A
  changed Dockerfile needs a new tag too, or the engines keep the image they built.
- The runner does not update itself (`--disableupdate`); GitHub refuses runners that fall too far
  behind, so bump the image when it says so.

## Not covered

- Ephemeral registration: each job gets a fresh container, but the runner keeps its registration (a token that may register runners would allow true ephemeral runners). Between a job's end and the restart (about 2 s) the runner could take another job; that job would then be cut off.
- Disk use: each runner's engine keeps its own images (`~gh-runner/.local/share/docker-<runner>`); nothing prunes them yet.
- Docker-based actions (`uses: docker://…`, a Dockerfile action) mount the work folder by host path,
  which this layout does not provide. None of closelistening-studio's jobs use one.
- No metrics or alert on the runners yet.
