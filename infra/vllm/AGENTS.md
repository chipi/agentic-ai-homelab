# AGENTS.md — infra/vllm/ (scoped rules)

Loaded when working under `infra/vllm/`. Layers on top of
[`../AGENTS.md`](../AGENTS.md) and the DGX rules in
[`../dgx/AGENTS.md`](../dgx/AGENTS.md); never duplicates or contradicts them.

`infra/vllm/` holds the local vLLM compose stacks — the serving model
(`coder-next`), the eval/sweep model (`autoresearch`), an Open WebUI front end,
and a `template/` to copy for new stacks. The rules here are the conventions
shared across those stacks.

## Port and key conventions

- **The serving vLLM listens on `9000`** (`coder-next` and `openwebui` target
  it); the autoresearch sweep vLLM uses `8003` (matches
  `GPU_MODE_RESEARCH_PORT` in `gpu-mode-swap.sh`). Keep new stacks on this
  convention.
- **`VLLM_API_KEY` is a single-operator dummy** (`buddy-is-the-king`). vLLM
  requires *a* key, but there is no real secret here; clients just send the same
  value as `Authorization: Bearer`. The one real secret is `HF_TOKEN` (gated
  model downloads), which lives only in `.env`.

## GPU coordination is not optional

One GB10 GPU cannot host two vLLMs at once. Before bringing any stack up, switch
modes with `gpu-mode-swap.sh` per [`../dgx/AGENTS.md`](../dgx/AGENTS.md) — never
start a second vLLM while another holds the GPU.

## GPU memory sizing

`--gpu-memory-utilization` has a hard ceiling of **0.78** on GB10 unified memory
(above starves the host; **0.92 OOM-crashes — never use it**). Right-size per
workload, not by default: single-request sweeps need far less KV cache than
concurrent serving. Methodology + per-model values:
[`autoresearch/KV_CACHE_SIZING.md`](autoresearch/KV_CACHE_SIZING.md).

## Adding a new stack

Copy [`template/`](template/) — it carries the shared env wiring, the healthcheck,
and the repo-root `.env` convention. Record non-obvious model/param choices as a
dated note under `<stack>/decisions/` (see `autoresearch/decisions/`).
