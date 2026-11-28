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
    12 cores and 48 GB (`x3-ci-runner-setup.sh`: `CPU_QUOTA=1200%`, `MEM_MAX=48G`), on CPUs 4-15 from item 25.
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
21. **Disk budget** (operator, 2026-11-27): 10 GB of engine and 8 GB of downloads per runner, 180 GB for
    the fleet. Downloads were 5 GB (150 GB) until the same day, when kept virtualenvs (item 24) were agreed.
    `entrypoint.sh` (`ci_disk`) checks both at every container start. It is best effort: a failure is
    logged and the job still runs.
    - **Downloads:** each tool version, browser, `.deb`, kept virtualenv and the HuggingFace folder counts
      as one entry. An entry not read for 14 days goes. Then the least recently read entries go until the
      folder is under 8 GB. Read times come from atime under `relatime`, which is precise to about a day.
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
    | X3 CI runners | CPU wait: some job waiting for a CPU under 10% of the time, per 5 min (item 25) | 95% | `rate(x3_ci_cpu_pressure_seconds_total) < 0.1` |
    | Hub CI collector | fresh within 15 min | 99% | `gh_ci_collector_last_success_timestamp` |

    History starts at about 22:00Z on 2026-11-26. Over that history the four levels stood at 95.5%,
    82.1%, 89.1% and 100% (10:10Z, 2026-11-27), so the first three start below objective. Two events
    caused it:
    - the backlog from the jobs lost on 26–27 Nov, before `--once` fixed it;
    - the X3 runners shown offline by GitHub for 25–31 minutes each on 2026-11-27, in two stretches (item
      23).

