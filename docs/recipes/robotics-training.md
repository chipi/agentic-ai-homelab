# Robotics training on the DGX (Microduck)

## Why this exists

The robotics lab (`chipi/robotics-lab`) trains walking policies for Pollen Robotics' Microduck with
[`microduck_rl`](https://github.com/pollen-robotics/microduck_rl): mjlab (MuJoCo Warp on CUDA) and rsl_rl
PPO, Python 3.12 via uv. It needs a CUDA GPU; the DGX's GB10 is the one we have. Training holds the GPU
for an hour or more, so it is a GPU mode like the vLLM slots: `gpu-mode-swap.sh robotics` brings the
training stack up, every other mode brings it down, and `status` says `robotics` while it runs, so no
other agent mistakes the GPU for free.

## Quick reference

```bash
# on the DGX
sudo -u ops /home/ops/agentic-ai-homelab/infra/robotics/microduck/prepare.sh   # once, and after a pin change
~/bin/gpu-mode-swap.sh robotics          # every vLLM and Ollama down; training up
~/bin/gpu-mode-swap.sh --mode-only       # robotics, while it runs
sudo docker logs -f robotics-train       # uv sync, then the trainer's output
~/bin/gpu-mode-swap.sh prod              # stops the training (no save on stop: see Measured), prod back
```

## What runs where

| What | Where |
|---|---|
| The stack | `infra/robotics/microduck/docker-compose.yml` in the ops checkout (`/home/ops/agentic-ai-homelab`), container `robotics-train`, as uid 1001 (ops) |
| The image | `ghcr.io/astral-sh/uv:python3.12-bookworm`, pinned by digest; nothing is installed on the host |
| The training code | `/opt/robotics/microduck_rl`, the commit pinned in `prepare.sh` (change it in a reviewed commit) |
| The venv, uv's cache, uv's Python | `/opt/robotics/cache` (the first `uv sync` pulls ~2 GB of CUDA wheels) |
| Checkpoints, TensorBoard logs | `/opt/robotics/microduck_rl/logs/` (rsl_rl's default) |
| Its log | `docker logs robotics-train` (Alloy ships container logs) |

The run: `uv sync --frozen`, then `uv run train Mjlab-Velocity-Flat-MicroDuck --env.scene.num-envs 4096`,
bounded by `timeout` (2 h by default), SIGINT at the end. Settings, in `infra/robotics/microduck/.env`
on the DGX (not in git), as for the vLLM stacks:

| Variable | Default | |
|---|---|---|
| `ROBOTICS_MEM_LIMIT` | `64g` | the container's memory cap: GB10 memory is one pool for CPU and GPU (121 GiB) |
| `ROBOTICS_MAX_RUNTIME` | `2h` | one run's bound |
| `ROBOTICS_NUM_ENVS` | `4096` | parallel environments |
| `ROBOTICS_LOGGER` | `tensorboard` | mjlab's default is `wandb`, which stops at once without an API key (the first run, 2026-11-13) |
| `ROBOTICS_TRAIN_ARGS` | | more trainer flags, e.g. `--agent.resume True --agent.load-checkpoint ...` to resume |

## When the DGX may leave prod

Prod serves the Close Listening pipeline. The nightly runs at 00:00Z and infra keeps 23:45Z to 03:00Z
clear (chipi/infra IADR-007): be back in prod by 23:30Z (prod's cold start is ~7 minutes). Ask the
operator for a window; check that prod is idle first (`docker logs --since 30m vllm-prod-vllm`).

## Once, before the first run

```bash
sudo install -d -o ops -g ops /opt/robotics          # an admin, once
sudo -u ops /home/ops/agentic-ai-homelab/infra/robotics/microduck/prepare.sh
```

## Verification

- `~/bin/gpu-mode-swap.sh --mode-only` says `robotics` while `robotics-train` runs, `free` after it ended.
- `sudo docker stats --no-stream robotics-train` stays under the cap; `nvidia-smi` shows the trainer.
- Leaving the mode: `robotics-train` is gone, and its log ends with the trainer's own exit.

## Troubleshooting

- **The mode ends at once:** `docker logs robotics-train`. A failed `uv sync` (the wheels' download;
  `UV_HTTP_TIMEOUT` is 600) or a CPU-only torch (the repo binds torch to the CUDA index on aarch64).
- **Killed by the cap (exit 137):** the run needs more than `ROBOTICS_MEM_LIMIT`; lower
  `ROBOTICS_NUM_ENVS`, or raise the cap from a measured number.

## Measured

The first run, 2026-11-13 21:33Z to 21:44Z (`Mjlab-Velocity-Flat-MicroDuck`, 4096 envs, microduck_rl
`0daab160d3fb`):

| | |
|---|---|
| Swap prod to robotics | 1 minute, the image pull included |
| First `uv sync` | 142 packages prepared in 1 m 45 s (the uv cache keeps them for later runs) |
| torch | `2.9.1+cu129`, CUDA available. It warns that it is built for capability 8.0 to 12.0 and the GB10 is 12.1; training ran on the GPU anyway |
| Warp | 1.12.0, "NVIDIA GB10 (122 GiB, sm_121)"; compiling its kernels the first time takes about a minute |
| The trainer's GPU memory | 5.1 GB, flat from the start to iteration 140 |
| The container's memory | 2.6 GiB of the 64 GiB cap |
| GPU | 90 to 91 % busy, 43 to 51 °C |
| Iteration time | 2.78 s at 4096 envs: 100 iterations in ~5 minutes |
| The task's own length | 50,000 iterations (~38 h). The repo's HF jobs use `--agent.max_iterations 4000` (~3 h 5 min here) |
| Swap back to prod | 6 m 18 s (the vLLMs' cold load) |

What it taught:

- **mjlab logs to Weights & Biases by default** and stops at once without an API key: the stack now
  passes `--agent.logger tensorboard` (`ROBOTICS_LOGGER`).
- **rsl_rl does not save on a stop.** Stopped at about iteration 140, the run kept only `model_0.pt`
  (and its ONNX). Set `--agent.save_interval` (e.g. 100: one save every ~5 minutes) in
  `ROBOTICS_TRAIN_ARGS`, and stop just after a save.
- **The memory is small.** ~8 GB in all would fit beside prod on the numbers, but prod with another GPU
  user is what the DGX's hard wedges were tied to (see gpu-mode-swap.sh), so robotics stays its own mode.

A full run: `ROBOTICS_TRAIN_ARGS="--agent.max_iterations 4000 --agent.save_interval 100"` and
`ROBOTICS_MAX_RUNTIME=3h30m`, in a window of about 3 h 45 min with the swaps; after the nightly is done
(it runs from 00:00Z; infra keeps 23:45Z to 03:00Z clear).
