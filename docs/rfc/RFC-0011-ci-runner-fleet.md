# RFC-0011 — A self-hosted CI runner fleet across the homelab, with a CI view in the hub

**Status:** Accepted (2026-11-26, operator); phase A being built.
**Relates to:** [ADR-0015](../adr/ADR-0015-x3-github-actions-runners.md) (the X3 runners, the current
design), [`infra/x3/ci-runner/`](https://github.com/chipi/agentic-ai-homelab/tree/main/infra/x3/ci-runner)
and [`infra/x3/x3-ci-runner-setup.sh`](https://github.com/chipi/agentic-ai-homelab/blob/main/infra/x3/x3-ci-runner-setup.sh),
the Hub ([`infra/homelab-home/`](https://github.com/chipi/agentic-ai-homelab/tree/main/infra/homelab-home):
`gen.sh`, `hub-status.js`, `status-job.js`, the Projects tab, VictoriaMetrics behind `/vm/`),
[RFC-0009](RFC-0009-service-slos.md) (the Hub's status job and Grafana alerts),
[Dev Docker engine](../recipes/dev-docker-engine.md) (the mini's production engine is closed to development),
the DGX's GPU modes ([`infra/dgx/AGENTS.md`](https://github.com/chipi/agentic-ai-homelab/blob/main/infra/dgx/AGENTS.md),
`infra/dgx/bin/gpu-mode-swap.sh`).

## Motivation

ADR-0015 (2026-11-25) moved the private repos' test suites from GitHub's runners (about $100 a month)
to rootless runners on the X3. Eight runners are registered as of 2026-11-26, and three things are now missing.

**1. What runs where.** Ten runners, each its own rootless Docker engine plus a runner container, a fresh
container per job, all under user `gh-runner`, capped at 12 cores and 48 GB: studio-1, common-1,
player-1..5, integration-1..2, infra-1. The repos on them:

| Repo | State |
|---|---|
| studio | moved |
| common | moved (Tests) |
| player | PR #49 and #50 pending |
| integration | PR #19 pending |
| infra | PR #121 pending: `infra-quality`, `llms-txt`, `delivery-test`, `caddy-validate` only. Every job with a production secret or an environment stays on GitHub (ADR-0015 rule 5) |
| podcast_scraper | not moved, and not to be: it is public, so GitHub's runners are free there, and a self-hosted runner on a public repo is forbidden (a fork's pull request would run code on the X3) |

**2. Parity took work, and the work cost sudo.** ADR-0015 says a job written for `ubuntu-latest` finds what
it expects. On 2026-11-26 six gaps showed that this was not yet true. Each was fixed in the runner image or
the unit:

| Gap found | Fix |
|---|---|
| `make` and build tools missing | `build-essential`, `pkg-config` and others in the image |
| setup-python's prebuilt Pythons find libpython through a RUNPATH fixed at `/opt/hostedtoolcache` | `AGENT_TOOLSDIRECTORY` and `RUNNER_TOOL_CACHE` set to it, the folder created in the image |
| one job per container: a job's leftovers broke the next job; the listener ignored SIGINT; a SIGTERM after the job lost the next job it was taking | the listener runs with `--once` and exits after its job; systemd starts a fresh container |
| no Chrome | not added; lighthouse now uses Playwright's Chromium |
| no `docker compose` plugin | v5.8.0 added to the image, checksum-pinned |
| bind mounts from the checkout and from `mktemp` name host paths the engine must find | the work folder is mounted at the same path on host and in container; `TMPDIR` is inside it |

Each of these needed the operator's sudo to roll out, through `x3-ci-runner-setup.sh`, because the unit
and the image live under the service user. That is a cost per gap, and more gaps are likely as more
workflows move.

**3. Nobody can see it.** The only view of a runner is GitHub's Settings page, one repo at a time. Whether
a runner is offline, how long jobs wait, how many minutes moved off GitHub: none of it is on the Hub or in
Grafana. A dead runner shows up as a job that never starts, because GitHub does not fall back to its own
runners (ADR-0015).

Two further things follow from ADR-0015's plan: a CI mini PC is to be bought, and `runs-on: [self-hosted,
x3]` names a machine, so every workflow would need editing when the runners move. And other machines
(the DGX, the mini) could run jobs the X3 cannot (GPU, macOS).

## Proposal

Three phases, in order. Each stands alone.

### A. Observability: a collector, alerts, a CI tab, an X3 column

1. **A collector job on the mini**, built like `status-job.js`: launchd, every few minutes (5), no
   daemon. It reads the GitHub API for the private repos and writes metrics to VictoriaMetrics. It reads
   only; it changes nothing on GitHub.
   - Runners per repo (`actions/runners`): online, busy, name, labels.
   - Workflow runs and jobs (`actions/runs`, `runs/<id>/jobs`): queue wait (created to started), duration,
     conclusion, runner name, labels.
2. **Metrics** (names proposed, to be settled when built):

   | Metric | Labels | Meaning |
   |---|---|---|
   | `gh_runner_up` | repo, runner, machine | 1 if the runner is online |
   | `gh_runner_busy` | repo, runner, machine | 1 if it has a job |
   | `gh_job_queue_seconds` | repo, workflow, runner | wait before the job started |
   | `gh_job_duration_seconds` | repo, workflow, runner | run time of a finished job |
   | `gh_job_total` | repo, workflow, runner, conclusion | counter of finished jobs |
   | `gh_minutes_total` | repo, where (`self-hosted` or `hosted`) | minutes by where the job ran, from the runner labels |

   The "minutes saved" figure is `gh_minutes_total{where="self-hosted"}` at the hosted per-minute rate.
   Wall-clock minutes understate the bill (parallel jobs bill separately, ADR-0015); the tab says so.
3. **A read-only token**, fine-grained, on the private repos only: Actions read, and Administration read
   for the runners endpoint. **To be verified:** which permission the runners list needs has not been
   checked; the list above is the operator's guess. The token sits in a file on the mini, like
   `~/assistant-github-readonly.env`, and no workflow or runner ever sees it.
4. **Alerts in Grafana** (rules file beside the existing ones):
   - a runner offline for more than 15 minutes;
   - a job queued for more than 30 minutes;
   - the `gh-runner` slice at its cap (CPU or memory) for a sustained period (window to be set from a
     week of data).
   The collector also records `gh_collector_last_success_timestamp`, with a stale alert as the Hub's jobs have.
5. **The Hub:**
   - **A CI tab**: runners by machine and repo (online, busy), the queue now, recent jobs with
     conclusion and duration, failures per repo, minutes saved. Its status semantics go in `hub-status.js`
     like the rest; the page draws from them.
   - **An X3 column** beside the Mac mini and DGX columns: host stat row, the `gh-runner` slice's CPU and
     memory, its services (the runner units and their engines).
   - **Unverified:** the X3 column needs host metrics from Alloy on the X3. Whether Alloy runs on the X3
     has not been checked. If it does not, the column waits on installing it, which is a separate decision.
6. **Rollback:** unload the launchd job, delete the rules, remove the tab and column from `gen.sh`. The
   metrics age out of VictoriaMetrics. Nothing else depends on them.

### B. Capability labels instead of machine labels

7. Workflows ask for what a job needs, not which box has it. Proposed labels (exact names to decide):
   `linux-x64`, `gpu`, `macos-arm64`. A runner carries the labels its machine can honour; a workflow says
   `runs-on: [self-hosted, linux-x64]`. When the CI box arrives, its runners register with the same
   labels and no workflow changes. The X3 runners lose their machine label only when the X3 stops running
   them.
8. **Migration** from `[self-hosted, x3]`: register each runner with both labels first (`x3` stays), then
   change one repo's `runs-on` at a time (one line per job, as ADR-0015 rule 6), then drop `x3` from the
   runners when no workflow names it. A repo that still says `x3` keeps working throughout.
9. **ADR-0015 is amended** (decision 6 and the "moves to the CI box" sentence) when this phase is accepted;
   until then it is unchanged. The `gpu` and `macos-arm64` labels are not registered on any runner until phase C.
10. **Rollback:** workflows go back to `[self-hosted, x3]`; the runners still carry that label until the
    last step of item 8.

### C. Other machines, as needs arrive

11. **DGX, a GPU runner.** The single GPU is shared by production vLLM, robotics training and the rest of the
    modes. A GPU job may run only in a CI window, entered through `gpu-mode-swap.sh` like robotics is, and
    never in production hours; the nightly at 00:00Z is not displaced. The runner takes the window through
    the same script and restores the previous mode on exit; if the mode is wrong, the job does not start.
    The exact mode name (a new `ci-gpu`, or reuse of an existing one) and the window are open. The runner
    runs on the DGX's `ops` account side, not as the operator, and holds no production credential.
12. **Mac mini, a macOS runner.** For Xcode and Apple builds, only once a repo needs them. Native, not a
    container (a macOS job cannot run in a Linux container). Its own user, outside the `admin` and `staff`
    groups where possible, and it must never touch the production Docker engine (`/var/run/docker.sock`);
    anything needing a container uses the dev engine, which the operator starts. The mini's 32 GB are shared
    with production, so one job at a time and a memory cap (mechanism to decide on macOS, where there are no
    cgroups). Label `macos-arm64`.
13. **Rollback per machine:** delete the runner in the repo's Settings, stop and remove its unit or launchd
    job, remove its user. Workflows that asked for that label wait, which the queue alert shows.

### Rollout order

14. A first (it makes B and C visible and safe), then B, then C one machine at a time as a repo needs it.
    Each phase's rollback is above; none needs the later phases.

### The parity rule

15. **A job written for `ubuntu-24.04` runs unchanged on a Linux runner of this fleet.** A gap found is a
    bug in the runner image, fixed there, never in the workflow. The gap goes in the Dockerfile with a
    comment saying what failed and when, as the six above are. To lower the sudo cost per gap, phase A's
    CI tab lists failed jobs with the runner name, so a parity gap is seen from the failure, not from a
    session finding it by hand.

## Runner health: capacity, caches, disk budget, service levels (built 2026-11-27)

The operator agreed this plan on 2026-11-27 after a review of the X3 runners. Each item below is built and
live. The X3-side files are in [`infra/x3/ci-runner/`](https://github.com/chipi/agentic-ai-homelab/tree/main/infra/x3/ci-runner).

16. **Capacity.** Five player runners (player-1..5, ten runners in all), and the `gh-runner` slice raised to
    12 cores and 48 GB (`x3-ci-runner-setup.sh`: `CPU_QUOTA=1200%`, `MEM_MAX=48G`).
17. **A stop that cannot fail the unit.** A runner with `--once` removes its own container when its job
    ends, so `docker stop` found no container and the unit was logged as failed. The fix is
    `ExecStop=-/usr/bin/docker stop …`.
18. **Rollouts without sudo, and without losing jobs.** `ci-runner-sync.timer` (as `gh-runner`, every
    2 min) installs what the operator's account copies to `/srv/ci-runner-src`. It restarts a runner that
    is behind only while that runner has no job, and it now checks for a job just before each restart. An
    earlier version checked every runner once, before the first restart. At the f40081d rollout that check
    was 6 and 11 s old when player-1 and player-3 were restarted. Both had just taken a job, and GitHub
    cancelled the two jobs ("A task was canceled.", 3b1e084). A job taken in the moment between the check
    and the restart is still lost.
19. **Throttling and memory metrics.** `x3-host.sh` pushes the slice's figures as `x3_ci_*`: CPU usage,
    CFS periods and throttled periods, the quota in cores, CPU and memory pressure, memory used, peak,
    `memory.high` and `memory.max`, the events at those limits, and OOM kills.
20. **Caches kept per runner.** Every job starts in a fresh container. Before this change, each job also
    fetched its tools again over the home line. Medians on the X3 against GitHub's VMs (player, 2026-11):

    | Step | X3 | GitHub |
    |---|---|---|
    | HuggingFace cache restore (1.16 GB) | 358 s, and the restore failed | 19 s |
    | Python environment cache restore | 226 s | 34 s |
    | Playwright browsers | 126 s | 10 s |
    | setup-node | 58 s | 3 s |
    | ffmpeg | 52 s | 9 s |
    | setup-python | 34 s | 2 s |

    The downloads stall for about 13 s, then run at 2.8–5 MB/s. Each runner now has its own folder,
    `~/ci-runner/cache/<i>`, kept across its jobs. It is mounted at its host path and named by `$CI_CACHE`.
    It holds:
    - `toolcache/` (`RUNNER_TOOL_CACHE`);
    - `ms-playwright/` (`PLAYWRIGHT_BROWSERS_PATH`);
    - `apt/` (the image's `docker-clean` is removed and `/var/cache/apt/archives` links here);
    - `huggingface/`, for a job to point `HF_HOME` at. Player does this from its PR #56.

    Each runner has its own folder, so two jobs never write to one folder at once. Three fixes went with
    it:
    - `HOME` is the work folder's parent, as on GitHub's VMs. With `HOME` elsewhere, actions/cache stored
      `~/.cache/huggingface` as a path relative to the workspace and restored it into a folder that does
      not exist ("Cannot mkdir").
    - `ImageOS=ubuntu24` and `ImageVersion=<image tag>` are set as GitHub's images set them. Cache keys
      built from them no longer read `ubuntu24-unknown`, so an X3 entry is never restored on GitHub's VMs
      or across X3 images.
    - **Not verified yet:** that these caches fill and shorten the steps above. The check is a comparison
      of step times on player jobs after the runners took f40081d (10:04–10:06Z, 2026-11-27).
21. **Disk budget** (operator, 2026-11-27): 150 GB for the whole fleet, which is 5 GB of downloads and
    10 GB of engine per runner. `entrypoint.sh` (`ci_disk`) checks both at every container start. It is
    best effort: a failure is logged and the job still runs.
    - **Downloads:** each tool version, browser, `.deb` and the HuggingFace folder counts as one entry.
      An entry not read for 14 days goes. Then the least recently read entries go until the folder is under
      5 GB. Read times come from atime under `relatime`, which is precise to about a day.
    - **The runner's own engine:** at every start, untagged images go, build cache unused for 7 days goes,
      and so does an image no job ran for 7 days. Docker records a last use for build cache but not for
      images, so `sync.sh` keeps one: every 2 minutes it writes the images of each engine's running
      containers, with the time, to `cache/<i>/.image-seen`. An image's last use is the newer of that and
      its pull. A container that lives under 2 minutes can be missed; its image then counts from its pull
      and is at worst pulled again. Over 10 GB of layers and build cache, all the build cache goes, then
      images least recently used first until under. Tested in an isolated engine with the clock moved
      8 days on: a seen image and one a container runs stayed, the others went, and the cap removed the
      rest in order.
    - **Reporting:** each start writes `$CI_CACHE/.sizes`, and `sync.sh` gathers the files into
      `log/ci-sizes.prom`. `x3-host.sh` pushes them as `x3_ci_runner_{cache,engine}_bytes` and
      `x3_ci_runner_measured_at` per runner, with `x3_ci_disk_{free,size}_bytes` for
      `/var/lib/gh-runner`. The first reading, at 09:50Z on 2026-11-27, showed engines of 2.7–5.8 GB and
      empty caches.
22. **Service levels** on the Hub's Levels tab (`slo-catalogue.json`, Platform group, linked to `#ci`):

    | Service | SLI | Objective | Query, in short |
    |---|---|---|---|
    | X3 CI runners | online, as a share of runner-minutes | 99% | `avg(gh_runner_up{machine="x3"})` |
    | X3 CI runners | no job waiting over 10 min | 95% | `max(gh_job_queue_seconds_max) < 600` |
    | X3 CI runners | CPU headroom: throttled in under 5% of CPU periods, per 5 min | 95% | `rate(x3_ci_cpu_throttled_periods_total) <= 0.05 * rate(x3_ci_cpu_periods_total)`; an idle slice counts as good |
    | Hub CI collector | fresh within 15 min | 99% | `gh_ci_collector_last_success_timestamp` |

    History starts at about 22:00Z on 2026-11-26. Over that history the four levels stood at 95.5%,
    82.1%, 89.1% and 100% (10:10Z, 2026-11-27), so the first three start below objective. Two events
    caused it:
    - the backlog from the jobs lost on 26–27 Nov, before `--once` fixed it;
    - every X3 runner offline from 02:35Z to 03:30Z on 2026-11-27. The X3 was not rebooted, and its log
      shows Wi-Fi rescans and "UDP is blocked" from tailscaled. The cause has not been found.

## Non-goals

- Public repos. podcast_scraper stays on GitHub's runners.
- Jobs holding production credentials. They stay on GitHub (ADR-0015 rule 5).
- Autoscaling. Runner counts are set by hand inside the cap.

## Open questions

1. **The token's permissions.** Which fine-grained permission the runners list needs (item 3) has not been
   checked.
2. **Where the collector runs.** The mini, next to the Hub, is proposed. The alternative is the X3, which
   would miss an X3 outage in the collector's own view.
3. **GitHub's platform fee.** ADR-0015 says GitHub announced a per-minute fee for self-hosted runners on
   private repos and then postponed it. Its status has not been checked. If it applies, "minutes saved"
   shrinks and the saving needs recomputing before phases B and C.
4. **Runner image updates.** Who bumps the base image (`ghcr.io/actions/actions-runner`, pinned at 2.338.2) and
   how: the image tag is in `ci-runner@.service` and changes by hand with sudo today. A runner version GitHub
   retires stops taking jobs.
5. **Ephemeral registration.** Registration is kept in a volume, so a runner is not ephemeral in GitHub's
   sense (ADR-0015). Ephemeral needs a token that may register runners, which is a stronger secret than
   phase A's read-only one.
6. **The CI box.** Buying it is the operator's plan; this RFC assumes only that its runners can use the
   same labels.

## Alternatives considered

- **Watch GitHub's Settings pages.** What exists. One repo at a time, no history, no alert.
- **Alloy on the runner hosts scraping the runner.** Sees the host, not GitHub's view of the queue and
  conclusions; the queue wait is the number that matters.
- **Run the DGX and mini jobs in containers on the X3.** Cannot give a GPU or macOS.
- **An organization account** to share runners across repos. `chipi` is a personal account (ADR-0015);
  moving is a larger decision than this RFC.

## Not covered

- **Verified today:** the runner list and the six gaps are as reported on 2026-11-26. The collector,
  metrics, labels, DGX and mini runners are all unbuilt.
- **Not verified:** the token permissions; whether Alloy runs on the X3; the status of GitHub's self-hosted
  platform fee; the GitHub API's rate use by the collector at 5-minute polling over five repos (expected to
  be small, not measured); whether macOS lets a memory cap be enforced.
- Disk use outside the per-runner budget (item 21). The X3's own system engine, the dev engine, held
  474 GB on 2026-11-27. It is not the runners', and nothing prunes it.
- Whether the caches in item 20 pay off (to be measured), and the cause of the 02:35–03:30Z outage on
  2026-11-27.
- The CI box's hardware and where it lives.
- Secrets handling for runners beyond "a workstation runner holds no production secret".
- Cost accounting beyond minutes: electricity, the operator's time.
