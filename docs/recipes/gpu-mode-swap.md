# GPU mode-swap — toggle coder-LLM vs autoresearch-LLM on a single GPU

**Date:** 2026-06-12
**Status:** v0.1 — script template; operator fill-in for compose paths
**Reach:** runs on DGX directly (no remote invocation)

A single DGX-class GPU can't host the coder-next vLLM and the autoresearch
vLLM at the same time — both want ~90% of VRAM in their respective profiles.
This recipe is the toggle: one command swaps which one is up, or brings
both down for idle / ML training / batch jobs.

> **Placeholder legend.**
>
> | Placeholder | What it stands for |
> |---|---|
> | `<coder-compose-dir>` | Directory holding the coder vLLM compose, e.g. `~/docker-compose/vllm-Qwen3-Coder-Next` |
> | `<research-compose-dir>` | Directory holding the autoresearch vLLM compose, e.g. `~/Projects/podcast_scraper/infra/dgx/vllm-autoresearch` |
> | `<coder-port>` | Listening port for the coder vLLM (e.g. `9000`) |
> | `<research-port>` | Listening port for the autoresearch vLLM (e.g. `8003`) |
> | `<coder-svc>` | Service name inside the coder compose (e.g. `vllm-coder-next`) |
> | `<research-svc>` | Service name inside the autoresearch compose (e.g. `vllm-autoresearch`) |

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
gpu-mode               # → show current state
gpu-mode code          # → switch to coder-next
gpu-mode research      # → switch to autoresearch
gpu-mode idle          # → bring both down
gpu-mode status        # → same as no-arg
```

Or if you didn't install the wrapper:

```bash
~/bin/gpu-mode-swap.sh code
```

---

## The script

### `~/bin/gpu-mode-swap.sh`

```bash
#!/usr/bin/env bash
# gpu-mode-swap.sh — toggle which vLLM owns the GPU.
#
# Modes: code | research | idle | status (default)
#
# Idempotent: re-running the same mode is a no-op (skips bring-down + bring-up).
# Per global AGENTS.md #6: each invocation reports cost (GPU mem freed/allocated)
# and final exit state.

set -euo pipefail

CODER_DIR="<coder-compose-dir>"
RESEARCH_DIR="<research-compose-dir>"
CODER_PORT=<coder-port>
RESEARCH_PORT=<research-port>
CODER_SVC="<coder-svc>"
RESEARCH_SVC="<research-svc>"

MODE="${1:-status}"

# ── helpers ──────────────────────────────────────────────────────────────

C_OK='\033[32m'; C_BAD='\033[31m'; C_DIM='\033[2m'; C_HDR='\033[1;36m'; C_RST='\033[0m'

log()   { printf "${C_HDR}[gpu-mode]${C_RST} %s\n" "$*"; }
ok()    { printf "  ${C_OK}✓${C_RST} %s\n" "$*"; }
warn()  { printf "  ${C_BAD}✗${C_RST} %s\n" "$*"; }
dim()   { printf "  ${C_DIM}%s${C_RST}\n" "$*"; }

is_listening() {
    ss -lntH 2>/dev/null | awk -v p=":$1$" '$4 ~ p {print; exit}' | grep -q ':'
}

gpu_mib_used() {
    nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits 2>/dev/null | head -1
}

compose_up()   { ( cd "$1" && sudo docker compose up -d ); }
compose_down() { ( cd "$1" && sudo docker compose down ); }

current_mode() {
    local code_up=0 research_up=0
    is_listening "$CODER_PORT"    && code_up=1
    is_listening "$RESEARCH_PORT" && research_up=1
    if   (( code_up && research_up )); then echo "BROKEN-BOTH"
    elif (( code_up ));                then echo "code"
    elif (( research_up ));            then echo "research"
    else                                    echo "idle"
    fi
}

wait_for_port() {
    local port=$1 timeout=${2:-120}
    for ((i=0; i<timeout; i++)); do
        is_listening "$port" && return 0
        sleep 1
    done
    return 1
}

# ── actions ──────────────────────────────────────────────────────────────

action_status() {
    log "current state"
    local mode; mode=$(current_mode)
    case "$mode" in
        code)         ok "coder-next vLLM up on :$CODER_PORT"; dim "research is down" ;;
        research)     ok "autoresearch vLLM up on :$RESEARCH_PORT"; dim "coder is down" ;;
        idle)         dim "both vLLM composes are down" ;;
        BROKEN-BOTH)  warn "BOTH listening — this is the GPU-contention failure mode" ;;
    esac
    dim "GPU mem used: $(gpu_mib_used) MiB"
}

action_code()     { do_swap "code" "$RESEARCH_DIR" "$CODER_DIR" "$CODER_PORT"; }
action_research() { do_swap "research" "$CODER_DIR" "$RESEARCH_DIR" "$RESEARCH_PORT"; }

action_idle() {
    log "→ idle (bringing both down)"
    local before; before=$(gpu_mib_used)
    [[ -d "$CODER_DIR" ]]    && compose_down "$CODER_DIR"    || true
    [[ -d "$RESEARCH_DIR" ]] && compose_down "$RESEARCH_DIR" || true
    sleep 2
    local after; after=$(gpu_mib_used)
    ok "GPU mem ${before}→${after} MiB"
}

do_swap() {
    local target=$1 stop_dir=$2 start_dir=$3 start_port=$4
    local current; current=$(current_mode)

    if [[ "$current" == "$target" ]]; then
        log "already in $target mode — no-op"
        action_status
        return 0
    fi

    log "→ $target (stopping $current, starting $target)"
    local before; before=$(gpu_mib_used)

    if [[ "$current" != "idle" && "$current" != "BROKEN-BOTH" ]]; then
        compose_down "$stop_dir"
        sleep 2
    elif [[ "$current" == "BROKEN-BOTH" ]]; then
        warn "BOTH were up — bringing both down before starting $target"
        compose_down "$CODER_DIR"    || true
        compose_down "$RESEARCH_DIR" || true
        sleep 3
    fi

    compose_up "$start_dir"

    if wait_for_port "$start_port"; then
        local after; after=$(gpu_mib_used)
        ok "$target vLLM listening on :$start_port (GPU mem ${before}→${after} MiB)"
    else
        warn "$target vLLM did not start listening within 120s — check 'docker compose logs'"
        exit 1
    fi
}

# ── dispatch ─────────────────────────────────────────────────────────────

case "$MODE" in
    status|"")  action_status ;;
    code)       action_code ;;
    research)   action_research ;;
    idle)       action_idle ;;
    *)
        echo "usage: $0 [code | research | idle | status]" >&2
        exit 2
        ;;
esac
```

### Shell wrapper (optional, in `~/.zshrc`)

```bash
alias gpu-mode='~/bin/gpu-mode-swap.sh'
```

Then `gpu-mode code` ⏎ from anywhere on the DGX.

---

## Install

```bash
mkdir -p ~/bin
$EDITOR ~/bin/gpu-mode-swap.sh           # paste above, edit placeholders
chmod +x ~/bin/gpu-mode-swap.sh
echo 'export PATH="$HOME/bin:$PATH"' >> ~/.zshrc   # if ~/bin isn't on PATH already
echo 'alias gpu-mode="~/bin/gpu-mode-swap.sh"' >> ~/.zshrc
source ~/.zshrc
```

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
