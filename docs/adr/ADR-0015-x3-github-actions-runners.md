# ADR-0015 — The private repos' GitHub Actions run on self-hosted runners, rootless, on the X3 first

**Status:** Accepted (2026-11-25, operator); being built, one repo as the test.
**Date:** 2026-11-25

## Context

GitHub Actions on the private repos costs the operator about $100 a month (operator, 2026-11-25).
In November the runs were mostly test suites. Wall-clock minutes from 2026-11-01 to 11-25, from
`gh api repos/chipi/<repo>/actions/runs` (billed minutes are higher: parallel jobs bill separately):

| Repo | Wall-clock minutes | Mostly |
|---|---|---|
| closelistening-player | ~4,600 | Tests |
| closelistening-common | ~3,500 | Tests |
| infra | ~2,300 | production drills, backups, deploys |
| closelistening-integration | ~1,500 | Integration |
| closelistening-studio | ~430 | Tests |

Self-hosted runners use no GitHub-hosted minutes. GitHub announced a per-minute platform fee for
self-hosted runners on private repos and then postponed it; where that stands was not checked.

The operator plans to buy mini PCs (one for CI, one for staging, one for services; the comparison
is on the [Homelab Mini PCs artifact](https://claude.ai/artifact/6XWwTaRr3hpVek9axcfiov)). Until then the
runners live on the X3, and move to the CI box when it arrives.

`chipi` is a personal account, not an organization. GitHub registers runners on a repository, an
organization or an enterprise, not on a personal account: each repo gets its own runners.

## Decision

1. **A service user `gh-runner`**, no login shell, not in the `docker` group.
2. **Its own rootless Docker engine** (Arch's `rootlesskit` and `slirp4netns`, Docker's
   `dockerd-rootless.sh` at the engine's version, checksum-pinned). A job that misbehaves is
   gh-runner on the X3, not root: the operator's `docker` group is root, and the staging engine of
   ADR-0013 is root too. The engine publishes no port on the X3 (`PORT_DRIVER=none`) and cannot
   reach the X3's loopback.
3. **Each runner is a container** of GitHub's own image (`ghcr.io/actions/actions-runner`, Ubuntu
   24.04, pinned), so jobs written for `ubuntu-latest` find what they expect. Its registration lives in
   a volume; its work folder and anything a job installs go with the container.
4. **One cap for all of it**: gh-runner's user slice gets 8 cores and 32 GB. CI never starves the
   operator's sessions or robotics-lab (on 2026-11-24 an unbounded test run of eval-harness did).
5. **Jobs that hold production credentials stay on GitHub's runners**: `infra`'s deploys,
   backups and drills. A workstation runner holds no production secret.
6. **One repo at a time**, starting with closelistening-studio (the smallest of the test suites). A
   repo moves by changing `runs-on: ubuntu-latest` to `runs-on: [self-hosted, x3]`, one line per job;
   its session makes the change.

## Consequences

- One runner runs one job at a time. More jobs at once means more runner instances (`register.sh
  <repo> 2`), all inside the same cap.
- **Each runner has its own rootless engine** (`docker@<runner>`), with its own network and image
  store, so two runners' jobs can each start a Postgres on 5432 (tested 2026-11-25). The first
  version shared one engine; studio, player and common all use a 5432 service, so it would have
  collided. The cost is disk: each engine pulls its own images.
- Each job gets a fresh container (a job-completed hook stops the runner, systemd starts a new one): on 2026-11-25 a job's leftover server and files broke the next job's e2e.
- The work folder is a host folder (`~gh-runner/ci-runner/work/<repo>-<n>`) mounted at the same path inside the runner container, and emptied at each container start: a job's `docker run -v <checkout>/file:…` names a path the engine, outside the container, must find (player's nginx test, 2026-11-26). `TMPDIR` points into it for the same reason: a `mktemp -d` the job mounts into `docker run` (infra's caddy check). The registration itself is kept, so the runner is not ephemeral in GitHub's sense; that needs a token that may register runners.
- Jobs run as the image's user `runner` (uid 1001, passwordless sudo), as on GitHub's VMs; the entrypoint does its set-up as root. As root, infra's read-only-folder test could not fail (2026-11-26). Each start also removes every other container on the runner's engine: a killed job's Postgres kept 5432.
- `x3-ci-runner-setup.sh` restarts only idle runners; a busy one takes the new files in the fresh container after its job.
- If the X3 is off, the jobs wait; GitHub does not fall back to its own runners.
- macOS jobs stay on GitHub.
- Never attach a runner to a public repo: a fork's pull request would run code on the X3.

## Rollback

A repo goes back with its `runs-on` line. The whole thing comes off with the undo steps in
`infra/x3/x3-ci-runner-setup.sh`.
