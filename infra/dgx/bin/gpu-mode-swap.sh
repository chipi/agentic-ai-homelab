#!/usr/bin/env bash
# gpu-mode-swap.sh — toggle which vLLM owns the GPU on a single-GPU DGX host.
#
# A single GPU can't host the coder-next vLLM and the autoresearch vLLM at
# the same time (both want ~90% of VRAM). This script is the explicit,
# scriptable contract for who owns the GPU right now.
#
# Modes: code | research | idle | prod | status (default)
#
#   prod — podcast_scraper pipeline: no vLLM, Ollama warm with the pinned
#          summary/GI/KG model (see PROD_LLM_MODEL), whisper + pyannote checked.
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
#   GPU_MODE_SUDO            Privilege prefix for host commands like
#                            `systemctl restart ollama` (default "sudo";
#                            set to "" when already root / passwordless)
#   GPU_MODE_START_TIMEOUT   Seconds to wait for target port (default 120)
#   GPU_MODE_RESEARCH_MIN_FREE_GIB  Free VRAM (GiB) required before starting
#                            the autoresearch vLLM (default 73 — matches
#                            --gpu-memory-utilization=0.6 on the GB10's ~121
#                            GiB usable, not the 128 GB nominal)
#   GPU_MODE_OLLAMA_FLUSH_TIMEOUT   Seconds to wait for Ollama GPU memory to
#                            free after `systemctl restart ollama` (default 30)
#   GPU_MODE_GPU_TOTAL_GIB   Total GPU memory (GiB) for the free-VRAM estimate,
#                            since nvidia-smi memory.total reads N/A on GB10 (default 121)
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

# Autoresearch compose lives under the homelab repo (same layout as
# coder-next / judge-a / judge-b), NOT under a checked-out podcast_scraper.
# The old default pointed at ``$HOME/Projects/podcast_scraper/infra/dgx/…``
# which never existed for the operator user and resolved to
# ``/opt/actions-runner/Projects/…`` for the GHA runner — both wrong.
RESEARCH_DIR="${GPU_MODE_RESEARCH_DIR:-$REPO_ROOT/infra/vllm/autoresearch}"
RESEARCH_PORT="${GPU_MODE_RESEARCH_PORT:-8003}"
RESEARCH_SVC="${GPU_MODE_RESEARCH_SVC:-vllm-autoresearch}"

# Judging mode — two sequential judge vLLMs for the autoresearch multi-judge
# sweep. Only one may be up at a time (same GPU as coder/research). The
# sweep script calls ``gpu-mode-swap.sh judging a`` before phase 2 and
# ``judging b`` before phase 3.
JUDGE_A_DIR="${GPU_MODE_JUDGE_A_DIR:-$REPO_ROOT/infra/vllm/judge-a}"
JUDGE_A_PORT="${GPU_MODE_JUDGE_A_PORT:-8003}"
JUDGE_A_SVC="${GPU_MODE_JUDGE_A_SVC:-vllm-judge-a}"

JUDGE_B_DIR="${GPU_MODE_JUDGE_B_DIR:-$REPO_ROOT/infra/vllm/judge-b}"
JUDGE_B_PORT="${GPU_MODE_JUDGE_B_PORT:-8003}"
JUDGE_B_SVC="${GPU_MODE_JUDGE_B_SVC:-vllm-judge-b}"

# judge-qwen-next (nvidia/Qwen3-Next-80B-A3B-Instruct-NVFP4) — Round 3
# successor to judge-a for the multi-judge sweep. Added 2026-07-03.
JUDGE_QWEN_NEXT_DIR="${GPU_MODE_JUDGE_QWEN_NEXT_DIR:-$REPO_ROOT/infra/vllm/judge-qwen-next}"
JUDGE_QWEN_NEXT_PORT="${GPU_MODE_JUDGE_QWEN_NEXT_PORT:-8003}"
JUDGE_QWEN_NEXT_SVC="${GPU_MODE_JUDGE_QWEN_NEXT_SVC:-vllm-judge-qwen-next}"