23. **Runners GitHub shows offline while they run.** On 2026-11-27 the home line dropped for a minute or
    two at 02:29Z: every runner's poll to GitHub's broker timed out ("The HTTP request timed out after
    00:01:40"), and the mini's egress probe failed at 02:30Z. GitHub showed the runners offline from 02:31Z
    to 02:35Z, then again for 20–25 minutes from about 03:01Z. `gh-runner`'s journal shows them polling
    without an error from 02:30Z on, and refreshing their tokens on schedule. The X3 is wired; its Wi-Fi
    is on but unconnected, so the rescans in its log are only searching. GitHub's status page lists no
    incident then. `sync.sh` now restarts a runner, which opens a new session, when all of these hold:
    - GitHub showed it offline in every sample of the last 10 minutes (`gh_runner_up` in VictoriaMetrics,
      from the collector), with 2 or more samples;
    - its unit has been up for 15 minutes;
    - it is idle;
    - it was not restarted this way in the last 30 minutes.

    No answer from VictoriaMetrics means no restart. On that night's data it would have restarted every
    runner at about 03:11Z, and the 5-minute drop at 02:31Z would not have triggered it.

24. **Kept virtualenvs** (operator, 2026-11-27). Common's `python-env` action caches the whole virtualenv,
    about 1–1.5 GB with CPU torch, in GitHub's cache. On GitHub's VMs it restores in 34 s; on the X3 it came
    down the home line every job, in 192–284 s, the slowest step left.
    - **On the X3,** the action skips GitHub's cache. It keeps the built venv in `$CI_CACHE/venvs/<key>`
      and gives each job its own copy at the path it was built at, by a btrfs reflink. The copy shares the
      file data, so it takes seconds, and whatever a job installs into its copy never reaches the next job.
      Tested in a container across two bind mounts of the X3's root subvolume: 300 MB and 3,000 files in
      0.05 s, every extent shared.
    - **The key decides freshness.** Today it is the image, the Python version, a hash of public's
      `pyproject.toml` and the extras. The operator asked how a cached venv stays true to a fresh install.
      Two gaps: the dependencies are ranges with no lock file, so new releases inside a range never change
      the key; and how the venv is built (the action itself) is not in the key. Agreed with the same change:
      - the ISO week in the key, so every venv is rebuilt at least weekly, on GitHub and on the X3 alike;
      - a hash of the action file in the key;
      - a weekly job that builds with no cache, so a fresh install that breaks is seen within days.

      Proposed to Common and public as a follow-up: a lock file in the key.
    - **The rule for every cache:** its key names everything that shapes its contents. Anything resolved
      at build time from outside, such as a version range, needs a time limit in the key or a pinned input.
      A regular run with no cache proves a fresh install still works.
    - `ci_disk` prunes each venv as one entry (item 21). Common's side is theirs to build; this item is
      the runner's part.
25. **Jobs see the cores they may use** (operator, 2026-11-27). The first CPU-headroom level (throttled in
    under 5% of CFS periods) stood at 72.8% over its first three hours, 10:00-13:00Z on 2026-11-27. Over
    the last four of those hours the slice used 20,055 CPU-seconds, 1.4 cores on average and at most 6.7
    in any 10 minutes, against its 12-core quota; yet 5-38% of its periods were throttled in busy 10-minute
    windows. Every job saw all 32 CPUs and sized its worker pools to them, so a burst used up the
    period's 1.2 s of quota within the 100 ms period. The cost was small: CPU pressure (some) of 229 s in
    the four hours, 1.6% of the time. The throttle counter's 4,360 s adds up the time over CPUs, so it
    overstates the delay.
    - **`AllowedCPUs=4-15`** on the slice (`CPU_SET` in `x3-ci-runner-setup.sh`), one thread of each of 12
      physical cores. `nproc` and every tool that reads the CPU affinity then see 12, and 12 busy CPUs use
      exactly the quota. Kept with it, the quota only bites if the cpuset is lost. `x3-host.sh` pushes
      `x3_ci_cpu_allowed_cores`.
    - **The level measures waiting, not throttle counts:** a minute is good when some task in the slice
      waited for a CPU under 10% of the time over 5 minutes (`cpu.pressure`, which counts waits from the
      cap as well as from the jobs sharing the 12 CPUs). Its id changed with it
      (`x3-ci-runners--cpu-wait-under-10-of-the-time-5-min`). The 10% line is above the worst 10 minutes
      seen so far (9.5%, 11:24Z).
    - Not verified yet: that a job container reports 12 from `nproc` after the change, and how the
      pressure moves once the jobs share 12 CPUs instead of being throttled.
    - Applied 2026-11-27 (the operator ran the setup): `cpuset.cpus.effective` is `4-15`, every one of the
      slice's 187 processes is allowed 4-15, and `x3_ci_cpu_allowed_cores` reads 12.
26. **Runners per repo, and a cap on running jobs** (operator, 2026-11-27: "at least 3 runners" per repo
    for contingency, "and then some other level to cap the total"). Over the metrics held (about 3 days):

    | Repo | Runners | Most busy at once | Minutes all busy | Longest wait |
    |---|---|---|---|---|
    | player | 5 | 5 | 230 | 84 min, mostly the backlog of 26-27 Nov |
    | common | 1 | 1 | 61 | 14 min |
    | infra | 1 | 1 | 48 | 7.5 min |
    | integration | 2 | 2 | 19 | 20 min |
    | studio | 1 | 0 | 0 | 0 |

    - **Runners:** 3 for common, infra and integration (each filled what it had), 2 for studio (no X3 job
      yet; the second is contingency), player stays at 5: 16 runners. Disk: 16 x 18 GB = 288 GB for the
      fleet (item 21), against 584 GB free. Each runner keeps its own caches, so more runners also means
      more first jobs that build them.
    - **The cap counts running jobs, not runners.** GitHub cannot cap across repos here: chipi is a user
      account, and runner groups are for organisations. A runner that is listening holds nothing; a job
      takes a slot in its job-started hook (`entrypoint.sh`), in a folder every runner shares
      (`~gh-runner/ci-runner/slots`, `mkdir` is atomic): its repo's own slot `r-<repo>`, else one of
      `CI_SLOTS_SHARED` (2, `ci-runner@.service`). With five repos that is 7 jobs at once at most, each
      repo always able to run one. While every slot is taken the job waits in its "Set up job" step, which
      says so, and its time counts against the job's timeout. The completed hook frees the slot; a runner's
      next start frees any slot it still holds (its job was killed), and `sync.sh` frees one whose runner
      unit is not active. Memory peaked at 26.8 GiB of 48 with 6 jobs at once; the slice's CPU and memory
      cap (items 16, 25) still bounds them all together.
    - **Metrics** (`sync.sh`, through `ci-sizes.prom`): `x3_ci_slots_held`, `x3_ci_slots_total`,
      `x3_ci_jobs_waiting_for_slot`, `x3_ci_slot_wait_oldest_seconds`.
    - Tested with a harness over the hook block (three runners of one repo and one of another, one shared
      slot): the third waits, the other repo's job does not, a freed slot is taken within 5 s, a restart
      frees a killed job's slot. Not tested yet inside a runner container on a real job.
    - **7 slots, not 10** (operator, the same evening). CPU is the limit, not memory: from 18:20 to 19:00Z,
      with 5-6 jobs at once, the slice used 10-11 of its 12 cores and some task waited for a CPU 62-71% of
      the time, so the CPU-wait level (item 25) read 0.834 against 0.95. With 10 slots, more jobs would
      only slow each other; with 7 the rest wait for a slot. Giving CI more than 12 CPUs is the other way,
      left for the operator to decide from a few days of the CPU-wait level and the slot-wait alert.
    - **Live the same evening:**
      - 16 runners online on GitHub (the operator registered the six new ones).
      - On a real job, player-3's docs (140697214710) waited 40 s, took `s-1`, and its completed hook ran
        clean.
      - Three fixes followed:
        - The completed hook exits 0 when the job holds no slot (6546b5c).
        - `wait/` is writable by the hook's user (dbe6d4c). Waits were not recorded before, and the
          harness, run as one user, could not catch it.
        - `x3_ci_slot_held{slot,runner}` shows which runner holds which slot.
    - **Two jobs lost to the sync's update restart** (player #60: 140697214368 on player-1 and
      140697214738 on player-4):
      - Each container had just started and taken a job. 53 s later the sync restarted it as idle, and
        GitHub declared the job lost 10 minutes after.
      - Why neither the worker check nor the `.job-running` marker saw the jobs is not established. Both
        most likely sat in the slot wait.
      - Two guards since:
        - no update restart of a container started under 10 minutes ago (80c284f): a container takes new
          files at its next start anyway;
        - none of a runner that holds or waits for a slot (25420b2).
    - **One spare, not one per repo, and 20 CPUs** (operator, 2026-11-28). With a slot reserved for each
      repo, Player had 3 slots at most (its own and the 2 shared) while the other four sat unused:
      its docs job waited 565 s and its lint 636 s for a slot and ran out of their 10-minute limits
      (runs 46061027627 and 46055604562). Now:
      - every slot (`s-1` to `s-<CI_SLOTS_TOTAL>`, 8) is shared;
      - a repo already running a job takes one only while 2 or more are free, so one stays spare for
        another repo's first job (best effort: two jobs checking at once can both take the last two);
      - the slice has 20 CPUs (`CPU_QUOTA=2000%`, `CPU_SET=4-15,20-27`: the 12 physical cores and the
        second thread of 8 of them), leaving 0-3, 16-19 and 28-31 to the host;
      - 8 slots on 20 CPUs keeps the ratio that 12 carried at about 5 jobs.
      Tested with the harness at 3 slots: two jobs of one repo run, its third waits for the spare,
      another repo's first takes the spare, a third repo's waits when all are taken, and a release
      lets the waiting job in within 5 s.
27. **npm's cache kept per runner** (2026-11-27). Lighthouse's setup-node took 78 s on player-4:
    - Node came from the kept tool cache in under a second.
    - The rest was restoring setup-node's 129 MB npm cache from GitHub's cache. npm's cache lived in the
      container's HOME and was lost after each job.
    - `npm_config_cache` now points at `$CI_CACHE/npm`, pruned as one entry.
    - A workflow turns setup-node's cache off on the X3 (`cache: ${{ !startsWith(runner.name, 'x3-') &&
      'npm' || '' }}`), asked of Player.
    - The public checkout (230-317 s against about 19 s) is Player's to change: a shallow fetch, or a
      kept mirror under `$CI_CACHE/git`.

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
  474 GB on 2026-11-27. It is not the runners'; since that day `infra/x3/dev-engine-prune.sh` prunes it
  weekly (the first run freed 120 GB), and the Hub's Docker disk tables show every engine.
- Whether the caches in item 20 pay off (to be measured), and why GitHub showed the runners offline from 03:01Z on
  2026-11-27.
- The CI box's hardware and where it lives.
- Secrets handling for runners beyond "a workstation runner holds no production secret".
- Cost accounting beyond minutes: electricity, the operator's time.
