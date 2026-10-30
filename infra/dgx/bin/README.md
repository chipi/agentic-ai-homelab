# `infra/dgx/bin/` — DGX-host operator scripts

Scripts the operator (and agents) run **on the DGX host** to manage the
shared GPU. Versioned in the repo so changes are reviewable; per-host
config is layered on top via env vars.

## Scripts

| Script | What it does | Recipe |
|---|---|---|
| `gpu-mode-swap.sh` | Toggle which vLLM owns the single GPU (`code` / `research` / `prod` / `ollama` / `free`) | [`docs/recipes/gpu-mode-swap.md`](../../../docs/recipes/gpu-mode-swap.md) |

---

## `gpu-mode-swap.sh`

A single DGX-class GPU can't host the coder-next and autoresearch vLLM
stacks at the same time (both want ~90% of VRAM). This script is the
explicit, scriptable contract for which one owns the GPU right now.

### Install on the DGX

The DGX checkout is **ops-owned** (`/home/ops/agentic-ai-homelab`) — everything on
the box runs as the `ops` user, not a personal account. Put the script on the
system `PATH` via a symlink into the checkout so any user runs it bare:

```bash
# one-time, as ops (or with sudo):
sudo ln -sf /home/ops/agentic-ai-homelab/infra/dgx/bin/gpu-mode-swap.sh \
            /usr/local/bin/gpu-mode-swap.sh

# verify:
gpu-mode-swap.sh status
```

The symlink into the checkout lets `git pull` (as ops) ship script updates without
re-installing. The script derives its repo root from its own location, so no path
config is needed after a `git pull`.

### The modes — what each one is about

The single GPU has **one vLLM slot**. Every mode is really "**what occupies the
vLLM slot**" (plus, for `prod`, whether the pinned Ollama model is warmed).

**The always-on ML services — `pyannote` (:8001), `faster-whisper`/speaches
(:8000), `moss` (:8004) — are NEVER touched by any mode.** They are the podcast
pipeline's production inference services and stay running in every mode; the
script only *checks* they're up. Only the vLLM composes (and the pinned Ollama
model) are swapped.

| Mode | vLLM slot | Pinned Ollama model | Frees the ~78 GB vLLM? | Use it for |
|---|---|---|---|---|
| `code` | coder-next vLLM (:9000, `Qwen3-Coder-Next-FP8`) | — | no (coder occupies it) | coding assistants |
| `research` | autoresearch vLLM (:8003, `Qwen3-30B-A3B FP4`) | — | no (research occupies it) | the autoresearch pipeline |
| `judging {a\|b\|n\|x}` | one judge vLLM (a=Qwen3-30B, b=Llama-3.3-70B, n=Qwen3-Next-80B, x=Nemotron-120B) | — | no | the multi-judge sweep |
| `prod` | **empty** | **warm** (`qwen3.5:35b`, keep_alive 24h) | yes | the podcast pipeline (LLM served by Ollama, not vLLM) |
| `free` | **empty** | cold | yes (**max free memory**) | reclaim the whole GPU — before a fresh vLLM start, or to park the box |
| `status` *(default)* | — (read-only) | — | — | print the current mode |