# judge-nemotron (NVIDIA-Nemotron-3-Super-120B-A12B-NVFP4) — Round 2
# cross-vendor eval-tuned judge for the multi-judge sweep. Added
# 2026-07-03.
JUDGE_NEMOTRON_DIR="${GPU_MODE_JUDGE_NEMOTRON_DIR:-$REPO_ROOT/infra/vllm/judge-nemotron}"
JUDGE_NEMOTRON_PORT="${GPU_MODE_JUDGE_NEMOTRON_PORT:-8003}"
JUDGE_NEMOTRON_SVC="${GPU_MODE_JUDGE_NEMOTRON_SVC:-vllm-judge-nemotron}"

DOCKER_CMD="${GPU_MODE_DOCKER:-sudo docker}"
SUDO="${GPU_MODE_SUDO-sudo}"                    # host-privilege prefix; "" if root
START_TIMEOUT="${GPU_MODE_START_TIMEOUT:-120}"

# research-mode GPU prep — Ollama shares the GPU and is flushed before vLLM
RESEARCH_MIN_FREE_GIB="${GPU_MODE_RESEARCH_MIN_FREE_GIB:-73}"
OLLAMA_FLUSH_TIMEOUT="${GPU_MODE_OLLAMA_FLUSH_TIMEOUT:-30}"
GPU_TOTAL_GIB="${GPU_MODE_GPU_TOTAL_GIB:-121}"   # GB10 usable ~121.7 GiB; memory.total reads N/A

# ── parse args ───────────────────────────────────────────────────────────

JSON=0
MODE_ONLY=0
NO_COLOR=0
MODE=""
JUDGING_SUB=""

