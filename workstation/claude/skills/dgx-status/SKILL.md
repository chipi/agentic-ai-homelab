---
name: dgx-status
description: One-shot read-only health snapshot of the DGX host — GPU mode, GPU utilization and compute-app count, nvidia-smi memory and processes, and running containers. Use to answer "what is the DGX doing right now" before deploying, switching GPU mode, or debugging a stuck endpoint. Strictly read-only; never changes state.
---

# dgx-status

A read-only snapshot of the DGX. Answers "what is the box doing right now" before
you deploy, switch modes, or debug a dead endpoint. **Never mutates** — no mode
switch, no up/down, no kill.

## Gather (all read-only, over ssh dgx-llm-1)

```bash
ssh dgx-llm-1 '
  ~/bin/gpu-mode-swap.sh status --json
  nvidia-smi --query-gpu=memory.used,memory.total,utilization.gpu --format=csv,noheader
  nvidia-smi --query-compute-apps=pid,process_name,used_memory --format=csv,noheader
  for p in 9000 8003; do curl -fsS -o /dev/null -w "$p:%{http_code} " http://127.0.0.1:$p/health 2>/dev/null; done; echo
  docker ps --format "{{.Names}} {{.Status}}" 2>/dev/null || echo "docker ps needs sudo"
'
```

## Report

One compact block:
- **mode** (code/research/idle/BROKEN-BOTH) + `gpu_compute_app_count`
- **GPU**: utilization %. NOTE: on GB10 (unified memory) `nvidia-smi`
  `memory.used/total` returns `[N/A]` — don't rely on it. Use the compute-apps
  `used_memory` below (and DCGM/Grafana) for real memory pressure.
- **compute apps**: pid / name / memory — who actually holds the GPU
- **vLLM health**: which of `:9000` / `:8003` answers
- **containers**: running stacks (or note docker needs sudo)

## Flag mismatches

- `idle` but a compute app is present → a training job / Ollama holds the GPU
  directly (switching would fight it — see the `gpu-mode` skill).
- `code` but `:9000` not healthy → the stack didn't come up cleanly.
- `BROKEN-BOTH`, or both ports answering → bad state; surface it, don't fix blindly.
