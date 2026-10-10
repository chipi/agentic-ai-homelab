# Handover — homelab session 2026-10-07 → 10-10

For the next agent working with the operator on the homelab. Read this page, then the
[agent operations handbook](../recipes/agent-access.md). Everything here was verified
on 2026-10-10 unless it says otherwise.

## State at handover

- Grafana: **no alerts firing**. DGX ~15% memory available. Mac mini forward healthy,
  dev engine stopped, all delivery workers healthy.
- No work in flight, no background jobs, no temporary worktrees left.

## What this session did (so you don't redo it)

| Area | Result | Where |
|---|---|---|
| Mac mini colima host↔VM forward wedged 7 h (10-08) | recovered; RCA (e2e container publishing a port in the prod VM → lima `-O forward` hung); watchdog alert now rate-based, capture keeps evidence, **auto-restart enabled** and live-tested | `docs/recipes/colima-lima-forwarding-recovery.md` |
| Development vs production Docker on the mini | prod socket `root:admin`; on-demand **dev engine** for development (`devengine start/stop`) | ADR-0009, `docs/recipes/dev-docker-engine.md` |
| Agent access | **operations handbook** with tested recipes for every service | `docs/recipes/agent-access.md` |
| Daily-recap false alarm (#2212) | rule now watches whether the enqueuer runs; #2212 closed | `rules.yaml` uid `delivery-cadence-daily-recap-stale` |
| DGX memory alert | faster-whisper restarted (8.95 → ~1 GiB); `WHISPER__TTL=-1` deployed (podcast_scraper 8f5291df4) | — |
| DGX converge `env_file` bug | fixed in podcast_scraper 53c4b19f7 (operator user read at deploy time) + regression test; CI green | podcast_scraper `infra/dgx/converge/deploy.py` |
| Delivery | 6483321 (new-episodes push `open_url`) deployed; rollback tag `closelistening-delivery:pre-6483321` | — |

## Open — needs the operator's decision

### 1. Do not run a real full `make dgx-deploy` yet

A pyinfra dry run of podcast_scraper main against the DGX (2026-10-10) connected and
loaded the fixed `deploy.py`, and listed what a **real** run would change beyond the fix:

| What | Effect of a real run | Status |
|---|---|---|
| `whisper-server` (retired OpenAI-whisper, no container today) | Dockerfile + `app.py` shipped, image built, **service started** — a new GPU/memory consumer | real surprise |
| `/opt/observability` (absent on the DGX) | installs DCGM + node-exporter + cAdvisor with `container_name: dcgm-exporter` / `cadvisor` — the **homelab-managed containers with those names already run** → name clash, that step errors | real surprise |
| `pyannote-server` | newer `app.py` from main shipped, image rebuilt, service restarted | expected? confirm with the operator |
| faster-whisper, moss | compose files rewritten (identical to live, comments aside), images pulled/rebuilt, `up -d` | restart only if the rebuilt image differs |
| `chown 1000:1000 /opt/llm-models/huggingface` | no-op: uid 1000 already owns it | fine |

Reconcile the first two (retire `whisper-server` and the observability block in
`deploy.py`, or make them opt-in) before anyone runs it for real.

**How to run the dry run without the operator** (their key has a passphrase; their
plain `ssh dgx-llm-1` uses Tailscale SSH): from a podcast_scraper checkout with
`infra/.env.dgx.local` and `infra/dgx/converge/.venv`:

```sh
set -a; . infra/.env.dgx.local; set +a; unset DGX_SSH_KEY
cd infra/dgx/converge && .venv/bin/pyinfra --sudo --dry inventory.py deploy.py --data ssh_config_file=/dev/null < /dev/null
```

`--dry` executes nothing; without `-y` it prints "Detected changes" (with `-y` it skips
detection). `--data ssh_config_file=/dev/null` stops pyinfra loading the
passphrase-protected key from `~/.ssh/config` and lets it authenticate through the agent.

### 2. Parallel long-episode transcription — documented, deferred

[podcast_scraper#2303](https://github.com/chipi/podcast_scraper/issues/2303): each long
episode in flight costs ~5.4 GiB in faster-whisper (three 132-min episodes at once peaked
~21 GiB against ~18–20 GiB free); nothing bounds the total across overlapping pipeline
runs. Operator: "We're not going to fix it. I just want to document." Pick up when asked.

## Dropped by the operator — do not re-raise

- Rotating keys (the Hugging Face token printed in a 10-09 transcript, the old
  eval-harness LiteLLM key): "I'm not going to rotate any keys right now."
- Purging local test traffic from Umami ("Player (dev)" ~75.9k events, "Player" 424): "no need".

## Watch-list (no action unless it recurs or the operator asks)

- faster-whisper's 8.8 GiB retention on 10-08 is unexplained; the DGX memory alert
  (<10%) will catch a recurrence.
- prod VPS: 7 OOM kills in a week (the fleet's "Kernel OOM killer fired" recurrences) —
  not investigated.
- podcast_scraper `stack-jobs-flow` live smoke is flaky (digest rows not visible in 120 s).
- Daily-recap alert can't see "ran but wrongly sent nothing" — needs an app-side
  "episode finished" metric.
- lima#5420 upgrade: monthly check in `docs/wip/NEXT_STEPS.md`.
- Moving the handbook (and the global AGENTS.md) to a private repo: when the operator
  restructures repos; keep it public until then.
- Undeletable throwaway test data expiring by retention: 2 VictoriaLogs lines and 1
  VictoriaTraces trace labelled `zz-handbook-test` / `source=handbook`.
- Langfuse ClickHouse CPU — offered in an earlier session, never approved.

## How to work with this operator (from this session)

- Homelab-repo and Mac-mini work is the homelab session's; never hand it to another
  project's agent. Pushes to agentic-ai-homelab main are pre-approved; podcast_scraper
  needs an explicit "yes" each time (direct to main, no PR).
- Check what already exists before proposing infrastructure — agents already reach every
  production service through the operator's SSH keys (handbook §0).
- The operator often works from a phone over Remote Control: never ask them to type in a
  terminal; find a way to do it from the session.
- Run multi-line remote recipes as script files, not heredocs piped through `ssh`
  (corrupts JSON); in zsh, `$var` doesn't word-split (use bash for loops over lists).
