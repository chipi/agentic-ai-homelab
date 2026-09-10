# vllm-prod-vllm — production serving vLLM

A dedicated **production serving** vLLM stack, split out from `autoresearch/`
so the two roles no longer share one folder:

- **`autoresearch/`** — eval / sweep target (podcast_scraper contention runs,
  #928-style baselines). Key defaults to a placeholder; may run open.
- **`prod-vllm/`** (this stack) — production serving. Key is **required**; no
  well-known/empty fallback.

Same model pin as autoresearch today (`NVFP4/Qwen3-30B-A3B-Instruct-2507-FP4`),
so this starts as a faithful copy of its serving config. Repin here when prod's
model diverges from the eval baseline.

## Name disambiguation (important)

There are two "prod" things and they are **not** the same:

| Thing | What it is |
|---|---|
| gpu-mode **`prod`** | podcast_scraper pipeline mode — *no vLLM*; Ollama serves the pinned `qwen3.5:35b` summary model plus whisper/pyannote/moss. |
| gpu-mode **`prod-vllm`** (this) | a real vLLM slot serving the model above on `:8003`. |

`gpu-mode-swap.sh prod-vllm` brings this up (and every other vLLM slot down —
single-owner-at-a-time on the one GB10 GPU).

## GPU coordination

Shares the single GB10 GPU with `coder-next` / `autoresearch` / `judge-*`. Only
one may own the GPU at a time; `gpu-mode-swap.sh` enforces it. This stack binds
`:8003` (the only ACL-permitted egress), same as autoresearch — which is why
they are mutually exclusive, not concurrent.

## Key handling (the security fix)

`docker-compose.yml` uses `--api-key=${VLLM_API_KEY:?…}`, so `docker compose up`
**fails fast** if the untracked `.env` has no real key. Generate one:

```bash
openssl rand -hex 24    # → VLLM_API_KEY in .env (chmod 600, never committed)
```

Do not reuse `buddy-is-the-king` (the compose-fallback placeholder for the
other stacks) or `EMPTY`. Tailnet-only endpoint → defence-in-depth.

## Bring-up

```bash
cp .env.example .env      # then fill HF_TOKEN + a generated VLLM_API_KEY
gpu-mode-swap.sh prod-vllm
```

KV-cache sizing methodology: `../autoresearch/KV_CACHE_SIZING.md` (not
duplicated here — same GPU, same model class).
