---
name: vllm-deploy
description: Safely bring a local vLLM stack up. Runs the read-only preflight (gpu-mode check, compose-check, .env presence) then hands you the exact deploy command for approval. Use when deploying or restarting coder-next / autoresearch / openwebui. Never runs up/down itself — the mutating step is gated on explicit approval.
---

# vllm-deploy

Bring a vLLM stack up without stepping on the GPU or a broken config. **Preflight
is read-only; the deploy is shared-state and gated on explicit approval.**

## Preflight — do all of these first (read-only)

1. **GPU free?** `ssh dgx-llm-1 '~/bin/gpu-mode-swap.sh status --json'`. If a
   compute app holds the GPU, or the other vLLM is already up, STOP — taking the
   GPU is a switch, which is gated (use the `gpu-mode` skill and get approval).
2. **Config valid?** Run the `compose-check` skill on the stack
   (`docker compose config -q` → PASS / ENV-MISSING / FAIL).
3. **Env ready?** If ENV-MISSING, `cp .env.example .env` and fill (`HF_TOKEN`)
   before deploying.

## Deploy — SHARED-STATE, explicit approval each time

Only after preflight is clean and the operator says go. The stack owns the GPU;
treat the DGX as production.

- Prefer `gpu-mode-swap.sh <code|research>` — it sequences the swap (brings the
  right stack up and the other down) rather than a bare `up`.
- Or, run from the stack dir in place (repo-root `.env` convention):
  `docker compose up -d`.
- **Never** `down -v`, prune volumes, or restart a live stack without separate,
  explicit approval.

## Verify

`ssh dgx-llm-1 'curl -fsS http://127.0.0.1:<port>/health'` and confirm the mode
matches (`gpu-mode` check). Report the resulting mode + health.