**`prod` vs `free`:** identical at the vLLM level (both empty the slot, both leave
the ML services up). The *only* difference is `prod` warms the pinned Ollama model
(~30 GB) for the pipeline; `free` leaves Ollama cold for **maximum free memory**.
Because the mode is detected from *which vLLM owns the GPU*, `status`/`--mode-only`
reports **`free`** for both (it can't see the Ollama warm) — expected, not a bug.

```bash
gpu-mode-swap.sh                # show current state (default = status)
gpu-mode-swap.sh code           # coder-next vLLM up, others down
gpu-mode-swap.sh research       # autoresearch vLLM up, others down
gpu-mode-swap.sh prod           # prod-serving vLLM up, others down (:8003, 64k)
gpu-mode-swap.sh ollama         # no vLLM; Ollama warm (podcast pipeline); ML services checked
gpu-mode-swap.sh free           # no vLLM, Ollama cold — maximum free memory
```

### Agent usage (the contract)

Agents should treat this script as the **authoritative GPU coordinator**.
Before invoking a local vLLM (e.g. before pointing a tool at
`http://<dgx>:9000/v1`), verify the right mode is active.

**Always call by absolute path** — the `gpu-mode` zsh alias does not load
in the non-interactive shells agents typically run in:

```bash
~/bin/gpu-mode-swap.sh --mode-only            # → "code" | "research" | "free" | "BROKEN-BOTH"
~/bin/gpu-mode-swap.sh code --json            # switch + machine-readable result
~/bin/gpu-mode-swap.sh status --json          # current state, machine-readable
```

**Output modes:**

| Flag | Effect |
|---|---|
| (none) | Human-readable, colored, all output to stderr |
| `--json` | Single JSON object on stdout, logs still on stderr |
| `--mode-only` | Just the mode string on stdout (status only) |
| `--no-color` | Strip ANSI codes from human output |

Color auto-disables when stdout/stderr isn't a TTY, so most agent capture
patterns just work without `--no-color`.

**JSON shape:**

```json
{
  "mode": "code",
  "success": true,
  "gpu_util_pct": 42,
  "gpu_compute_app_count": 1,
  "compute_apps_before": 0,
  "compute_apps_after": 1,
  "port": 9000
}
```

**Why util + app count, not VRAM:** GB10 (Grace+Blackwell) uses unified
memory — there's no separate VRAM chip, so `nvidia-smi
--query-gpu=memory.used` returns `[N/A]`. `utilization.gpu` and compute-app
count work on every nvidia-smi variant and give the same "did the swap
take effect" signal the VRAM delta used to give on discrete GPUs.

**Exit codes:**

| Code | Meaning |
|---|---|
| `0` | Every stack the mode needs serves its expected model (prod: `:8003` **and** `:8005`) |
| `1` | That end state was not reached — a stack not serving within `GPU_MODE_START_TIMEOUT`, or its container exited |
| `2` | Usage error / unknown mode |
| `3` | Config error (compose dir missing) |
| `4` | Another swap is already running (its log is named) |

**Detached, logged, checked (2026-10-30).** Every mode except `status` re-runs itself
under `setsid -w nohup` and writes everything to
`~/.local/state/gpu-mode/swap-<UTC>-<mode>.log` (`last.log` points at the newest). The
caller is given the log path and follows it; if the caller's SSH session drops or it is
killed, the swap carries on to the end. "Serving" means `/health` is 200 **and**
`/v1/models` lists the expected id (`GPU_MODE_PRODVLLM_MODEL`, `GPU_MODE_TRANSLATE_MODEL`).
The log always ends with `MODE=<mode> OK` or `MODE=<mode> FAILED: <reason>`, so the outcome
can be read after the fact:

```bash
sudo -u ops tail -1 /home/ops/.local/state/gpu-mode/last.log    # MODE=prod OK
```

`--foreground` runs inline (tests, debugging). Tests: `bash infra/dgx/bin/gpu-mode-swap.test.sh`
(stub docker/curl/systemctl, no GPU needed).

**Re-running:** the same mode tears nothing down. It starts only what is missing (e.g.
translate after a prod swap that was cut short) and re-checks that everything serves.

### Sudo expectation

The script calls `sudo docker compose up -d` / `down`. For unattended
agent use, either:

1. Add a sudoers `NOPASSWD` rule for `/usr/bin/docker` (recommended
   on a personal homelab DGX), or
2. Set `GPU_MODE_DOCKER=docker` if you've configured rootless Docker.

Without one of these, the script hangs on a password prompt under an
agent.

### Per-host config

Defaults are sensible for this repo's layout. To override, either export
the env vars in the calling shell or drop a `~/.config/gpu-mode.env`:

```bash
# ~/.config/gpu-mode.env (sourced if present, gitignored — operator-local).
# Homelab stacks (coder-next, judges) derive from the script's own checkout; the product
# stacks (prod-vllm, translate, autoresearch) live in chipi/infra and default to
# <checkout parent>/chipi-infra/infra/ai/vllm/<stack>. The DGX sets them explicitly:
# GPU_MODE_PRODVLLM_DIR=/home/ops/chipi-infra/infra/ai/vllm/prod-vllm  (same for TRANSLATE, RESEARCH)
GPU_MODE_CODER_PORT=9000
GPU_MODE_RESEARCH_PORT=8003
GPU_MODE_DOCKER="sudo docker"
```

Available variables (all optional):

| Var | Default | Purpose |
|---|---|---|
| `GPU_MODE_CODER_DIR` | `<repo>/infra/vllm/coder-next` | Coder compose dir |
| `GPU_MODE_CODER_PORT` | `9000` | Coder vLLM port |
| `GPU_MODE_CODER_SVC` | `vllm-coder-next` | Coder compose service name |
| `GPU_MODE_RESEARCH_DIR` | `~/Projects/podcast_scraper/infra/dgx/vllm-autoresearch` | Autoresearch compose dir |
| `GPU_MODE_RESEARCH_PORT` | `8003` | Autoresearch vLLM port |
| `GPU_MODE_RESEARCH_SVC` | `vllm-autoresearch` | Autoresearch service name |
| `GPU_MODE_DOCKER` | `sudo docker` | Docker command prefix |
| `GPU_MODE_SUDO` | `sudo` | Privilege prefix for host cmds (e.g. `systemctl restart ollama`); `""` if root/passwordless |
| `GPU_MODE_START_TIMEOUT` | `600` | Seconds a stack may take from `compose up` to serving (slowest cold load measured: translate, ~400 s) |
| `GPU_MODE_PRODVLLM_MODEL` | `NVFP4/Qwen3-30B-A3B-Instruct-2507-FP4` | Id prod-vllm must list on `/v1/models` (`""` = any) |
| `GPU_MODE_TRANSLATE_MODEL` | `google/translategemma-12b-it` | Id translate must list on `/v1/models` (`""` = any) |
| `GPU_MODE_STATE_DIR` | `~/.local/state/gpu-mode` | Swap logs, `last.log`, the lock |

### Common failure modes

- **`BROKEN-BOTH` reported.** Someone bypassed the script and brought a
  stack up manually. The next `code` / `research` call recovers by
  bringing both down first.
- **`compose dir missing` (exit 3).** The autoresearch dir lives in the
  `podcast_scraper` repo by default — if you don't have that repo cloned,
  set `GPU_MODE_RESEARCH_DIR` or just use `code` / `free`.
- **GPU memory stays high after `free`.** Zombie vLLM worker. See the
  recipe's troubleshooting section — usually `pkill -9 -f vllm`.
- **`FAILED: … not serving … within 600s`.** First-run model download or CUDA
  graph compile, or the stack serves a different model id than expected. Read the
  swap log, then `docker logs <container>`; re-run the same mode to finish once fixed.

### What "agent-friendly" means here

- Absolute path invocation (no alias dependency).
- Machine-readable output (`--json`, `--mode-only`).
- Color auto-disables for non-TTY captures.
- All human logs to stderr; stdout reserved for structured output.
- Stable exit codes per situation.
- Re-runnable — the same mode starts only what is missing and re-checks the rest.
- No interactive prompts (with sudoers configured).
- Versioned in the repo — agents see updates via `git pull`.
