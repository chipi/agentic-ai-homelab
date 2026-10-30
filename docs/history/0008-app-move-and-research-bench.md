# 0008 — The app move closed, a quiet delivery worker, and the research bench

**Date:** 2026-10-30
**Operator:** Marko (chipi)
**Agent:** Claude Opus 5.5, via Claude Code (homelab session)
**Outcome:** the homelab side of the app move (D-0014) is finished: the product stacks, boards
and skills run from chipi/infra and are gone from this repo. The delivery worker no longer floods
its log on every prod deploy, and an alert now tells a deploy blip from an outage. The DGX runs
Ollama 0.40.13 with nine new models for eval-harness, and all three machines that run local models
(DGX, X3, MacBook) send research telemetry to one board.
**Previous:** [0007 — docs/wip cleanup](0007-wip-notes-closed.md).

## What the operator pointed at

The app move's runbook (chipi/infra, driven by the infra session), then a run of follow-ups the
day surfaced: noisy delivery errors, eval-harness's local-model day on the DGX, and "what telemetry
do we have when we research?".

## What landed

**App move (D-0014), runbook steps S1–S8**
- PR A (#119, 8771d1d): `install.sh` links product skills from a chipi/infra checkout (an infra
  skill wins over a same-named one here; a symlink target is RELINKed, never backed up — a `.bak`
  link under `~/.claude/skills` loads as a second skill); `index.py` renders a chipi/infra block;
  `infra-drift` takes several `--checkout`s; the six product boards deleted here.
- S1: chipi/infra cloned on the mini (gh credential helper, this checkout only) and the DGX (ops'
  SSH key). S3: #119 merged, boards re-uploaded to `o11y` by chipi/infra's `grafana_sync` (absent
  ~20 s). S4: delivery runs from `~/chipi-infra` (e2e sends delivered on both builds; the operator
  received both). S5: prod-vllm and translate run from `/home/ops/chipi-infra`. S8: the dead DGX
  GitHub runner retired (service, `/opt/actions-runner`, user; no files left owned by its uid).
- PR B (#123, 04bdacf): `infra/delivery/`, the prod-podcast collector, the three product vLLM stacks
  and the six product skills removed; every reference reworded; research write-ups linked in
  chipi/podcast-scraper-eval-data. S7: both hosts pulled, the old directories (four `.env` files,
  eleven secret/compose backups) deleted after checking nothing used them; drift 0 on both hosts.
- `gpu-mode-swap.sh`: product stacks default to the sibling `chipi-infra` checkout; START_TIMEOUT
  120 → 300 s (a cold `prod` after `free` timed out at 120 s and never started translate).

**Delivery** (chipi/infra #24, 414ff5f + bb3cde2): an unreachable outbox is one INFO line and a
backed-off poll (60 → 300 s) instead of a 40-line traceback every 30 s. Fourteen days of logs:
100 failed polls; all 11 "Connection refused" episodes were prod `compose-api-1` restarts
(deploys). New metrics `delivery_outbox_poll_failures_total` and
`delivery_outbox_last_success_timestamp_seconds` (stamped at start, never 0); homelab alert
`delivery-outbox-unreachable` (f07efa9).

**Eval-harness on LiteLLM and the DGX**
- D-0017: all `eval-*` aliases on `OPENROUTER_API_KEY_EVALS`; cap $60 → $100; aliases added for
  Sonnet 5.5, Haiku 5.5, GPT-6.1 Sol, GPT-6 Luna, Gemini 4 Argon / 3.5 Flash Lite, Mistral Large 4
  and Medium 3.5, Kimi K3.1 Pro, Qwen3.5 122B, gpt-oss-120b, and `eval-fleet-triage-pro`. Fable 5.1
  is refused by the workspace's zero-data-retention guardrail.
- DGX Ollama 0.30.10 → 0.40.13 (the registry refused newer models to 0.30.10 with HTTP 412);
  nine models pulled; GPU in `ollama` mode for the runs (translate freed too), back to `prod`
  before prod's 00:00Z nightly.
- Hugging Face: `orrery-triage` (verdicts.jsonl, 9c6bacb) and `signal-fleet-dedup` tagged v1,
  both private.

**Research bench** (D-0018): the DGX's `ollama.service` journal shipped (0c59ee3) and its
`ollama-metrics` sidecar restarted; user-level Alloy collectors on the X3 and the MacBook
(66f896d); board `Homelab/research-bench` with model speed parsed from llama.cpp's
`print_timing` lines on all three hosts.

**Clean-up and checks**
- Credentials audit on both hosts: a dead token in the DGX's `~/.git-credentials` and the mini's
  stale `fleet.env` deleted; the earliest live expiry is the mini's gh token, 2026-11-27.
- The empty Grafana folders, the litellm `.env` backup and other leftovers deleted (D-0019).
- `install.sh` links only directories with a SKILL.md (05ee032), and a CI job runs
  `install.test.sh` now (66f896d).
- Langfuse's ClickHouse and MinIO pinned to their running digests (c983964): mini drift 0.

## Things that went wrong

- SSH from the X3 to GitHub was refused for ~15 min (14:20–14:35Z) with nothing changed locally;
  it recovered by itself. The key was not touched.
- A script of mine printed "already gone" for DGX directories it could not read (no sudo on the
  existence test); the guard stopped it and the rerun deleted them.
- I first told eval-harness gpt-oss:120b was missing, from an `ollama list` cut at 20 lines.

## Open threads

- The DGX back to `prod` before 22:00Z, then prod's 5-check route test (in progress at writing).
- Research bench: run start/end marks, MacBook GPU (root only), a loaded-model metric off-DGX.
- The unexplained 2026-10-28 16:15–16:30Z delivery timeouts.
- `wip/NEXT_STEPS.md` holds the rest.
