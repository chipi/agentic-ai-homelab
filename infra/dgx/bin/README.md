# `infra/dgx/bin/` — DGX-host operator scripts

Scripts the operator (and agents) run **on the DGX host** to manage the
shared GPU. Versioned in the repo so changes are reviewable; per-host
config is layered on top via env vars.

## Scripts

| Script | What it does | Recipe |
|---|---|---|
| `gpu-mode-swap.sh` | Toggle which vLLM owns the single GPU (`code` / `research` / `idle`) | [`docs/recipes/gpu-mode-swap.md`](../../../docs/recipes/gpu-mode-swap.md) |

---

## `gpu-mode-swap.sh`

A single DGX-class GPU can't host the coder-next and autoresearch vLLM
stacks at the same time (both want ~90% of VRAM). This script is the
explicit, scriptable contract for which one owns the GPU right now.

### Install on the DGX

```bash
# Make ~/bin a symlink target (one-time):
mkdir -p ~/bin
ln -sf ~/agentic-ai-homelab/infra/dgx/bin/gpu-mode-swap.sh ~/bin/gpu-mode-swap.sh

# Optional shell alias for ergonomics:
echo 'alias gpu-mode="~/bin/gpu-mode-swap.sh"' >> ~/.zshrc
source ~/.zshrc

# Verify:
gpu-mode-swap.sh status
```

The symlink lets `git pull` ship script updates without re-installing.

### Human usage

```bash
gpu-mode-swap.sh                # show current state (default = status)
gpu-mode-swap.sh code           # bring coder-next vLLM up, autoresearch down
gpu-mode-swap.sh research       # bring autoresearch up, coder-next down
gpu-mode-swap.sh idle           # both down — frees GPU for ML training / Ollama
```

### Agent usage (the contract)

Agents should treat this script as the **authoritative GPU coordinator**.
Before invoking a local vLLM (e.g. before pointing a tool at
`http://<dgx>:9000/v1`), verify the right mode is active.

**Always call by absolute path** — the `gpu-mode` zsh alias does not load
in the non-interactive shells agents typically run in:

```bash
~/bin/gpu-mode-swap.sh --mode-only            # → "code" | "research" | "idle" | "BROKEN-BOTH"
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
| `0` | Requested mode is active (or no-op confirmed) |
| `1` | Target vLLM did not start listening within timeout |
| `2` | Usage error / unknown mode |
| `3` | Config error (compose dir missing) |

**Idempotency:** re-running the same mode is a no-op. Safe to call before
every local-vLLM request without measurable cost.

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
# ~/.config/gpu-mode.env (sourced if present, gitignored — operator-local)
GPU_MODE_RESEARCH_DIR=/home/operator/Projects/podcast_scraper/infra/dgx/vllm-autoresearch
GPU_MODE_CODER_PORT=9000
GPU_MODE_RESEARCH_PORT=8003
GPU_MODE_DOCKER="sudo docker"
GPU_MODE_START_TIMEOUT=180
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
| `GPU_MODE_START_TIMEOUT` | `120` | Seconds to wait for target port |

### Common failure modes

- **`BROKEN-BOTH` reported.** Someone bypassed the script and brought a
  stack up manually. The next `code` / `research` call recovers by
  bringing both down first.
- **`compose dir missing` (exit 3).** The autoresearch dir lives in the
  `podcast_scraper` repo by default — if you don't have that repo cloned,
  set `GPU_MODE_RESEARCH_DIR` or just use `code` / `idle`.
- **GPU memory stays high after `idle`.** Zombie vLLM worker. See the
  recipe's troubleshooting section — usually `pkill -9 -f vllm`.
- **Port doesn't come up within 120s.** First-run model download or CUDA
  graph compile. Bump `GPU_MODE_START_TIMEOUT=300`, or pre-warm the
  compose manually once.

### What "agent-friendly" means here

- Absolute path invocation (no alias dependency).
- Machine-readable output (`--json`, `--mode-only`).
- Color auto-disables for non-TTY captures.
- All human logs to stderr; stdout reserved for structured output.
- Stable exit codes per situation.
- Idempotent — safe to call defensively before every local-vLLM request.
- No interactive prompts (with sudoers configured).
- Versioned in the repo — agents see updates via `git pull`.
