# Homelab session handover — 2026-11-26

Handover from the homelab owner session that ran 2026-11-24 to 2026-11-26 (sessions
`c9fb6ef6…` and `014cvkLE…`). The standing punch list is [NEXT_STEPS](NEXT_STEPS.md); this note
says what is in flight and what was promised to whom. State checked at 2026-11-26 00:10 CET.

## In flight: watch these first

1. **Done: the fresh container per job is proven.** Studio #22 (477f7f7cf, run 45721319358): `e2e`
   started 2 s after `viewer` on `x3-closelistening-studio-1` and passed. Studio main 21d87707
   (run 45722744424): `e2e` right after #22's `e2e`, passed. database has the main sha for
   Integration's lock. If "webServer exited early" ever returns, check that the runner container
   restarted after the previous job (README in `infra/x3/ci-runner/`).
2. **Self-hosted runners, next repos: the morning deploy is done; go ahead** (operator, 2026-11-26:
   "Deploy is done, we can continue with gh runners"). Nothing is pushed yet: common's change was
   checked on a throwaway branch (`test.yml` has one job, line 22, `runs-on: ubuntu-latest`; no
   `docker://` actions, no container jobs) and dropped when the session ended. Redo it: clone
   chipi/closelistening-common, branch `ci/x3-runner`, `runs-on: [self-hosted, x3]`, open the PR, watch
   its Tests run on `x3-closelistening-common-1`, merge on the operator's go. Then closelistening-player (six jobs: register `closelistening-player-2` and `-3`
   first; its session changes `runs-on`), then closelistening-integration. `infra`'s deploy, backup and
   drill jobs stay on GitHub (ADR-0015). Details: NEXT_STEPS, X3 section.

## The runners (ADR-0015), as they are

- `gh-runner` on the X3 (uid 959, not in the docker group); per runner a rootless engine
  `docker@<repo>-<n>` and a container `ci-runner@<repo>-<n>`; all of it capped at 8 cores and 32 GB.
- Online: `x3-closelistening-studio-1`, `-player-1`, `-common-1`. Only Studio's workflows use them
  so far (#20, merged).
- Changes to `infra/x3/ci-runner/` reach the X3 only when the operator runs
  `sudo bash ~/deploy/agentic-ai-homelab/infra/x3/x3-ci-runner-setup.sh` (pull the deploy checkout
  first). A runner registration: an agent writes a one-hour token
  (`gh api -X POST repos/chipi/<repo>/actions/runners/registration-token -q .token`) to a mode-600
  file in `~/deploy/`, the operator runs `register.sh <repo> <n> <file>`.
- Fixed on the way, each reproduced in the image first: the engine's netns (a host-net runner
  reaching its job's services), root's sudo (`--group-add sudo`; the image's sudoers has no
  sudoers.d), apt's downloads kept (`docker-clean` removed), one engine per runner (5432 collisions),
  a fresh container per job.
- Open: true ephemeral registration, an image prune per engine, metrics and an alert. GitHub's
  announced fee for self-hosted runners on private repos was postponed; its current state is
  unchecked.

## The DGX

- Mode `prod` (switched back and checked after Recce's RC-P10 window, 2026-11-26 morning: both
  vLLMs healthy, /v1/models answering on :8003 and :8005). photogrammetry (Recce) has the operator's standing go to switch
  it to `free` for daytime GPU windows: it switches as `markodragoljevic@dgx-llm-1`, sends "done",
  and homelab switches back with `~/bin/gpu-mode-swap.sh prod --json`, then checks both vLLMs
  (healthy, `/v1/models` on :8003 and :8005). The operator: "I tell any agent and any agent can flip
  the switch."

## Eval catalogs and MCP (infra/evh-serve), live since 2026-11-24

- https://{fleet,podcast,bakeoff}-evals.tail6d0ed4.ts.net, MCP at `/mcp`; listed on the Hub.
- The 5-minute sync runs (`/tmp/evh-serve.log` on the mini: all three UP TO DATE at 23:09Z), but no
  new commit has reached any of the three since the deploy, so "a new commit appears" is unproven.
- The two writing MCP tools (`study-ask`, `study-tell`) stay offered until eval-harness 0.8.2 adds a
  flag; the containers are the guard (read-only checkout, no keys, $0 cap, internal network).

## GitHub hardware choice (for the operator)

- [Homelab Mini PCs](https://claude.ai/artifact/6XWwTaRr3hpVek9axcfiov): Lenovo M90q/M80q Gen 4 or
  Dell 7010 Plus Micro with an i5-13500T. Offers seen: OptiPlex 7070 Micro (base €190; i5-9500T,
  32 GB, 512 GB = €449; i7-9700T, 32 GB, 1 TB = €589), fine for services and staging, weak for CI;
  a 7070 Micro with i5-9600 (65 W, price not given).

## GlitchTip (2026-11-24)

- flotilla took issues 761 (contract check), 944, 943, 941; it resolves them after a deploy proves
  them quiet. Leave them.
- orrery logged 1193 (ResizeObserver) and 1188 (Load failed) as row B2 in its 0.9.12 plan.
- 566 and 876 (Langfuse "Unexpected error") resolved on the operator's go: traces lost during
  planned restarts of the mini (the colima restart 2026-11-24 07:20Z, a Caddy restart 2026-11-14 03:10Z).

## Waiting on the operator

- **Backups (ADR-0014):** the go for the mini's nightly restic job; first check why the
  2026-11-21 offsite run failed ("no files for stamp 20261121-043004") and whether the stale alert
  fired. The operator still copies the three `restic.pw` files into the password manager.
- Asking eval-harness to cap its test parallelism (it starved robotics-lab, 2026-11-24): offered,
  not answered.
- The bold note added to `docs/recipes/agent-access.md` (5c0dbb6, "any agent session on the X3 can
  stop prod"): the operator called it unasked-for; revert offered, not answered.

## Done this stretch (for the paper trail)

- X3: Omarchy's crash notifier off and its `diagnose-crash` skill links removed, in the installer;
  three stray Omarchy-launched Claude sessions terminated; docker0 recreated by the operator after it
  vanished (2026-11-25 09:23).
- evh-serve (replaces infra/fleet-evals), the Hub rows, ADR-0015 and the runners, R8 point B passed on
  eval-harness 0.8.1 candidate 7bd64876d.
