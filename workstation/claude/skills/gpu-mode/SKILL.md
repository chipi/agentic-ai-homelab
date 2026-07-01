---
name: gpu-mode
description: Coordinate which vLLM owns the single DGX GPU before using a local vLLM endpoint. Checks the active mode (code/research/idle/BROKEN-BOTH) read-only, and switches only on explicit request. Use before pointing any tool at a local vLLM (http://<dgx>:9000/v1 or :8003/v1), when a vLLM call fails to connect, or when asked to bring the coder-next or autoresearch vLLM up or down. Switching is shared-state — never switch without explicit approval.
---

# gpu-mode

The DGX has one GB10 GPU; the `coder-next` and `autoresearch` vLLMs can't both
hold it (both want ~90% of VRAM). `gpu-mode-swap.sh` is the authoritative
coordinator. This skill wraps it: **check freely, switch only on explicit go.**

## Connect

The script lives on the DGX host, symlinked at `~/bin/gpu-mode-swap.sh`. Reach it
over the tailnet with ssh (non-interactive → always the absolute path; the
`gpu-mode` zsh alias is not loaded in agent shells):

```bash
ssh dgx-llm-1 '~/bin/gpu-mode-swap.sh <args>'
```

## Check the mode — read-only, always safe

Before ANY local vLLM call, confirm the right stack owns the GPU:

```bash
ssh dgx-llm-1 '~/bin/gpu-mode-swap.sh --mode-only'    # → code | research | idle | BROKEN-BOTH
ssh dgx-llm-1 '~/bin/gpu-mode-swap.sh status --json'  # full machine-readable state
```

- **code** — coder-next up on `:9000`
- **research** — autoresearch up on `:8003`
- **idle** — both down; GPU free for ML training / Ollama
- **BROKEN-BOTH** — both listening (bad state); needs a human, do not pile on

If the mode already matches what you need, proceed. If not, see below — but do
not switch on your own.

## Switch the mode — SHARED-STATE, explicit approval required every time

Switching brings one vLLM up and the other down; it interrupts whatever is using
the GPU right now (a sweep, a training job, Ollama). Treat the DGX as production:

- Never switch as a side effect of "I need the endpoint." Ask first.
- `idle` does not mean the GPU is idle — a training job or Ollama can hold it
  directly while gpu-mode-swap reports `idle`. Confirm with the operator before
  taking the GPU.
- Only after an explicit go, and by absolute path:
  ```bash
  ssh dgx-llm-1 '~/bin/gpu-mode-swap.sh code --json'      # coder-next up, autoresearch down
  ssh dgx-llm-1 '~/bin/gpu-mode-swap.sh research --json'  # autoresearch up, coder-next down
  ssh dgx-llm-1 '~/bin/gpu-mode-swap.sh idle --json'      # both down
  ```

## Report

- State the current mode plainly. If a switch happened, show the `--json` result
  and the resulting mode.
- On `BROKEN-BOTH` or a failed `wait_for_port`, stop and surface it — follow the
  troubleshooting in `docs/recipes/gpu-mode-swap.md`; do not retry blindly.
