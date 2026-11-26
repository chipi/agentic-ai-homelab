# Homelab session handover — 2026-11-26

Handover from the homelab owner session that ran 2026-11-24 to 2026-11-26 (sessions
`c9fb6ef6…` and `014cvkLE…`). The standing punch list is [NEXT_STEPS](NEXT_STEPS.md); this note
says what is in flight and what was promised to whom. Updated 2026-11-26 22:40Z.

## Tomorrow (2026-11-27)

1. **Robotics R7** (robotics-lab's request, its message of 2026-11-26 ~22:25Z): one run in an
   afternoon window ending by 23:20Z. **Needs the operator's go first** (the go of 2026-11-26 covered
   M1 and M2 only). microduck-nav 4248b0e, `Mjlab-Nav-Ours-MicroDuck`, 4096 envs,
   `--agent.max-iterations 400 --agent.save-interval 50 --agent.logger tensorboard`,
   ROBOTICS_MAX_RUNTIME=180m; MICRODUCK_WALKER_ONNX as M2; MICRODUCK_POOL = a copy of
   `/work/microduck-nav-runs/pools/ours-v1.jsonl.gz` (gz sha256 0b23ce53533b23616b853a34fd193e1fa60160390099cd7b70404b718fd004ec,
   check on the DGX). Report the iteration time at 10 (over 26 s does not fit 180 min); stop if the
   first reset does not say "25000 kept; held out: 5000 doorway; skipped ... 0". Copy to
   `/work/microduck-nav-runs/r7/`, swap back to prod, check both vLLMs.
2. **Second brain in Slack (#195, merged 22abc9f):** the mini is ready up to the bridge (litellm_clients,
   alias `second-brain`, key `n8n-second-brain`, n8n recreated, `sbaskrun0000001` live,
   `sbaskagent00001` installed inactive). The operator does the Slack app steps with flotilla and
   writes `~/n8n/sb-bridge/slack-app.token`; flotilla says when. Then: `docker exec n8n n8n
   publish:workflow --id=sbaskagent00001`, `cd infra/n8n/sb-bridge && docker compose up -d`, check
   `healthy` and that its socket opens through the proxy (README, Second brain agent, steps 5-7).

## The runners (ADR-0015), as they are

- All five private repos run CI on the X3: studio, common, player (#49, #50), integration (#19,
  cf97f4c), infra (#121: quality, llms-txt, delivery-test, caddy; deploys and drills stay on GitHub).
  podcast_scraper is public and stays on GitHub's runners. 8 runners: studio-1, common-1, player-1..3,
  integration-1..2, infra-1.
- **Runner fixes need no sudo now:** copy the files to `/srv/ci-runner-src` (the line in
  `infra/x3/ci-runner/sync.sh`'s header); `ci-runner-sync.timer` (gh-runner, every 2 min) installs them
  and restarts each runner that is behind only while idle. Log: `/srv/ci-runner-src/log/sync.log`.
  The setup script is still needed for packages, the slice cap, subordinate ids and a new
  registration (`register.sh`, root).
- Fixed 2026-11-26 (ADR-0015 consequences): jobs run as user runner; a start clears a killed job's
  containers; the work folder and TMPDIR are host paths at the same path; docker compose and the
  browsers' libraries in the image (2.338.2-4); a job's `/var/run/docker.sock` is the runner's own
  engine; setup restarts only idle runners.
- **Seen on the Hub's CI tab (https://hub.tail6d0ed4.ts.net/#ci, RFC-0011 phase A, live):** player
  queues (14 jobs behind 3 runners at 22:08Z); a 4th player runner would need a registration
  (root). Cache restores are slow over the X3's home line (~100 Mbit; a 10 min segment timeout, and
  "tar exit 2" twice on player); a local cache would fix it, not proposed yet.
- At 22:35Z player-1 and -2 had not taken the sync's restart (busy); they take it when idle.

## Guard hooks (2026-11-26, d8f6473)

- subagent-model-guard: one advisor per session per hour (operator: "one advisor at a time"), a 5th
  agent within 10 minutes denied (state the count and cost to the operator), no session_id counted in
  a shared bucket. command-ask-guard: a state-changing docker command that names no engine is denied.
  Attack run against the live hook: the six-advisor pattern allows 1 of 6. After the ingestion
  session ran six Fable "advisors" as auditors.

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
- podcast-evals serves no write tools since 2026-11-26 (`--no-agent-tools`, harness 0.8.2; eval probed 73 tools). fleet- and bakeoff-evals are on an older harness: the two writing MCP tools (`study-ask`, `study-tell`) stay offered there until it adds a
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