while (( $# )); do
    case "$1" in
        --json)       JSON=1 ;;
        --mode-only)  MODE_ONLY=1 ;;
        --no-color)   NO_COLOR=1 ;;
        -h|--help)
            sed -n '2,30p' "$SCRIPT_PATH" | sed 's/^# \{0,1\}//'
            exit 0
            ;;
        code|research|idle|prod|status) MODE="$1" ;;
        judging)
            MODE="judging"
            # judging requires a sub-arg: a, b, n (qwen-next), or x (nemotron)
            shift
            if [[ $# -eq 0 || ! "$1" =~ ^[abnx]$ ]]; then
                echo "usage: $0 judging {a|b|n|x} [--json] [--mode-only] [--no-color]" >&2
                exit 2
            fi
            JUDGING_SUB="$1"
            ;;
        *)
            echo "usage: $0 [code|research|idle|prod|status|judging {a|b|n|x}] [--json] [--mode-only] [--no-color]" >&2
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

# ── research-mode GPU preparation (research slot only) ───────────────────
# Ollama's systemd service keeps models resident in GPU memory even when idle.
# On a fresh autoresearch vLLM start that can leave too little free VRAM, and
# vLLM aborts at CUDA init if free is under what --gpu-memory-utilization needs.
# Restart Ollama to drop its models (they reload on demand — cold start is
# acceptable), then wait until enough VRAM is free before starting vLLM.

gpu_free_gib() {
    # GB10 unified memory reports total/used/free as [N/A] in nvidia-smi; but
    # per-process used_memory IS available via --query-compute-apps. Sum it and
    # subtract from the known total (env GPU_MODE_GPU_TOTAL_GIB) for free GiB.
    # On nvidia-smi failure, returns empty string (sentinel) rather than a nonzero
    # exit — a nonzero return trips set -e at the caller's command-substitution site.
    # This makes a genuine failure distinguishable from a real "0 MiB used" reading.
    local raw used_mib
    if ! raw="$(nvidia-smi --query-compute-apps=used_memory \
                 --format=csv,noheader,nounits 2>/dev/null)"; then
        echo ""   # sentinel: nvidia-smi failed; caller detects via non-numeric output
        return 0
    fi
    used_mib="$(awk '{s+=$1} END{print s+0}' <<<"$raw")"
    awk -v tot="$GPU_TOTAL_GIB" -v used="${used_mib:-0}" \
        'BEGIN{ printf "%.0f", tot - used/1024 }'
}

prepare_gpu_for_research() {
    log "research: flushing Ollama GPU models before vLLM start"
    if $SUDO systemctl restart ollama; then
        ok "ollama restarted — models drop from GPU, reload on demand"
    else
        warn "could not restart ollama (absent / no sudo?) — continuing"
    fi
    local free="" smi_fails=0
    for ((i=0; i<OLLAMA_FLUSH_TIMEOUT; i++)); do
        free="$(gpu_free_gib)"
        if [[ "$free" =~ ^[0-9]+$ ]]; then
            smi_fails=0   # reset blind counter on a good read
            if (( RESEARCH_MIN_FREE_GIB <= free )); then
                ok "GPU free ${free} GiB (need ${RESEARCH_MIN_FREE_GIB}) — ready"
                return 0
            fi
        else
            # nvidia-smi returned no output — driver hiccup, binary absent, or sudo issue.
            # Don't spin the full timeout on a deterministic failure; abort after 3
            # consecutive misses with a message distinct from the below-threshold case.
            smi_fails=$(( smi_fails + 1 ))
            if (( smi_fails >= 3 )); then
                warn "nvidia-smi failed ${smi_fails} consecutive times — cannot read VRAM; starting vLLM blind (may OOM)"
                return 0
            fi
        fi
        sleep 1
    done
    warn "GPU free ${free:-?} GiB below ${RESEARCH_MIN_FREE_GIB} GiB after ${OLLAMA_FLUSH_TIMEOUT}s — starting vLLM anyway (may OOM)"
}

remove_stale_research_container() {
    # A prior failed boot leaves an Exited container; `compose up` then fails
    # with a name Conflict. Remove it — but never a running one. A single
    # `docker inspect` reads the state atomically; the old two-`docker ps`
    # check could race if the container's state changed between the calls.
    local name="$RESEARCH_SVC" state
    state="$($DOCKER_CMD inspect -f '{{.State.Status}}' "$name" 2>/dev/null)" || state=""
    if [[ -n "$state" && "$state" != "running" ]]; then
        log "removing $state $name container (avoids compose name conflict)"
        $DOCKER_CMD rm -f "$name" 1>&2 \
            || warn "could not remove $state $name container — compose up may hit a name conflict"
    fi
}

# Container-name detection: port 8003 is shared across autoresearch +
# judge-a + judge-b (tailscale ACL only permits 8003 + 11434 out of the DGX),
# so we can't tell them apart by listening port. ``docker ps`` gives us the
# exact container that owns the GPU right now.
running_containers() {
    $DOCKER_CMD ps --format '{{.Names}}' 2>/dev/null
}

current_mode() {
    local names; names="$(running_containers)"
    local code_up=0 research_up=0 judge_a_up=0 judge_b_up=0 judge_qwen_next_up=0 judge_nemotron_up=0
    grep -qx "$CODER_SVC"    <<<"$names" && code_up=1
    grep -qx "$RESEARCH_SVC" <<<"$names" && research_up=1
    grep -qx "$JUDGE_A_SVC"  <<<"$names" && judge_a_up=1
    grep -qx "$JUDGE_B_SVC"  <<<"$names" && judge_b_up=1
    grep -qx "$JUDGE_QWEN_NEXT_SVC" <<<"$names" && judge_qwen_next_up=1
    grep -qx "$JUDGE_NEMOTRON_SVC" <<<"$names" && judge_nemotron_up=1
    local total=$((code_up + research_up + judge_a_up + judge_b_up + judge_qwen_next_up + judge_nemotron_up))
    if   (( total > 1 ));           then echo "BROKEN-BOTH"
    elif (( code_up ));             then echo "code"
    elif (( research_up ));         then echo "research"
    elif (( judge_a_up ));          then echo "judging-a"
    elif (( judge_b_up ));          then echo "judging-b"
    elif (( judge_qwen_next_up ));  then echo "judging-qwen-next"
    elif (( judge_nemotron_up ));   then echo "judging-nemotron"
    else                                 echo "idle"
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

# Wait for a vLLM's /health endpoint to return 200. vLLM binds its port as
# soon as the ASGI server starts — but /health returns 200 ONLY when the
# model has finished loading (weights + CUDA graphs + KV cache init). If
# a client hits /v1/chat/completions before /health is 200 the request
# hangs / times out. This is the correct readiness signal for a swap.
wait_for_health() {
    local port=$1 timeout=${2:-$START_TIMEOUT}
    local waited=0
    while (( waited < timeout )); do
        if curl -fsS --max-time 3 "http://127.0.0.1:${port}/health" >/dev/null 2>&1; then
            return 0
        fi
        sleep 5
        waited=$((waited + 5))
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

# Bring every known vLLM compose down. Called before starting a target when
# the current mode isn't a clean single-owner state (e.g. BROKEN-BOTH), or
# by ``action_idle``. Passing ``$1 = <target-dir>`` skips only that one so
# the caller can then bring it up cleanly.
stop_all_composes() {
    local except="${1:-}"
    for d in "$CODER_DIR" "$RESEARCH_DIR" "$JUDGE_A_DIR" "$JUDGE_B_DIR" "$JUDGE_QWEN_NEXT_DIR" "$JUDGE_NEMOTRON_DIR"; do
        [[ "$d" == "$except" ]] && continue
        [[ -d "$d" ]] && compose_down "$d" || true
    done
}

# Also flush Ollama before starting any vLLM — Ollama holds GPU memory for
# recently-served models even when idle, which OOM-crashes a vLLM boot that
# expects ~73 GB free. We unload every resident model via Ollama's own
# /api/generate {keep_alive: 0} — no daemon restart, no root required
# (the previous ``sudo systemctl restart ollama`` broke the GHA self-hosted
# runner because its systemd unit sets NoNewPrivileges=true, blocking sudo).
# Models reload cold on the next inference request (~30-60 s each), same
# cost as the old restart path.
#
# OLLAMA_HOST override lets the caller point at a non-default endpoint;
# defaults to the DGX-local socket the daemon already listens on.
flush_ollama() {
    local host="${OLLAMA_HOST:-http://127.0.0.1:11434}"
    # If daemon isn't reachable at all, nothing to flush — quiet no-op.
    curl -fsS --max-time 3 "${host}/api/ps" >/dev/null 2>&1 || return 0
    local resident
    resident="$(curl -fsS --max-time 3 "${host}/api/ps" \
        | python3 -c 'import json,sys
try:
    for m in json.load(sys.stdin).get("models", []):
        print(m["name"])
except Exception:
    pass' 2>/dev/null)" || true
    if [[ -z "$resident" ]]; then
        return 0
    fi
    log "flushing Ollama GPU-resident models via /api/generate keep_alive=0"
    while IFS= read -r name; do
        [[ -z "$name" ]] && continue
        dim "unloading: $name"
        curl -fsS --max-time 5 -X POST "${host}/api/generate" \
             -H 'Content-Type: application/json' \
             -d "$(printf '{"model":"%s","keep_alive":0}' "$name")" \
             >/dev/null 2>&1 || warn "unload $name failed (proceeding)"
    done <<< "$resident"
    # Ollama drops the models synchronously on request, but give the
    # runtime a beat to actually release the CUDA context before the
    # caller starts the next vLLM boot.
    sleep 2
}

action_status() {
    local mode; mode=$(current_mode)
    if (( MODE_ONLY )); then
        echo "$mode"
        return 0
    fi
    log "current state"
    case "$mode" in
        code)         ok "coder-next vLLM up on :$CODER_PORT" ;;
        research)     ok "autoresearch vLLM up on :$RESEARCH_PORT" ;;
        judging-a)    ok "judge-a vLLM up on :$JUDGE_A_PORT" ;;
        judging-b)    ok "judge-b vLLM up on :$JUDGE_B_PORT" ;;
        judging-qwen-next) ok "judge-qwen-next vLLM up on :$JUDGE_QWEN_NEXT_PORT" ;;
        judging-nemotron)  ok "judge-nemotron vLLM up on :$JUDGE_NEMOTRON_PORT" ;;
        idle)         dim "all vLLM composes are down" ;;
        BROKEN-BOTH)  warn "MULTIPLE listening — GPU-contention failure mode" ;;
    esac
    dim "GPU: $(gpu_state_line)"
    ((JSON)) && emit_json "$mode" true || true
}

