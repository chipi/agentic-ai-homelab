# vLLM compose template — hardened coder-next

> **Status: v0.2 — real.** Templated `docker-compose.yml` is here.
> Image tag pinned to `:25.11-py3` (the validated build from genesis).
> Model revision is a placeholder — fill in after first verified boot.

Hardened compose for serving a coding-class LLM on NVIDIA GB10-class
hardware via vLLM, behind an `--api-key` gate. Default model is
`Qwen/Qwen3-Coder-Next-FP8`, port `9000`. The template captures all the
v0.1 genesis decisions in one file.

## Quick start

```bash
# On the DGX-class host:
cp -r agentic-ai-homelab/infra/vllm/ ~/docker-compose/vllm-coder-next/
cd ~/docker-compose/vllm-coder-next/

# 1. Secrets
cp .env.example .env
chmod 600 .env
$EDITOR .env              # fill HF_TOKEN + VLLM_API_KEY

# 2. Caches (one-time per host)
sudo mkdir -p /opt/llm-models/huggingface /opt/llm-models/vllm-cache
sudo chown -R $USER:$USER /opt/llm-models

# 3. Pin the model revision (one-time per model)
$EDITOR docker-compose.yml   # replace MODEL_REVISION_PLACEHOLDER with a SHA

# 4. Boot
sudo docker compose up -d
sudo docker compose logs -f vllm-coder-next   # watch the warm-up

# Cold start = 5-10 min on first revision pull. After cache is warm, ~30s.

# 5. Verify
curl -fsS http://localhost:9000/v1/models -H "Authorization: Bearer $(grep VLLM_API_KEY .env | cut -d= -f2)"
# Expect: {"data": [{"id": "coder-next", ...}], ...}
```

> **Pre-flight tip.** Don't boot this while the autoresearch vLLM or
> Ollama is actively serving — see GPU contention notes below. Run
> [`recipes/gpu-mode-swap.md`](../../docs/recipes/gpu-mode-swap.md)
> `gpu-mode idle` first to clear the GPU.

## Model selection

The template defaults to **`Qwen/Qwen3-Coder-Next-FP8`** — the operator's
working coder model. Reasons:

- FP8 quant fits comfortably in GB10's VRAM at the 0.92 utilization
  budget with a 131k context window.
- Native tool-call schema (`qwen3_coder` parser) works cleanly with
  opencode + Claude Code's MCP tool flow.
- Active model series — Qwen 3 is what the Qwen team is currently
  iterating on.

To swap models:

1. Update the `--model=` arg to the HF path (e.g.
   `Qwen/Qwen2.5-Coder-32B-Instruct`).
2. Update `--tool-call-parser=` to match (parsers are model-family-
   specific — `hermes`, `mistral`, `llama3_json`, `qwen3_coder`, …).
3. Update `--served-model-name=` (this is what clients see in `/v1/models`).
4. Refresh `MODEL_REVISION_PLACEHOLDER` with a SHA for the new model.
5. Re-tune `--max-model-len` and `--gpu-memory-utilization` if the model
   shape changes significantly (see tuning table below).

> **Rule on Blackwell:** prefer **FP8** over **BF16** for the same model
> family. ~1.5-2× throughput at <1% quality loss for code. Only fall back
> to BF16 if the model has no FP8 release.

## Port + GPU memory tuning

The defaults (port 9000, `--gpu-memory-utilization=0.92`) assume the
single-GPU "I own the box" pattern. Adjust per scenario:

| Scenario | `--gpu-memory-utilization` | `--max-model-len` | Notes |
|---|---|---|---|
| Single coder vLLM, exclusive GPU | 0.92 | 131072 | The default. Use with mode-swap. |
| Sharing GPU with Ollama (rare) | 0.60 | 65536 | Leaves room for occasional Ollama serving |
| Multiple vLLM (different ports) | 0.40-0.50 each | 32768 | Possible but not recommended on GB10 |
| Long context priority | 0.92 | 262144 | At the cost of throughput |
| Throughput priority | 0.92 | 32768 | Maximizes batch size |

> Tune `--max-model-len` down before tuning utilization down — KV cache
> scales linearly with context, so trimming 131k → 32k frees a lot of VRAM.

