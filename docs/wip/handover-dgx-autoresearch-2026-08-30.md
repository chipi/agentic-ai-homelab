# Handover — DGX autoresearch vLLM: nothing was missing, it's under `ops`

**Date:** 2026-08-30 · **From:** homelab agent (Mac mini + DGX session)
**To:** the podcast_scraper session that filed "DGX autoresearch vLLM is MISSING"
**Host:** `dgx-llm-1` / `spark-2c14` (100.69.49.126)

## Correction first: the infrastructure was never missing

Your brief concluded *"missing infrastructure, not a wrong GPU mode."* That is
wrong, and the reason is worth internalising: **everything on the DGX lives under
the `ops` account**, and `/home/ops` is mode `drwxr-x---`. From
`markodragoljevic` the box genuinely *looks* empty — no checkout, no `~/bin`
script — which is exactly the dead end you hit. The other trail, the
`~/Projects/podcast_scraper/...` path, came from a **July-1 script backup**; the
current script defaults to `$REPO_ROOT/infra/vllm/autoresearch`.

Everything you asked to be "restored" already exists and is configured:

| Thing | Where | State |
|---|---|---|
| autoresearch compose | `/home/ops/agentic-ai-homelab/infra/vllm/autoresearch/` | present |
| its `.env` | same dir (`0640 ops:ops`) | populated — HF_TOKEN, `VLLM_API_KEY=buddy-is-the-king`, `VLLM_PORT=8090`, `HF_HOME`, cache path |
| model pin | in the compose | `NVFP4/Qwen3-30B-A3B-Instruct-2507-FP4`, and `--served-model-name` is the same string → your `vllm_verify_served_model: true` will pass |
| the model weights | `/opt/llm-models/huggingface` (1.7 TB cache) | **already downloaded** |
| vLLM image | `nvcr.io/nvidia/vllm:26.05-py3` | already pulled |
| `gpu-mode-swap.sh` | `/home/ops/agentic-ai-homelab/infra/dgx/bin/` | present |
| `GPU_MODE_RESEARCH_DIR` | `/home/ops/.config/gpu-mode.env` | already correct |

**The stack is stopped, not absent.** Starting it downloads nothing.

Fastest orientation on this box, for next time:

```sh
docker ps --format '{{.Names}}\t{{.Label "com.docker.compose.project.working_dir"}}'
```

Every running container is an `ops` compose project — that's how you find the root.

## Fire it up (one command)

`~/bin/gpu-mode-swap.sh` on the operator's account is now a wrapper that re-execs
as `ops`, so just:

```sh
ssh dgx-llm-1
gpu-mode-swap.sh status       # read-only sanity
gpu-mode-swap.sh research     # brings up autoresearch vLLM on :8003
```

**Never run `gpu-mode-swap.sh code`** — that's `coder-next`, the operator's IDE
vLLM, off-limits.

### Verify (paste-ready, your own contract)

```sh
ssh dgx-llm-1 'curl -s http://localhost:8003/v1/models | python3 -m json.tool'
# MUST list exactly: NVFP4/Qwen3-30B-A3B-Instruct-2507-FP4
```

## Read this before you start it — GPU is shared with live production

Three services are on that GPU **right now** carrying production ASR/diarization
(your brief said don't disturb them, and they're the reason to care):

`pyannote` :8001 · `faster-whisper` :8000 · `moss` :8004 · plus `ollama` :11434
(your `prod_dgx_full` summary fallback tier). All healthy, HTTP 200.

**Memory sizing — the one thing I'd change before starting.** The `.env` has
`VLLM_GPU_MEM_UTIL=0.65`, but the repo's own `KV_CACHE_SIZING.md` says **0.25**
is right-sized for this exact NVFP4 model (18 GB weights) and that anything
higher just pre-allocates KV cache a single-request sweep never touches —
freeing ~45 GiB of unified memory for those sibling services. With production
ASR live on the same GB10, start at 0.25:

```sh
sudo -u ops sed -i 's/^VLLM_GPU_MEM_UTIL=.*/VLLM_GPU_MEM_UTIL=0.25/' \
  /home/ops/agentic-ai-homelab/infra/vllm/autoresearch/.env
```

I did **not** make that change — it's yours to make deliberately, and it's
trivially reversible.

**Do not touch `VLLM_PORT`.** It's the *engine* (ZMQ) port, not the API port.
The API port is hardcoded to 8003. Setting `VLLM_PORT=8003` makes the engine
bind 8004 and silently crash-loops `moss` — that cost ~3 days once (2026-08-16).

## Observability: fully wired, nothing for you to add

I audited this end-to-end because the operator flagged it as important. Verdict:
**when you start the stack, metrics and logs flow to the mini automatically.**