action_code()     { do_swap "code"     "$CODER_DIR"    "$CODER_PORT"; }
action_research() { do_swap "research" "$RESEARCH_DIR" "$RESEARCH_PORT"; }
action_judging_a() { do_swap "judging-a" "$JUDGE_A_DIR" "$JUDGE_A_PORT"; }
action_judging_b() { do_swap "judging-b" "$JUDGE_B_DIR" "$JUDGE_B_PORT"; }
action_judging_n() { do_swap "judging-qwen-next" "$JUDGE_QWEN_NEXT_DIR" "$JUDGE_QWEN_NEXT_PORT"; }
action_judging_x() { do_swap "judging-nemotron"  "$JUDGE_NEMOTRON_DIR"  "$JUDGE_NEMOTRON_PORT"; }

action_idle() {
    log "→ idle (bringing all vLLM composes down)"
    local apps_before; apps_before=$(gpu_compute_app_count)
    stop_all_composes
    sleep 2
    local apps_after; apps_after=$(gpu_compute_app_count)
    ok "compute apps ${apps_before}→${apps_after}; now: $(gpu_state_line)"
    ((JSON)) && emit_json "idle" true "compute_apps_before=${apps_before}" "compute_apps_after=${apps_after}" || true
}

# ── prod (podcast_scraper pipeline) ──────────────────────────────────────
#
# The pipeline's three GPU consumers are faster-whisper (:8000), pyannote
# (:8001) and Ollama (:11434) — none of them is a vLLM. A vLLM sitting in the
# research slot holds ~79 GB and starves them, so "prod" is precisely: no vLLM
# at all, plus the LLM the pipeline is actually evaluated against, kept warm.
#
# The model is PINNED, not incidental. ``qwen3.5:35b`` is the #928 summary/GI/KG
# championship winner (finale 5.00/5 Sonnet, 4.90 GPT-5.4, 100% judge agreement)
# and the 2026-07 judges matrix reconfirmed it ("June's champion holds up").
# Changing it is a decision that invalidates those evals, so it lives here as one
# named constant rather than being whatever happened to be loaded.
#
# Unlike the vLLM modes this does NOT flush Ollama — in prod, Ollama *is* the point.
#
# Note: `status` will report `idle`, because mode is derived from which vLLM owns
# the GPU and prod deliberately runs none. That is accurate: no vLLM owns it.
PROD_LLM_MODEL="${GPU_MODE_PROD_LLM_MODEL:-qwen3.5:35b}"
PROD_WHISPER_PORT="${GPU_MODE_PROD_WHISPER_PORT:-8000}"
PROD_DIARIZE_PORT="${GPU_MODE_PROD_DIARIZE_PORT:-8001}"
PROD_MOSS_PORT="${GPU_MODE_PROD_MOSS_PORT:-8004}"