Port `9000` matches the rest of the homelab convention (D-0002 in
`docs/history/0002-decisions.md`). Change at your peril — the Tailscale
ACL, opencode config, Chatbox setup, observability scrape all hard-code
it.

## GPU contention — use the mode-swap recipe

Don't try to run this vLLM alongside the autoresearch vLLM or while
Ollama is under load. The 0.92 utilization budget is "I own the GPU".
Mode-swap is the explicit toggle:

```bash
gpu-mode code         # bring coder-next up, ensure others down
gpu-mode research     # autoresearch instead
gpu-mode idle         # both down
```

Recipe + script template:
[`docs/recipes/gpu-mode-swap.md`](../../docs/recipes/gpu-mode-swap.md).

## Image-bump dance

NVIDIA tags releases like `:25.11-py3`, `:26.05-py3`. The release cadence
is roughly quarterly; image bumps can introduce model-arch breaking
changes (e.g. Mamba support requires transformers 5.x, only in `:26.05-py3+`).

Sibling-file pattern for staging a bump without touching the live config:

```bash
# Stage:
cp docker-compose.yml docker-compose.yml.25.11-py3.bak
cp docker-compose.yml docker-compose.yml.26.05-py3
$EDITOR docker-compose.yml.26.05-py3       # change image tag

# Test:
sudo docker compose -f docker-compose.yml.26.05-py3 up -d
sudo docker compose -f docker-compose.yml.26.05-py3 logs -f
# Validate: model loads, tool calls work, throughput sane.

# Promote (if good):
mv docker-compose.yml.26.05-py3 docker-compose.yml
sudo docker compose up -d

# Rollback (if bad):
sudo docker compose -f docker-compose.yml.26.05-py3 down
sudo docker compose up -d   # already on the old tag in docker-compose.yml
```

The `.bak` of the previous tag stays around — easy reversion if a later
discovery shows the bumped version regressed something subtle.

## Revision pinning

`--revision=MODEL_REVISION_PLACEHOLDER` in the compose is intentional —
fill it in after first verified boot. The pattern:

1. Boot with no `--revision` flag (or a commented-out one) to pull HEAD.
2. After confirming the model works, find the local snapshot:

   ```bash
   ls /opt/llm-models/huggingface/models--Qwen--Qwen3-Coder-Next-FP8/snapshots/
   ```

   The directory name is the SHA.

3. Replace `MODEL_REVISION_PLACEHOLDER` with that SHA. Commit it (the
   compose, not `.env`).
4. Future boots pin to the validated build — no surprise re-downloads
   if HF rebases the model.

## Healthcheck timing

The compose's healthcheck waits 10 minutes (`start_period: 10m`) before
the first probe — cold-start scenarios can run that long because of:

- First-time model download (~75GB at 50-200 MB/s depending on link)
- Initial CUDA-graph compilation (per-shape, multi-minute first time)
- vLLM's warmup pass

After the caches are warm, restarts complete in ~30 seconds. If your
cache is wiped or you're on a fresh box, expect the long path.

If healthcheck fails after 10 minutes: see `docker compose logs` — most
real failures are `HF_TOKEN` missing/wrong, GPU access denied (NVIDIA
runtime not configured), or model SHA invalid.

## Provenance

This template was authored after the genesis session
(`docs/history/0001-genesis.md` Phase 2) productionized the operator's
working compose. Decisions captured in
`docs/history/0002-decisions.md`:

- D-0002 — Port 9000 (unification across both vLLM composes).
- (Phase 2 hardening — see genesis Phase 2 table for the full list of
  what got fixed: container name, log rotation, vllm-cache mount,
  HF_TOKEN wiring, image bump path, `--api-key`, model dedup, revision
  pin, `qwen3_coder` parser + auto tool choice.)

A second working example (different model) lives on the operator's DGX
at `~/docker-compose/vllm-openwebui/`. A more polished reference with
Mamba support exists in `podcast_scraper-FUTURE/infra/dgx/vllm-autoresearch/`
on the operator's machine; see its README for `:26.05-py3+` notes if you're
adopting Qwen3.6-35B-A3B or similar.
