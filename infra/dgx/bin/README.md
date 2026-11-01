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

Each mode decides three things: which **main LLM** holds the GPU, whether the
**translate vLLM** (:8005, 29 GiB) runs beside it, and whether the **Ollama daemon**
runs. Only one main LLM at a time, and Ollama never beside a vLLM (#63). Operator's
design, 2026-11-01:

| Mode | Main LLM | translate :8005 | Ollama daemon | Use it for |
|---|---|---|---|---|
| `prod` | prod-vllm :8003 (`Qwen3-30B-A3B FP4`) | started | stopped | prod serving + the nightly |
| `ollama` | Ollama :11434, pinned `qwen3.5:35b` warmed (24h) | started | started | the podcast pipeline on Ollama |
| `research-vllm` | autoresearch vLLM :8003 (`Qwen3-30B-A3B FP4`) | stopped | stopped | the autoresearch pipeline |
| `research-ollama` | Ollama :11434, any model, room for ~90 GiB | stopped | started | research and eval runs, incl. the large models |
| `code` | coder-next vLLM :9000 (`Qwen3-Coder-Next-FP8`) | stopped | stopped | coding assistants |
| `judging {a\|b\|n\|x}` | one judge vLLM :8003 (a=Qwen3-30B, b=Llama-3.3-70B, n=Qwen3-Next-80B, x=Nemotron-120B) | stopped | stopped | the multi-judge sweep |
| `free` | — | stopped | left as is | free the GPU (all but the speech services) |
| `status` *(default)* | read-only | | | print the current state |

**The speech services — `faster-whisper` (:8000), `pyannote` (:8001), `moss` (:8004)
— run in every mode and no mode touches them** (own stacks under `/opt/…`, ~5 GiB
together; prod's nightly needs them, so they stay up even in code/judging). The
script only checks they answer.

GPU memory measured 2026-11-01: translate 29 GiB, prod-vllm 25 GiB, the three speech
services ~5 GiB together, ~121 GiB usable. That is why the large Ollama models
(nemotron-super 120B, mistral-medium 128B, ~90 GiB) belong in `research-ollama`, where
translate is stopped.

`status` / `--mode-only` reports the mode from which vLLM runs, so `ollama` and
`research-ollama` both read `free` there; `status` also prints whether the Ollama
daemon and translate are up. `research` is still accepted as the old name of
`research-vllm`.

```bash
gpu-mode-swap.sh                    # show current state (default = status)
gpu-mode-swap.sh prod               # prod-vllm + translate
gpu-mode-swap.sh ollama             # Ollama (pinned model warm) + translate
gpu-mode-swap.sh research-vllm      # autoresearch vLLM only
gpu-mode-swap.sh research-ollama    # Ollama only, room for the large models
gpu-mode-swap.sh code               # coder-next vLLM only
gpu-mode-swap.sh judging x          # one judge vLLM only
gpu-mode-swap.sh free               # no vLLM, no translate
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