action_prod() {
    log "→ prod (pipeline: no vLLM; Ollama serves the pinned LLM)"
    local apps_before; apps_before=$(gpu_compute_app_count)

    stop_all_composes
    sleep 2

    local host="${OLLAMA_HOST:-http://127.0.0.1:11434}"
    local llm_ok=0
    if ! curl -fsS --max-time 3 "${host}/api/ps" >/dev/null 2>&1; then
        warn "Ollama unreachable at ${host} — the pipeline's summary/GI/KG stages will fail"
    else
        log "warming pinned prod model: ${PROD_LLM_MODEL} (cold load can take ~1-2 min)"
        if curl -fsS --max-time 600 -X POST "${host}/api/generate" \
                -H 'Content-Type: application/json' \
                -d "$(printf '{"model":"%s","prompt":"ok","keep_alive":"24h","stream":false}' "$PROD_LLM_MODEL")" \
                >/dev/null 2>&1; then
            ok "Ollama warm: ${PROD_LLM_MODEL} (keep_alive=24h)"
            llm_ok=1
        else
            warn "could not warm ${PROD_LLM_MODEL} — pulled? try: ollama pull ${PROD_LLM_MODEL}"
        fi
    fi

    local svc_ok=1
    if curl -fsS --max-time 5 -o /dev/null "http://127.0.0.1:${PROD_WHISPER_PORT}/v1/models" 2>/dev/null; then
        ok "faster-whisper up on :${PROD_WHISPER_PORT}"
    else
        warn "faster-whisper NOT responding on :${PROD_WHISPER_PORT}"; svc_ok=0
    fi
    if curl -fsS --max-time 5 -o /dev/null "http://127.0.0.1:${PROD_DIARIZE_PORT}/v1/models" 2>/dev/null; then
        ok "pyannote up on :${PROD_DIARIZE_PORT}"
    else
        warn "pyannote NOT responding on :${PROD_DIARIZE_PORT}"; svc_ok=0
    fi
    if curl -fsS --max-time 5 -o /dev/null "http://127.0.0.1:${PROD_MOSS_PORT}/v1/models" 2>/dev/null; then
        ok "MOSS up on :${PROD_MOSS_PORT}"
    else
        warn "MOSS NOT responding on :${PROD_MOSS_PORT} (transcription falls back to faster-whisper)"
    fi

    local apps_after; apps_after=$(gpu_compute_app_count)
    ok "compute apps ${apps_before}→${apps_after}; now: $(gpu_state_line)"

    local all_ok=false
    [[ $llm_ok -eq 1 && $svc_ok -eq 1 ]] && all_ok=true
    ((JSON)) && emit_json "prod" "$all_ok" "llm=${PROD_LLM_MODEL}" "compute_apps_before=${apps_before}" "compute_apps_after=${apps_after}" || true
    [[ "$all_ok" == true ]] || return 1
}