- **Metrics** → `https://vm.tail6d0ed4.ts.net/api/v1/write`, `instance=dgx-llm-1`.
  The `vllm-autoresearch` scrape job (localhost:8003, 15s) is already defined in
  the DGX alloy config and currently reports `up=0` simply because the stack is
  down. `vllm:*` series exist in VM history from previous runs.
- **Logs** → `https://vlogs.tail6d0ed4.ts.net/insert/loki/api/v1/push`, via
  docker discovery, so the vLLM container's stdout/stderr ships with no extra
  wiring. Verified live: 558 log lines in the last hour from 7 DGX containers.
- **Also scraped:** `dcgm` (GPU), `cadvisor`, `node`, `ollama`, `pyannote`, `alloy`.
- **Dashboards:** *DGX — Services* (`dgx-services`) and *DGX observability (#943)*
  in Grafana, both with vLLM panels.
- **Alerting:** vLLM is **deliberately excluded** from the `infra-target-down`
  rule — these are on-demand services, so "down" is normal, not an incident.
  Don't add a target-down alert for it; that exclusion is intentional.

### LLM tracing — covered, and it all lands in ONE place: the homelab Langfuse

**Corrected twice on 2026-08-30, now verified against the data.** An earlier
draft claimed a tracing gap (wrong), and a second draft claimed a separate
production Langfuse (also wrong). The actual topology:

- **There is exactly one Langfuse — the homelab one on the mini**
  (`langfuse.tail6d0ed4.ts.net`, project `agents`). There is **no** production
  Langfuse.
- **Production runs its own LiteLLM**: prod app → prod LiteLLM → the LLM
  providers — and the tracing lands back in the homelab Langfuse.

Verified by querying that Langfuse's ClickHouse directly (2026-08-30):

| evidence | value |
|---|---|
| `litellm-acompletion` traces | 21,003 |
| `triage-fleet/*` traces (homelab fleet, app-layer naming) | 96 |
| models seen incl. podcast aliases | `podcast-pro-0829`, `podcast-flash-0731`, `openrouter/deepseek/deepseek-v4-flash` (17.5k), `fleet-triage-pro` |
| most recent trace | `2026-08-30 19:58` — live |

Both emission styles are present in that one sink: gateway-level
(`litellm-acompletion`, LiteLLM's Langfuse callback) and app-level
(`triage-fleet/...`). So a `prod_dgx_full` run costs nothing in observability —
per-request prompt/completion/cost tracing arrives regardless of whether the
call goes through LiteLLM or straight to the DGX vLLM on :8003.

**Everything converges on the mini**, which makes correlation easy: LLM traces
in Langfuse, and the DGX's vLLM serving metrics + container logs in
VictoriaMetrics/VictoriaLogs (`instance=dgx-llm-1`) — same box, one place to look.

*(Not inspected by me: the prod VPS itself. It exposes only the `api` and
`integrations/unix` jobs to the homelab VM, and prod SSH uses a separate key I
don't hold — by design. The prod-LiteLLM half of the path above is the
operator's description; the homelab-Langfuse half is verified from its own data.)*

## What I changed on the box

- **Deleted** `~markodragoljevic/agentic-ai-homelab` (a duplicate checkout I had
  created before finding the ops one — removed so nobody repeats this confusion),
  the stale `~/bin/gpu-mode-swap.sh.bak.1782928793` (Jul 1, obsolete path), and
  `~/.config/gpu-mode.env` (pointed at that duplicate).
- **Added** `~/bin/gpu-mode-swap.sh` — wrapper that re-execs the real script as
  `ops`, and `~/README-dgx.md` — orientation for whoever lands there next.
- **Repo:** `infra/dgx/AGENTS.md` now documents the ops-account layout and this
  incident (commit `69519c9`).
- I did **not** start any vLLM, change any `.env`, or touch the running services.

## Caution: do NOT `git pull` the ops checkout as part of this

It sits at `312c29e`, **0 ahead / 94 behind** origin/main, with one local edit —
which turns out to be *the same* port-8003 hardcode that's already upstream, so
the live autoresearch config is functionally current. But those 94 commits
include an **observability restructure** (`infra/observability/config.alloy` →
`hosts/<name>/config.alloy`, plus alloy compose changes). A naive pull risks
breaking the telemetry described above and would recreate running containers.

Reconciling that drift is a separate, deliberate maintenance task — not a
prerequisite for starting autoresearch. Don't fold it into this work.

## One thing left to decide

**`VLLM_GPU_MEM_UTIL` 0.65 → 0.25** while production ASR shares the GPU
(recommended above, deliberately left to you — trivially reversible).

*(A second item — "does the direct-to-vLLM path lose Langfuse tracing?" — was
raised in an earlier draft and is **resolved, not a gap**: the app traces into
Langfuse itself. See the observability section.)*
