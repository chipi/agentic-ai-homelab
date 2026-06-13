#!/usr/bin/env bash
# gpu-mode-swap.sh — toggle which vLLM owns the GPU on a single-GPU DGX host.
#
# A single GPU can't host the coder-next vLLM and the autoresearch vLLM at
# the same time (both want ~90% of VRAM). This script is the explicit,
# scriptable contract for who owns the GPU right now.
#
# Modes: code | research | idle | status (default)
#
# Idempotent: re-running the same mode is a no-op. Agent-friendly: supports
# --json (machine-readable), --no-color (strip ANSI), --mode-only (print
# just the current mode). All human-readable logs go to stderr; --json
# output goes to stdout as a single object.
#
# Config — override any of these via env vars (or ~/.config/gpu-mode.env):
#   GPU_MODE_CODER_DIR       Path to coder-next compose dir
#   GPU_MODE_CODER_PORT      Coder vLLM listening port
#   GPU_MODE_CODER_SVC       Coder vLLM compose service name
#   GPU_MODE_RESEARCH_DIR    Path to autoresearch compose dir
#   GPU_MODE_RESEARCH_PORT   Autoresearch vLLM listening port
#   GPU_MODE_RESEARCH_SVC    Autoresearch vLLM compose service name
#   GPU_MODE_DOCKER          Docker command prefix (default "sudo docker";
#                            set to "docker" for rootless setups)
#   GPU_MODE_START_TIMEOUT   Seconds to wait for target port (default 120)
#
# Exit codes:
#   0  success — requested mode is active (or no-op confirmed)
#   1  failed to bring up target (port not listening within timeout)
#   2  usage error / unknown mode
#   3  config error (compose dir missing)

set -euo pipefail

# ── resolve paths ────────────────────────────────────────────────────────

SCRIPT_PATH="$(readlink -f "${BASH_SOURCE[0]}")"
SCRIPT_DIR="$(dirname "$SCRIPT_PATH")"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"

# Optional per-host overrides without exporting env vars manually.
USER_CONFIG="${XDG_CONFIG_HOME:-$HOME/.config}/gpu-mode.env"
[[ -r "$USER_CONFIG" ]] && set -a && source "$USER_CONFIG" && set +a

# ── config (env-var overridable) ─────────────────────────────────────────

CODER_DIR="${GPU_MODE_CODER_DIR:-$REPO_ROOT/infra/vllm/coder-next}"
CODER_PORT="${GPU_MODE_CODER_PORT:-9000}"
CODER_SVC="${GPU_MODE_CODER_SVC:-vllm-coder-next}"

RESEARCH_DIR="${GPU_MODE_RESEARCH_DIR:-$HOME/Projects/podcast_scraper/infra/dgx/vllm-autoresearch}"
RESEARCH_PORT="${GPU_MODE_RESEARCH_PORT:-8003}"
RESEARCH_SVC="${GPU_MODE_RESEARCH_SVC:-vllm-autoresearch}"

DOCKER_CMD="${GPU_MODE_DOCKER:-sudo docker}"
START_TIMEOUT="${GPU_MODE_START_TIMEOUT:-120}"

# ── parse args ───────────────────────────────────────────────────────────

JSON=0
MODE_ONLY=0
NO_COLOR=0
MODE=""

while (( $# )); do
    case "$1" in
        --json)       JSON=1 ;;
        --mode-only)  MODE_ONLY=1 ;;
        --no-color)   NO_COLOR=1 ;;
        -h|--help)
            sed -n '2,30p' "$SCRIPT_PATH" | sed 's/^# \{0,1\}//'
            exit 0
            ;;
        code|research|idle|status) MODE="$1" ;;
        *)
            echo "usage: $0 [code|research|idle|status] [--json] [--mode-only] [--no-color]" >&2
            exit 2
            ;;
    esac
    shift
done

MODE="${MODE:-status}"

# Auto-disable color when stdout is not a TTY, or NO_COLOR is honored.
if [[ -n "${NO_COLOR:-}" ]] || (( NO_COLOR )) || (( JSON )) || ! [[ -t 2 ]]; then
    C_OK=''; C_BAD=''; C_DIM=''; C_HDR=''; C_RST=''
else
    C_OK='\033[32m'; C_BAD='\033[31m'; C_DIM='\033[2m'; C_HDR='\033[1;36m'; C_RST='\033[0m'
fi

# ── helpers (all human output to stderr) ─────────────────────────────────

log()  { (( JSON )) || printf "${C_HDR}[gpu-mode]${C_RST} %s\n" "$*" >&2; }
ok()   { (( JSON )) || printf "  ${C_OK}✓${C_RST} %s\n" "$*" >&2; }
warn() { (( JSON )) || printf "  ${C_BAD}✗${C_RST} %s\n" "$*" >&2; }
dim()  { (( JSON )) || printf "  ${C_DIM}%s${C_RST}\n" "$*" >&2; }

is_listening() {
    ss -lntH 2>/dev/null | awk -v p=":$1$" '$4 ~ p {print; exit}' | grep -q ':'
}