do_swap() {
    local target=$1 start_dir=$2 start_port=$3
    require_dir "$start_dir"
    local current; current=$(current_mode)

    if [[ "$current" == "$target" ]]; then
        log "already in $target mode — no-op"
        action_status
        return 0
    fi

    log "→ $target (current: $current)"
    local apps_before; apps_before=$(gpu_compute_app_count)

    # Bring down every other compose (including the current owner, if any).
    # This is the single-owner invariant: exactly one vLLM at a time.
    stop_all_composes "$start_dir"
    sleep 2

    # Flush Ollama's GPU-resident models so vLLM boot doesn't OOM. Only
    # needed on Ollama→vLLM transitions but idempotent — safe to always
    # run before compose_up.
    flush_ollama

    # research slot shares the GPU with Ollama — flush it + clear any stale
    # container before starting. Code slot is intentionally untouched here.
    if [[ "$target" == "research" ]]; then
        prepare_gpu_for_research
        remove_stale_research_container
    fi

    compose_up "$start_dir"

    if ! wait_for_port "$start_port"; then
        warn "$target vLLM did not bind :$start_port within ${START_TIMEOUT}s"
        ((JSON)) && emit_json "$target" false "compute_apps_before=${apps_before}" "port=$start_port" || true
        exit 1
    fi

    # Port is bound but the model may still be loading. Poll /health until
    # 200 (or timeout) so callers know the vLLM is actually ready to serve.
    log "waiting for $target /health (model load)"
    if wait_for_health "$start_port"; then
        local apps_after; apps_after=$(gpu_compute_app_count)
        ok "$target vLLM ready on :$start_port (compute apps ${apps_before}→${apps_after}; $(gpu_state_line))"
        ((JSON)) && emit_json "$target" true "compute_apps_before=${apps_before}" "compute_apps_after=${apps_after}" "port=$start_port" || true
    else
        warn "$target vLLM port :$start_port bound but /health not 200 within ${START_TIMEOUT}s — model still loading? check 'docker logs $target'"
        ((JSON)) && emit_json "$target" false "compute_apps_before=${apps_before}" "port=$start_port" || true
        exit 1
    fi
}

# ── dispatch ─────────────────────────────────────────────────────────────

case "$MODE" in
    status)    action_status ;;
    code)      action_code ;;
    research)  action_research ;;
    idle)      action_idle ;;
    prod)      action_prod ;;
    judging)
        case "$JUDGING_SUB" in
            a) action_judging_a ;;
            b) action_judging_b ;;
            n) action_judging_n ;;
            x) action_judging_x ;;
            *) echo "usage: $0 judging {a|b}" >&2; exit 2 ;;
        esac
        ;;
    *)
        echo "usage: $0 [code|research|idle|prod|status|judging {a|b}] [--json] [--mode-only] [--no-color]" >&2
        exit 2
        ;;
esac
