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

## Key handling (EMPTY drop-in for now)

`docker-compose.yml` uses `--api-key=${VLLM_API_KEY:-EMPTY}` — it **mirrors
autoresearch's `EMPTY`** so prod-vllm is a drop-in on `:8003` for the current
consumers, which send `Bearer EMPTY`. The prod/dev consumer configs can't be
rotated to a new key right now, so requiring one here would 401 them all.
Tailnet-only endpoint → defence-in-depth regardless.

**Deferred improvement (2026-09-13):** once the consumers can take a new key,
generate a real per-stack secret (`openssl rand -hex 24`), set it in the
untracked `.env`, and tighten the compose back to `--api-key=${VLLM_API_KEY:?…}`
so it fails fast on a missing key.

## Bring-up

```bash
cp .env.example .env      # HF_TOKEN from the shared cache; VLLM_API_KEY stays EMPTY
gpu-mode-swap.sh prod-vllm
```

KV-cache sizing methodology: `../autoresearch/KV_CACHE_SIZING.md` (not
duplicated here — same GPU, same model class).
