# GPU mode-swap — toggle coder-LLM vs autoresearch-LLM on a single GPU

**Date:** 2026-06-12 (v0.1 inline template) → 2026-06-13 (v0.2 promoted to repo)
**Status:** v0.2 — script lives at [`infra/dgx/bin/gpu-mode-swap.sh`](https://github.com/chipi/agentic-ai-homelab/blob/main/infra/dgx/bin/gpu-mode-swap.sh); config via env vars (no fill-in required)
**Reach:** runs on DGX directly (no remote invocation)

A single DGX-class GPU can't host the coder-next vLLM and the autoresearch
vLLM at the same time — both want ~90% of VRAM in their respective profiles.
This recipe is the toggle: one command swaps which one is up, or brings
both down for idle / ML training / batch jobs.

The script is version-controlled in the repo and reads its config from env
vars with sensible defaults. The legend below documents the defaults —
override any of them via env vars or `~/.config/gpu-mode.env`, see
[`infra/dgx/bin/README.md`](https://github.com/chipi/agentic-ai-homelab/blob/main/infra/dgx/bin/README.md).

> **Default config (env-var overridable).**
>
> | Knob | Default | Env var |
> |---|---|---|
> | Coder compose dir | `<repo>/infra/vllm/coder-next` | `GPU_MODE_CODER_DIR` |
> | Research compose dir | `~/Projects/podcast_scraper/infra/dgx/vllm-autoresearch` | `GPU_MODE_RESEARCH_DIR` |
> | Coder vLLM port | `9000` | `GPU_MODE_CODER_PORT` |
> | Research vLLM port | `8003` | `GPU_MODE_RESEARCH_PORT` |
> | Coder service name | `vllm-coder-next` | `GPU_MODE_CODER_SVC` |
> | Research service name | `vllm-autoresearch` | `GPU_MODE_RESEARCH_SVC` |
> | Docker command | `sudo docker` | `GPU_MODE_DOCKER` |
> | Start timeout (s) | `120` | `GPU_MODE_START_TIMEOUT` |

---

## Why this exists

Both vLLM composes are configured to claim most of GPU memory:

- `coder-next` runs with `--gpu-memory-utilization 0.92` on `<coder-port>`
- `autoresearch` runs with `--gpu-memory-utilization 0.60` on `<research-port>`

Running them together either fails OOM at startup or thrashes — they're
mutex by design. Plus Ollama (`:11434`) takes a slice when actively
serving. The mode-swap is the explicit, scriptable contract for which
workload owns the GPU right now.

Three modes:

| Mode | What's up | When |
|---|---|---|
| `code` | coder-next vLLM | Day-to-day opencode / Claude Code work with local model |
| `research` | autoresearch vLLM | Running podcast_scraper batch jobs / eval harness |
| `idle` | neither | ML training, manual `nvidia-smi`-watching, freeing the box |

---

## Quick reference

```bash
gpu-mode                       # → show current state
gpu-mode code                  # → switch to coder-next
gpu-mode research              # → switch to autoresearch
gpu-mode idle                  # → bring both down
gpu-mode status                # → same as no-arg
gpu-mode status --mode-only    # → just "code" / "research" / "idle" (agent-friendly)
gpu-mode code --json           # → switch + machine-readable result on stdout
```

Or if you didn't install the alias (agents: always use this form):

```bash
~/bin/gpu-mode-swap.sh code
```

---

## The script

The script lives in the repo at
[`infra/dgx/bin/gpu-mode-swap.sh`](https://github.com/chipi/agentic-ai-homelab/blob/main/infra/dgx/bin/gpu-mode-swap.sh).
Versioned, agent-friendly (supports `--json`, `--mode-only`, `--no-color`,
auto-disables color for non-TTY), env-var configurable (no placeholders
to fill in for the default homelab layout).

Co-located reference (install, agent contract, exit codes, output modes,
sudo expectation, env vars, common failure modes):
[`infra/dgx/bin/README.md`](https://github.com/chipi/agentic-ai-homelab/blob/main/infra/dgx/bin/README.md).

### Shell wrapper (optional, in `~/.zshrc`)

```bash
alias gpu-mode='~/bin/gpu-mode-swap.sh'
```

Then `gpu-mode code` ⏎ from anywhere on the DGX.

---

## Install

```bash
# Symlink the repo script into ~/bin so `git pull` ships updates:
mkdir -p ~/bin
ln -sf ~/agentic-ai-homelab/infra/dgx/bin/gpu-mode-swap.sh ~/bin/gpu-mode-swap.sh
echo 'export PATH="$HOME/bin:$PATH"' >> ~/.zshrc   # if ~/bin isn't on PATH already
echo 'alias gpu-mode="~/bin/gpu-mode-swap.sh"' >> ~/.zshrc
source ~/.zshrc
```

Defaults assume your repo clone is at `~/agentic-ai-homelab/` and
podcast_scraper at `~/Projects/podcast_scraper/`. Override paths via
`~/.config/gpu-mode.env` if your layout differs — see
[`infra/dgx/bin/README.md`](https://github.com/chipi/agentic-ai-homelab/blob/main/infra/dgx/bin/README.md).

Verify:

```bash
gpu-mode status
```

Should print current mode + GPU memory used.

---

## Verification (first runs)

After each transition, three things should be true:

1. **The intended port is listening.** `ss -lnt | grep :<port>`
2. **The "other" port is NOT listening.** Otherwise mode-swap silently
   failed to bring down the prior mode.
3. **GPU memory used dropped** (after `down`) then rose (after `up`).
   If it stays high after `down`, a zombie process is holding VRAM —
   see troubleshooting.

```bash
gpu-mode code
sleep 5
ss -lntH | grep -E ":(<coder-port>|<research-port>)\b"  # only coder-port should appear
nvidia-smi --query-gpu=memory.used --format=csv,noheader
```

---

## Troubleshooting

### `wait_for_port` times out

vLLM start can take longer than 120s on first run (downloading model, CUDA
graph compile). Bump `wait_for_port "$start_port"` second arg to `300`,
or pre-warm by running the compose once manually.

If it's not first-run: check `cd <compose-dir> && sudo docker compose logs --tail=200`
— most failures are `HF_TOKEN` missing or model revision mismatch.

### Both listening (`BROKEN-BOTH`)

Manual mistake — someone brought one up without the script. The script
handles this by bringing both down then starting the requested one.

### GPU memory still high after `idle`

Zombie process holding VRAM. The dashboard's `nvitop` pane will show it.
Common culprits:

```bash
# Find what's still on the GPU:
nvidia-smi --query-compute-apps=pid,used_memory,process_name --format=csv,noheader

# Kill orphan vLLM workers (after compose down):
pkill -9 -f vllm
sleep 2
nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits
```

### Compose `down` succeeds but port still listening

Container is gone but kernel hasn't reclaimed the socket. Usually
self-clears within ~10s; if persistent, something else (host process,
another container) is bound to that port.

---

## Future improvements (not done)

- **Healthcheck-aware wait** — instead of port-listening, poll
  `curl localhost:<port>/v1/models` to confirm vLLM actually responds.
- **Pre-warmed swap** — keep the *idle* compose's image layers warm via
  `docker compose pull` on a cron, so `up` doesn't pay download cost.
- **Auto-idle hook** — systemd timer that runs `gpu-mode idle` if no
  client has hit either vLLM for N minutes (frees GPU for opportunistic
  Ollama use).
- **Mode = `ollama-only`** — explicit fourth mode that brings both vLLM
  composes down AND ensures Ollama is up. Currently `idle` leaves Ollama
  state alone.
- **observability metric** — push current-mode as a custom Grafana label
  so dashboards can show "what owned the GPU at time T".

---

## Quick reference card

```
gpu-mode               # show status
gpu-mode code          # coder-next vLLM up, autoresearch down
gpu-mode research      # autoresearch up, coder-next down
gpu-mode idle          # both down

Verify port:           ss -lnt | grep :<port>
Verify GPU process:    nvidia-smi --query-compute-apps=pid,used_memory,process_name --format=csv,noheader
Kill zombie vLLM:      pkill -9 -f vllm
```
