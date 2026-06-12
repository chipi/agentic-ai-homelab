# vLLM compose template

> **Status: v0.1 placeholder.** Real templated compose lands in v0.2 per
> `docs/wip/NEXT_STEPS.md`. The session that produced the source compose is
> recorded in `docs/history/0001-genesis.md` Phase 2.

## What goes here (target state)

A hardened, templated `docker-compose.yml` for serving a coding-class LLM
(initial target: `Qwen/Qwen3-Coder-Next-FP8`) on NVIDIA GB10-class
hardware via vLLM, behind an `--api-key` gate.

Captures all the decisions from `docs/history/0002-decisions.md`:

- `--api-key <secret>` enabled (placeholder + comment to override)
- `--revision <SHA>` pinned to a known-good model snapshot (template:
  user provides SHA after first verified boot)
- `--enable-auto-tool-choice` + `--tool-call-parser qwen3_coder`
- `VLLM_DISABLE_TORCH_COMPILE=1` (Blackwell hot-fix)
- `gpu-memory-utilization` and `max-model-len` tunable via env
- Shared HF cache mount (`/opt/llm-models/huggingface`)
- vLLM CUDA-graph cache mount (`/opt/llm-models/vllm-cache`) — avoids
  recompile on cold start
- `env_file` for `HF_TOKEN` (gated-model support)
- Log rotation (`50m × 3`)
- Healthcheck with 10-min `start_period` (cold cache model load)
- `restart: unless-stopped`
- Sibling-file image-bump convention: `docker-compose.yml.<newtag>` for
  staging an image upgrade without touching the live config

## Reference source (until v0.2 lands)

The actual working compose lives on the operator's DGX at
`~/docker-compose/vllm-Qwen3-Coder-Next/docker-compose.yml`. It was the
output of Phase 2 of the genesis session. Until templated and committed
here, that file is the canonical reference.

A second working example (different model, different memory utilization
profile) lives at `~/docker-compose/vllm-openwebui/`.

A more polished reference with a richer description lives in
`podcast_scraper-FUTURE/infra/dgx/vllm-autoresearch/` — see its README for
deeper notes on the NVIDIA image version interaction with model
architecture (Mamba support requires transformers 5.x, only present in
26.05-py3+).

## Open in v0.1

- [ ] `docker-compose.yml` — the templated version.
- [ ] `docker-compose.yml.example` with substitution variables clearly
      flagged.
- [ ] `README.md` expansion — model selection guidance, GPU memory
      tuning table, mode-swap pattern, image-bump checklist.
- [ ] `gpu-mode-swap.sh` helper — toggle which vLLM compose owns the GPU.