gpu_util_pct() {
    # GPU utilization % — works on both discrete and unified-memory parts.
    # On GB10 (Grace+Blackwell) this is the load-bearing signal since the
    # discrete-VRAM query (memory.used) returns "[N/A]".
    local raw
    raw="$(nvidia-smi --query-gpu=utilization.gpu --format=csv,noheader,nounits 2>/dev/null | head -1 | tr -d ' ')"
    [[ "$raw" =~ ^[0-9]+$ ]] && echo "$raw" || echo ""
}

gpu_compute_app_count() {
    # Count of processes holding a CUDA context. idle → 0, vLLM up → 1,
    # something else grabbed the GPU → >1. Works on every nvidia-smi.
    nvidia-smi --query-compute-apps=pid --format=csv,noheader 2>/dev/null | grep -cE '^[0-9]+$' || echo 0
}

# Compact "util%/N-apps" string for human output. Empty fields render as "?".
gpu_state_line() {
    local u; u="$(gpu_util_pct)"
    local n; n="$(gpu_compute_app_count)"
    echo "util ${u:-?}% / ${n} compute app$([ "$n" = "1" ] || echo s)"
}

compose_up()   { ( cd "$1" && $DOCKER_CMD compose up -d ) >&2; }
compose_down() { ( cd "$1" && $DOCKER_CMD compose down ) >&2; }

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
    local port=$1 timeout=${2:-$START_TIMEOUT}
    for ((i=0; i<timeout; i++)); do
        is_listening "$port" && return 0
        sleep 1
    done
    return 1
}

# Emit JSON result on stdout. Args: <mode> <success(0|1)> [extra k=v pairs]
emit_json() {
    local mode="$1" success="$2"; shift 2
    local util; util="$(gpu_util_pct)"
    local apps; apps="$(gpu_compute_app_count)"
    printf '{"mode":"%s","success":%s,"gpu_util_pct":%s,"gpu_compute_app_count":%s' \
        "$mode" "$success" "${util:-null}" "${apps:-0}"
    while (( $# )); do
        printf ',"%s":%s' "${1%%=*}" "${1#*=}"
        shift
    done
    printf '}\n'
}

require_dir() {
    [[ -d "$1" ]] || { warn "compose dir missing: $1"; exit 3; }
}

# ── actions ──────────────────────────────────────────────────────────────

action_status() {
    local mode; mode=$(current_mode)
    if (( MODE_ONLY )); then
        echo "$mode"
        return 0
    fi
    log "current state"
    case "$mode" in
        code)         ok "coder-next vLLM up on :$CODER_PORT"; dim "research is down" ;;
        research)     ok "autoresearch vLLM up on :$RESEARCH_PORT"; dim "coder is down" ;;
        idle)         dim "both vLLM composes are down" ;;
        BROKEN-BOTH)  warn "BOTH listening — GPU-contention failure mode" ;;
    esac
    dim "GPU: $(gpu_state_line)"
    (( JSON )) && emit_json "$mode" true
}

action_code()     { do_swap "code"     "$RESEARCH_DIR" "$CODER_DIR"    "$CODER_PORT"; }
action_research() { do_swap "research" "$CODER_DIR"    "$RESEARCH_DIR" "$RESEARCH_PORT"; }

action_idle() {
    log "→ idle (bringing both down)"
    local apps_before; apps_before=$(gpu_compute_app_count)
    [[ -d "$CODER_DIR" ]]    && compose_down "$CODER_DIR"    || true
    [[ -d "$RESEARCH_DIR" ]] && compose_down "$RESEARCH_DIR" || true
    sleep 2
    local apps_after; apps_after=$(gpu_compute_app_count)
    ok "compute apps ${apps_before}→${apps_after}; now: $(gpu_state_line)"
    (( JSON )) && emit_json "idle" true "compute_apps_before=${apps_before}" "compute_apps_after=${apps_after}"
}

do_swap() {
    local target=$1 stop_dir=$2 start_dir=$3 start_port=$4
    require_dir "$start_dir"
    local current; current=$(current_mode)

    if [[ "$current" == "$target" ]]; then
        log "already in $target mode — no-op"
        action_status
        return 0
    fi

    log "→ $target (stopping $current, starting $target)"
    local apps_before; apps_before=$(gpu_compute_app_count)

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
        local apps_after; apps_after=$(gpu_compute_app_count)
        ok "$target vLLM listening on :$start_port (compute apps ${apps_before}→${apps_after}; $(gpu_state_line))"
        (( JSON )) && emit_json "$target" true "compute_apps_before=${apps_before}" "compute_apps_after=${apps_after}" "port=$start_port"
    else
        warn "$target vLLM did not start listening within ${START_TIMEOUT}s — check 'docker compose logs'"
        (( JSON )) && emit_json "$target" false "compute_apps_before=${apps_before}" "port=$start_port"
        exit 1
    fi
}

# ── dispatch ─────────────────────────────────────────────────────────────

case "$MODE" in
    status)    action_status ;;
    code)      action_code ;;
    research)  action_research ;;
    idle)      action_idle ;;
    *)
        echo "usage: $0 [code|research|idle|status] [--json] [--mode-only] [--no-color]" >&2
        exit 2
        ;;
esac
