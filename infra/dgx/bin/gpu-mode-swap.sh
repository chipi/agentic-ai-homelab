#!/usr/bin/env bash
# gpu-mode-swap.sh — toggle which vLLM owns the GPU on a single-GPU DGX host.
#
# A single GPU can't host the coder-next vLLM and the autoresearch vLLM at
# the same time (both want ~90% of VRAM). This script is the explicit,
# scriptable contract for who owns the GPU right now.
#
# Modes: code | research | free | prod | ollama | status (default)
#
#   prod — production SERVING vLLM slot on :8003 (chipi/infra infra/ai/vllm/prod-vllm).
#          A real vLLM, single-owner-at-a-time like research.
#   ollama — podcast_scraper pipeline: NO vLLM, Ollama warm with the pinned
#          summary/GI/KG model (see OLLAMA_LLM_MODEL), whisper + pyannote checked.
#          Starts the daemon, since any vLLM mode will have stopped it.
#
# OLLAMA vs vLLM — who may hold the GPU:
#
#   Every vLLM mode (code, research, prod, judging-*) STOPS the ollama daemon. It
#   does not merely flush it: flushing unloads resident models but leaves the daemon
#   listening, so one request reloads a model, and that load/unload CYCLE wedged this
#   host three times on 2026-09-15/16, each needing a physical power cycle (#63):
#
#     freeze 1  ollama 15.4 -> 45.1 -> 15.4 GB   died 16 min after the unload, 37.8 GB free
#     freeze 2  ollama  0   -> 29.7 ->  0   GB   died  3 min after the unload, 34.5 GB free
#     freeze 3  ollama  0   -> 23.9 ->  0   GB   died  7 min after the unload, 36.1 GB free
#
#   Every wedge landed MINUTES AFTER the release, with memory already recovered, and
#   the squeeze floor varied 10x (0.97 -> 9.54 GB free) without changing the outcome —
#   so depth was never the trigger, co-residency was. Capping OLLAMA_CONTEXT_LENGTH
#   made the squeeze shallower and the host still wedged.
#
#   Ollama therefore runs only when NO vLLM owns the GPU: the `ollama` and `free`
#   modes. Escape hatch: GPU_MODE_VLLM_STOPS_OLLAMA=0 restores flush-only.
#
#   Observed-vs-inferred: all three wedges were in PROD mode (vllm-prod-vllm resident
#   at 31.38 / 30.47 / 30.57 GB). research, code and judging-* are the same structure
#   — a heavy vLLM co-resident with Ollama — but have not themselves been seen to
#   wedge. The rule is applied on the mechanism, not on three data points.
#
#   AMENDMENT 2026-09-17 — shipped logs contradict part of the above. The rule STANDS
#   (it is the conservative one), but three claims here are now known to be wrong or
#   unsupported. Reconstructed from VictoriaLogs, where each wedge is a gap in DGX log
#   shipping: 09-15 19:10Z->22:00Z, 09-16 00:10Z->06:00Z, plus a partial dip at 09:00Z.
#
#     * "the load/unload CYCLE is the trigger" does not fit wedge 2. The last
#       ollama-metrics line before it reads "Refreshed metrics data: 0 models loaded"
#       — ollama was already empty and idle. There was no cycle to blame.
#     * "only PROD mode wedged" is EXPOSURE, not a property. prod-vllm and
#       autoresearch are the same image (nvcr.io/nvidia/vllm:26.05-py3) and
#       the same flags (--gpu-memory-utilization=0.75, --max-model-len=65536, ipc:host).
#       prod is simply what has been running since the container was created 09-13; the
#       other modes never had the opportunity.
#     * What BOTH wedges actually share is sustained heavy vLLM load with the ollama
#       daemon merely present:
#           wedge 1  19:05Z  prompt 1013.7 tok/s, gen 120.2 tok/s, Running: 4 reqs, ollama 1 model
#           wedge 2  00:03Z  prompt 1839.6 tok/s, gen  73.8 tok/s, Running: 2 reqs, ollama 0 models
#       Neither died at idle. 09-15 carried 200-330 chat/completions per 30min from
#       14:00Z to 18:30Z — ~4.5h of batch — before dying; the next batch resumed 23:00Z
#       and died ~1h in.
#     * The driving client was 100.87.33.61 = `homelab`, the mac mini, relaying through
#       its litellm. So the workload is ours and identifiable, not ambient.
#
#   Still NOT established: why load + an idle daemon would wedge a host with 34-38 GB
#   free, and whether the mini's concurrent log storm contributed. Do not promote any of
#   the above to a cause without a deliberate replay under load — the freezes need a
#   PHYSICAL power cycle, so that is an operator decision, not an agent's.
#
#   ⚠ SUPERSEDED BY WEDGE 4 — read the block at the end of this section FIRST. The
#   "did NOT reproduce" finding below was written at 07:30Z on 2026-09-18 and the host
#   wedged again at 08:27Z the same morning. It is kept because its DATA is still valid
#   (8h of co-residency really did survive); its CONCLUSION is not.
#
#   REPLAY UNDER LOAD, 2026-09-17/18 — the stated mechanism did NOT reproduce.
#
#   An 8-hour operator-run crunch with ollama co-resident on the prod vLLM. Survived:
#   uptime unbroken (boot 2026-09-16 12:35:08 throughout), log shipping continuous
#   across all 20 half-hour buckets with no gap, 0 OOM kills, 0 CUDA/NVML/Xid/illegal-
#   memory events, and 0 error-level lines from the DGX in 10h.
#
#   It was not an idle sit. vLLM sustained 300-584 chat/completions per hour for 7+
#   hours (peak 741.8 tok/s prompt, 2 concurrent). From 02:00Z ollama ran REPEATED
#   load/unload cycles — resident ~6-8 min per hour, four hours running — concurrent
#   with that load. That is the exact cycle blamed above, exercised over and over,
#   for longer than either wedge survived:
#
#     wedge 1      1013.7 tok/s, 4 reqs, ollama 1 model    died after ~4.5h
#     wedge 2      1839.6 tok/s, 2 reqs, ollama 0 models   died after ~1h
#     this replay   741.8 tok/s, 2 reqs, ollama cycling    8h+, no failure
#
#   Caveat, stated so nobody over-reads this: peak intensity was LOWER (741 vs
#   1013/1839 tok/s; 2 concurrent vs 4). This does not prove immunity at the highest
#   load the box has seen. What it does is falsify "the load/unload CYCLE wedges the
#   host" as a sufficient mechanism — the cycle ran for hours under real load and
#   nothing happened.
#
#   What else changed between the wedges and this replay: the mac mini (the client
#   driving both wedges, via its litellm) had ~50,400 log lines/day of pure noise
#   removed at cause on 2026-09-17 — 49,151 VictoriaMetrics parse rejects and 1,239
#   Grafana template errors. Whether that is causally related is UNKNOWN and untested;
#   it is recorded only because it is the other thing that moved.
#
#   THE RULE IS LEFT IN PLACE. One clean replay does not overturn three power cycles,
#   and the failure mode is a hard wedge. Treat this as evidence for revisiting the
#   rule deliberately, not as licence to run co-resident by default.
#
#   ---------------------------------------------------------------------------------
#   WEDGE 4 — 2026-09-18 08:27Z. It reproduced, 57 minutes after the block above was
#   committed. And the evidence points AWAY from software entirely.
#
#   Every telemetry path stopped inside 60 seconds of each other:
#
#     logs                 last 08:27:14Z
#     host memory (/proc)  last 08:27:00Z
#     cadvisor (127 srs)   last 08:27:00Z
#     DCGM (GPU driver)    last 08:28:00Z
#     vLLM engine          last 08:28:00Z
#     alloy self-metrics   last 08:28:00Z
#
#   Those are INDEPENDENT subsystems. A container crash or a GPU hang kills one. All of
#   them stopping together means the host stopped executing — and ping/:8003/ssh were
#   dead FROM THE MINI too, so it is not a laptop-network artifact.
#
#   Thermals in the final 20 minutes (the box had been idle at 38C):
#
#     08:16  47C  95% util   38.9W   <- load starts
#     08:20  65C  96% util   43.1W
#     08:25  68C  96% util   43.5W
#     08:27  70C  96% util   43.9W
#     08:28  71C  96% util   44.2W   <- last sample, still climbing, never plateaued
#
#   Board ACPI zones at 08:28Z: 79.0 / 79.0 / 77.8 / 76.7 / 71.7 / 68.8 / 67.8 C.
#   Hottest board zone 79C vs GPU die 70C = +9C, matching the documented "~10C hotter"
#   offset for this hardware.
#
#   TWO EARLIER CLAIMS IN THIS FILE ARE NOW SUSPECT:
#
#   1. "Every wedge landed MINUTES AFTER the release." At wedge 4 the GPU was pinned at
#      96% util with 2 requests running at the final sample. What LOOKED like a release
#      was one 10s vLLM log line between batches; the GPU never let go. If wedges 1-3
#      were read the same way — from an instantaneous log line rather than GPU util —
#      the "load/unload cycle" theory rests on a misread.
#   2. "depth was never the trigger." Memory held flat at 73.2-73.3 GB free through the
#      entire final window. That part survives: it is NOT memory.
#
#   THE LIKELY CAUSE IS THE HARDWARE, NOT US. NVIDIA GB10 / DGX Spark has a documented
#   "under-load power-off issue" — see github.com/maci0/gb10-thermal-toolkit, which
#   exists solely to work around it, and the NVIDIA forum threads on ACPI zones hitting
#   96-97C with "fans not ramping". Key points from that work:
#
#     * the governing sensor is the BOARD / Grace-CPU ACPI zone, ~10C hotter than the
#       GPU die (confirmed here: 79 vs 70)
#     * danger zone 94-96C; 87-91C is the safe band
#     * power is never the limiter (~49W peak against a ~140W budget) — it is COOLING
#     * mitigations: verify case fan airflow DIRECTION (~18C on affected units), and
#       cap clocks with `nvidia-smi -lgc` around 2200 MHz
#     * after a thermal power-off a unit can latch into a stuck ~14W state — disconnect
#       power for ~5 MINUTES to reset the controller, a quick cycle may not clear it
#
#   HONEST GAP: our hottest zone read 79C, below the documented 94-96C trip. Every zone
#   was still rising at the last sample and we sample at 60s, so it may have spiked in
#   the unobserved final minute — but that is unproven. What IS established is a
#   monotonic 58->79C climb over 12 minutes at a FLAT ~43W with no plateau, which is a
#   cooling signature, not a compute one.
#
#   WE HAVE NO FAN TELEMETRY. The box publishes no tachometer to node_exporter
#   (node_hwmon_fan_rpm absent); cooling is EC/firmware-controlled and invisible to
#   Linux. node_cooling_device_* exists but is PCIe link-speed + CPU throttle states,
#   all reading 0 (nothing ever throttled). So "was the fan spinning" is unanswerable
#   from telemetry — which is itself worth fixing.
#
#   ALERT WE SHOULD HAVE HAD, on metrics already collected:
#     max(node_thermal_zone_temp{cluster="dgx"}) > 85                    (warn)
#     deriv(max(node_thermal_zone_temp{cluster="dgx"})[10m:]) > 1.5      (climbing)
#   The second would have fired ~08:20Z, about seven minutes before the host died.
#
#   THE UNIT IS ALSO `systemctl disable`d ON THE HOST (2026-09-16). Do not "fix" the
#   DGX by re-enabling it. `stop` is runtime-only, so the boot symlink outlived every
#   stop this script performs: the 12:35 power-cycle started ollama 9 seconds into
#   boot, and the host sat back in the wedge-prone state for ~1h40m with nobody aware,
#   because nothing re-applies a mode at boot. Disabling deletes
#   default.target.wants/ollama.service, which is the only part of "prod mode" that
#   did not already survive a reboot — every vLLM stack is `restart: unless-stopped`,
#   so docker restores the mode by itself.
#
#   A boot-time `gpu-mode-swap prod` unit was considered and rejected: current_mode()
#   reads which compose service is up, docker has already restored prod by then, so
#   the swap short-circuits and never reaches stop_ollama_daemon. It would log success
#   and leave ollama running. Forcing it works but tears down the vLLM docker just
#   started, on every boot, and pins reboots to prod even when the box was left in
#   research or judging.
#
#   `ollama` and `free` modes are unaffected: start_ollama_daemon calls `systemctl
#   start`, which does not care whether a unit is enabled. Cost of the trade: after a
#   reboot, anything expecting :11434 without running this script gets connection
#   refused instead of a wedge. That is the intended failure direction.
#
# A SWAP RUNS DETACHED AND ENDS ON A CHECKED STATE (2026-10-30). Twice that day a swap to
# prod ended with translate down and needing a hand start: once the 120 s timeout ran out
# before translate's cold load (~6m40s), once the caller's SSH session was cut mid-run and
# the script died with it. So every mode except `status`:
#   * re-runs itself under `setsid -w nohup` with all output in its own log,
#     ${GPU_MODE_STATE_DIR:-~/.local/state/gpu-mode}/swap-<UTC>-<mode>.log (last.log points
#     at the newest). The caller follows the log and gets the exit code, but a dropped SSH
#     session, a killed caller or Ctrl-C no longer stops the swap. --foreground runs inline.
#   * waits per stack until /health is 200 AND /v1/models lists the expected model id,
#     within GPU_MODE_START_TIMEOUT (default 600 s: slowest cold load measured 400 s).
#   * checks the end state before exiting: prod = :8003 and :8005 both serving their models.
#     Exit 0 means that state was reached; anything short of it exits non-zero.
#   * ends its log with one line, `MODE=<mode> OK` or `MODE=<mode> FAILED: <reason>`.
#   * holds a lock: a second swap while one runs fails at once (exit 4).
#
# Re-running the same mode does not tear anything down: it starts only what is missing
# (e.g. translate after a half-done prod swap) and re-checks that everything serves.
# Agent-friendly: --json (machine-readable result on stdout), --no-color, --mode-only.
#
# RESETTING A MESSED-UP HOST: re-running the same mode does NOT do it. The mode is
# inferred from which compose service is running, not from whether the host is sane,
# so a hand-started ollama or a manually loaded model still reports the current mode.
# Use `--force` to re-run the full swap (stop every compose, stop ollama, bring the
# target back up), or bounce through `free` and back.
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
#   GPU_MODE_START_TIMEOUT   Seconds a stack may take to serve (default 600)
#   GPU_MODE_PRODVLLM_MODEL  Model id prod-vllm must list on /v1/models
#   GPU_MODE_TRANSLATE_MODEL Model id translate must list on /v1/models
#                            ("" = any model; the other slots always accept any)
#   GPU_MODE_STATE_DIR       Where swap logs and the lock live
#                            (default ~/.local/state/gpu-mode)
#   GPU_MODE_RESEARCH_MIN_FREE_GIB  Free VRAM (GiB) required before starting
#                            the autoresearch vLLM (default 73 — matches
#                            --gpu-memory-utilization=0.6 on the GB10's ~121
#                            GiB usable, not the 128 GB nominal)
#   GPU_MODE_OLLAMA_FLUSH_TIMEOUT   Seconds to wait for Ollama GPU memory to
#                            free after `systemctl restart ollama` (default 30)
#   GPU_MODE_GPU_TOTAL_GIB   Total GPU memory (GiB) for the free-VRAM estimate,
#                            since nvidia-smi memory.total reads N/A on GB10 (default 121)
#   GPU_MODE_VLLM_STOPS_OLLAMA  1 (default) = every vLLM mode STOPS the ollama
#                            daemon; 0 = flush resident models only, leaving it
#                            listening. Default is 1 because a listening daemon
#                            reloads on the next request, and that cycle wedged the
#                            host 3x (#63). Requires sudo; if it is blocked the swap
#                            still proceeds and warns rather than failing.
#
# Exit codes:
#   0  success — every stack the mode needs is serving its expected model
#   1  the end state was not reached (a stack not serving within the timeout, or exited)
#   2  usage error / unknown mode
#   3  config error (compose dir missing)
#   4  another swap is already running (its log is named)

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

# autoresearch, prod-vllm and translate are product stacks: they live in chipi/infra
# (infra/ai/vllm/) since 2026-10-30, checked out at ~/chipi-infra, and the DGX's
# ~/.config/gpu-mode.env sets their GPU_MODE_*_DIR. The defaults name that checkout,
# a sibling of this one (not $HOME: root or another user would resolve elsewhere).
INFRA_ROOT="${GPU_MODE_INFRA_ROOT:-$(dirname "$REPO_ROOT")/chipi-infra}"
RESEARCH_DIR="${GPU_MODE_RESEARCH_DIR:-$INFRA_ROOT/infra/ai/vllm/autoresearch}"
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

# prod-vllm — production serving vLLM (chipi/infra infra/ai/vllm/prod-vllm). A copy of the
# autoresearch serving config kept as its own named slot. Same GB10 GPU, same
# :8003 (single-owner-at-a-time) as the other vLLM slots. Distinct from the
# `prod` pipeline mode, which runs no vLLM at all.
PRODVLLM_DIR="${GPU_MODE_PRODVLLM_DIR:-$INFRA_ROOT/infra/ai/vllm/prod-vllm}"
PRODVLLM_PORT="${GPU_MODE_PRODVLLM_PORT:-8003}"
PRODVLLM_SVC="${GPU_MODE_PRODVLLM_SVC:-vllm-prod-vllm}"
# What "prod-vllm serves" means: /v1/models lists this id. The id the stack served on
# 2026-10-30; change it here (or in gpu-mode.env) when chipi/infra changes the model.
PRODVLLM_MODEL="${GPU_MODE_PRODVLLM_MODEL-NVFP4/Qwen3-30B-A3B-Instruct-2507-FP4}"

# translate — the translation vLLM (chipi/infra infra/ai/vllm/translate), TranslateGemma-12B.
#
# THE ONE STACK THAT IS NOT MUTUALLY EXCLUSIVE. Every other slot here shares :8003
# and the single-owner rule; this one has its own port (:8005) and comes up
# ALONGSIDE prod-vllm, because an episode needs translation AND summarization in the
# same pipeline pass (translation runs immediately before summary inside
# generate_episode_metadata). Swapping per episode would mean two model loads per
# episode, which is not a usable shape.
#
# It is therefore brought up BY `prod` mode rather than being a mode of its own, and
# stop_all_composes leaves it alone except when going to `free` (see there).
TRANSLATE_DIR="${GPU_MODE_TRANSLATE_DIR:-$INFRA_ROOT/infra/ai/vllm/translate}"
TRANSLATE_PORT="${GPU_MODE_TRANSLATE_PORT:-8005}"
TRANSLATE_SVC="${GPU_MODE_TRANSLATE_SVC:-vllm-translate}"
TRANSLATE_MODEL="${GPU_MODE_TRANSLATE_MODEL-google/translategemma-12b-it}"
# 1 (default) = `prod` mode also brings the translation vLLM up. Set 0 to serve
# summaries without translation (e.g. reproducing a pre-#2169 run, or freeing the
# memory for a heavier prod model).
TRANSLATE_WITH_PROD="${GPU_MODE_TRANSLATE_WITH_PROD:-1}"

DOCKER_CMD="${GPU_MODE_DOCKER:-sudo docker}"
SUDO="${GPU_MODE_SUDO-sudo}"                    # host-privilege prefix; "" if root
# Per stack, from `compose up` to serving its model. Measured cold loads on 2026-10-30:
# translate up to ~6m40s (400 s), prod-vllm ~5m21s (321 s). The old 120 s, then 300 s, were
# both below the slowest; 600 s is the slowest plus half again.
START_TIMEOUT="${GPU_MODE_START_TIMEOUT:-600}"
STATE_DIR="${GPU_MODE_STATE_DIR:-${XDG_STATE_HOME:-$HOME/.local/state}/gpu-mode}"

# research-mode GPU prep — Ollama shares the GPU and is flushed before vLLM
RESEARCH_MIN_FREE_GIB="${GPU_MODE_RESEARCH_MIN_FREE_GIB:-73}"
OLLAMA_FLUSH_TIMEOUT="${GPU_MODE_OLLAMA_FLUSH_TIMEOUT:-30}"
GPU_TOTAL_GIB="${GPU_MODE_GPU_TOTAL_GIB:-121}"   # GB10 usable ~121.7 GiB; memory.total reads N/A

# ── parse args ───────────────────────────────────────────────────────────

JSON=0
MODE_ONLY=0
NO_COLOR=0
FORCE=0
FOREGROUND=0
MODE=""
JUDGING_SUB=""
ORIG_ARGS=("$@")

while (( $# )); do
    case "$1" in
        --json)       JSON=1 ;;
        --mode-only)  MODE_ONLY=1 ;;
        --no-color)   NO_COLOR=1 ;;
        --force)      FORCE=1 ;;
        --foreground) FOREGROUND=1 ;;
        -h|--help)
            sed -n '2,30p' "$SCRIPT_PATH" | sed 's/^# \{0,1\}//'
            exit 0
            ;;
        code|research|free|prod|ollama|status) MODE="$1" ;;
        judging)
            MODE="judging"
            # judging requires a sub-arg: a, b, n (qwen-next), or x (nemotron)
            shift
            if [[ $# -eq 0 || ! "$1" =~ ^[abnx]$ ]]; then
                echo "usage: $0 judging {a|b|n|x} [--json] [--mode-only] [--no-color] [--force]" >&2
                exit 2
            fi
            JUDGING_SUB="$1"
            ;;
        *)
            echo "usage: $0 [code|research|free|prod|ollama|status|judging {a|b|n|x}] [--json] [--mode-only] [--no-color] [--force] [--foreground]" >&2
            echo "  prod = serving vLLM on :$PRODVLLM_PORT PLUS the co-resident translate vLLM on :$TRANSLATE_PORT" >&2
            echo "         (GPU_MODE_TRANSLATE_WITH_PROD=0 brings up the serving vLLM only)" >&2
            exit 2
            ;;
    esac
    shift
done

MODE="${MODE:-status}"
MODE_LABEL="$MODE${JUDGING_SUB:+-$JUDGING_SUB}"

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

# Stop the swap: the reason becomes the log's last line (see finish) and --json reports it.
FAIL_REASON=""
fail() {
    local code=1
    [[ "$1" =~ ^[0-9]+$ ]] && { code=$1; shift; }
    FAIL_REASON="$*"
    warn "$*"
    ((JSON)) && emit_json "$MODE_LABEL" false || true
    exit "$code"
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
    # do_swap has just STOPPED the daemon (stop_ollama_daemon). `systemctl restart` starts a
    # stopped unit, so restarting here put ollama back up beside every research/prod vLLM —
    # the co-residency #63 forbids. Found 2026-10-30: ollama active since the 21:45Z prod swap.
    # Restart only in flush-only mode, where the daemon is meant to stay up.
    if [[ "${GPU_MODE_VLLM_STOPS_OLLAMA:-1}" != "1" ]]; then
        log "research: flushing Ollama GPU models before vLLM start"
        if $SUDO systemctl restart ollama; then
            ok "ollama restarted — models drop from GPU, reload on demand"
        else
            warn "could not restart ollama (absent / no sudo?) — continuing"
        fi
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

remove_stale_container() {
    # A prior failed boot leaves an Exited container; `compose up` then fails
    # with a name Conflict. Remove it — but never a running one. A single
    # `docker inspect` reads the state atomically; the old two-`docker ps`
    # check could race if the container's state changed between the calls.
    local name="${1:-$RESEARCH_SVC}" state
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
    local code_up=0 research_up=0 prodvllm_up=0 judge_a_up=0 judge_b_up=0 judge_qwen_next_up=0 judge_nemotron_up=0
    grep -qx "$CODER_SVC"    <<<"$names" && code_up=1
    grep -qx "$RESEARCH_SVC" <<<"$names" && research_up=1
    grep -qx "$PRODVLLM_SVC" <<<"$names" && prodvllm_up=1
    grep -qx "$JUDGE_A_SVC"  <<<"$names" && judge_a_up=1
    grep -qx "$JUDGE_B_SVC"  <<<"$names" && judge_b_up=1
    grep -qx "$JUDGE_QWEN_NEXT_SVC" <<<"$names" && judge_qwen_next_up=1
    grep -qx "$JUDGE_NEMOTRON_SVC" <<<"$names" && judge_nemotron_up=1
    local total=$((code_up + research_up + prodvllm_up + judge_a_up + judge_b_up + judge_qwen_next_up + judge_nemotron_up))
    if   (( total > 1 ));           then echo "BROKEN-BOTH"
    elif (( code_up ));             then echo "code"
    elif (( research_up ));         then echo "research"
    elif (( prodvllm_up ));         then echo "prod"
    elif (( judge_a_up ));          then echo "judging-a"
    elif (( judge_b_up ));          then echo "judging-b"
    elif (( judge_qwen_next_up ));  then echo "judging-qwen-next"
    elif (( judge_nemotron_up ));   then echo "judging-nemotron"
    else                                 echo "free"
    fi
}

# The stack's own client key (its .env), so /v1/models can be asked as a client would.
stack_api_key() {
    sed -n 's/^VLLM_API_KEY=//p' "$1/.env" 2>/dev/null | head -1 | tr -d "\"'" || true
}

# A stack SERVES when /health is 200 (vLLM answers it only once weights, CUDA graphs and
# KV cache are up; a bound port alone means nothing) AND /v1/models lists the expected
# model id (any id when none is expected). The key goes to curl on stdin, never argv.
serving_ok() {  # <port> <stack dir> <model id or "">
    local port=$1 dir=$2 model=$3 key body
    curl -fsS --max-time 3 -o /dev/null "http://127.0.0.1:${port}/health" 2>/dev/null || return 1
    key="$(stack_api_key "$dir")"
    body="$(printf 'header = "Authorization: Bearer %s"\n' "$key" \
        | curl -fsS --max-time 5 -K - "http://127.0.0.1:${port}/v1/models" 2>/dev/null)" || return 1
    WANT="$model" python3 -c '
import json, os, sys
try:
    ids = [m.get("id") for m in json.load(sys.stdin).get("data", [])]
except Exception:
    sys.exit(1)
want = os.environ["WANT"]
sys.exit(0 if ((want in ids) if want else ids) else 1)' <<<"$body"
}

# One deadline per stack, from `compose up` to serving. Gives up early only when the
# container is gone or has exited — a restarting or loading one gets the full timeout.
wait_serving() {  # <label> <port> <stack dir> <container> <model id or "">
    local label=$1 port=$2 dir=$3 svc=$4 model=$5
    local start=$SECONDS waited=0 state="" next_note=0
    while (( waited < START_TIMEOUT )); do
        if serving_ok "$port" "$dir" "$model"; then
            ok "$label serving ${model:-a model} on :$port (${waited}s)"
            return 0
        fi
        if [[ -n "$svc" ]]; then
            state="$($DOCKER_CMD inspect -f '{{.State.Status}}' "$svc" 2>/dev/null)" || state="absent"
            if [[ "$state" =~ ^(absent|exited|dead)$ ]] && (( waited >= 20 )); then
                warn "$label container $svc is $state — check 'docker logs $svc'"
                return 1
            fi
        fi
        if (( waited >= next_note )); then
            dim "$label: not serving yet (${waited}s of ${START_TIMEOUT}s, container ${state:-?})"
            next_note=$(( next_note + 60 ))
        fi
        sleep 5
        waited=$(( SECONDS - start ))
    done
    warn "$label not serving ${model:-a model} on :$port within ${START_TIMEOUT}s — check 'docker logs $svc'"
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
    [[ -d "$1" ]] || fail 3 "compose dir missing: $1"
}

# ── actions ──────────────────────────────────────────────────────────────

# Bring every known vLLM compose down. Called before starting a target when
# the current mode isn't a clean single-owner state (e.g. BROKEN-BOTH), or
# by ``action_free``. Passing ``$1 = <target-dir>`` skips only that one so
# the caller can then bring it up cleanly.
stop_all_composes() {
    local except="${1:-}"
    for d in "$CODER_DIR" "$RESEARCH_DIR" "$PRODVLLM_DIR" "$JUDGE_A_DIR" "$JUDGE_B_DIR" "$JUDGE_QWEN_NEXT_DIR" "$JUDGE_NEMOTRON_DIR"; do
        [[ "$d" == "$except" ]] && continue
        [[ -d "$d" ]] && compose_down "$d" || true
    done
}

# Every :8003 slot PLUS the co-resident translate stack. Used by `free`, which must
# leave nothing holding the GPU — stop_all_composes deliberately omits translate so a
# swap INTO prod does not tear down the translator it is about to need.
stop_all_composes_including_translate() {
    stop_all_composes "${1:-}"
    [[ -d "$TRANSLATE_DIR" ]] && compose_down "$TRANSLATE_DIR" || true
}

# Also flush Ollama before starting any vLLM — Ollama holds GPU memory for
# recently-served models even when idle, which OOM-crashes a vLLM boot that
# expects ~73 GB free. We unload every resident model via Ollama's own
# /api/generate {keep_alive: 0} — no daemon restart, no root required
# (``sudo systemctl restart ollama`` fails under a systemd unit that sets
# NoNewPrivileges=true, which blocks sudo).
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

# Flushing is NOT enough for prod. flush_ollama unloads resident models but leaves the
# DAEMON listening, so the next inference request reloads one — and it is that
# allocate/serve/release CYCLE that wedges this host, not the memory depth.
#
# Three wedges on 2026-09-15/16 (chipi/agentic-ai-homelab#63), each needing a physical
# power cycle. Every one of them died 3-16 minutes AFTER ollama released a model, with
# memory already recovered:
#
#   freeze 1  ollama 15.4 -> 45.1 -> 15.4 GB   died 16 min after the unload, 37.8 GB free
#   freeze 2  ollama  0   -> 29.7 ->  0   GB   died  3 min after the unload, 34.5 GB free
#   freeze 3  ollama  0   -> 23.9 ->  0   GB   died  7 min after the unload, 36.1 GB free
#
# Squeeze depth varied 10x (0.97 -> 9.54 GB free) and made no difference to the outcome,
# so capping context (OLLAMA_CONTEXT_LENGTH=32768) made the squeeze shallower without
# stopping the wedge. Stopping the daemon removes the trigger instead of softening it.
#
# Set GPU_MODE_VLLM_STOPS_OLLAMA=0 to keep the old flush-only behaviour.
# The ollama-metrics sidecar polls :11434 every ~15s forever and logs an ERROR on every
# failure. With ollama deliberately stopped that is 5,760 error lines a day about a service
# we chose to shut down — noise that also MASKS a real ollama failure, since a dead ollama and
# an intentionally-absent one look identical in the log. It is a third-party image
# (ghcr.io/norskhelsenett/ollama-metrics) so the polling cannot be tuned; bind its lifecycle to
# ollama's instead. `restart: unless-stopped` means an explicit `docker stop` sticks until we
# start it again, which is exactly the semantics wanted here.
ollama_sidecar() {  # $1 = start|stop
    docker inspect ollama-metrics >/dev/null 2>&1 || return 0
    if docker "$1" ollama-metrics >/dev/null 2>&1; then
        dim "ollama-metrics sidecar ${1}ped"
    else
        warn "could not $1 the ollama-metrics sidecar (it will keep polling a dead :11434)"
    fi
}

stop_ollama_daemon() {
    if [[ "${GPU_MODE_VLLM_STOPS_OLLAMA:-1}" != "1" ]]; then
        dim "GPU_MODE_VLLM_STOPS_OLLAMA=0 — leaving the ollama daemon up (flush only)"
        flush_ollama
        return 0
    fi
    # Unload first so the CUDA context is released cleanly rather than torn down under us.
    flush_ollama
    if ! systemctl is-active --quiet ollama 2>/dev/null; then
        ok "ollama daemon already stopped"
        # The sidecar too: this early return skipped it, so with ollama already down (the
        # DGX's normal state in prod mode) the exporter kept polling :11434 and logged an
        # error every 15 s, from 2026-09-18 until it was noticed on 2026-10-17.
        ollama_sidecar stop
        return 0
    fi
    log "stopping the ollama daemon (prod mode: no load/unload cycles on this host)"
    if $SUDO systemctl stop ollama 2>/dev/null; then
        ok "ollama stopped — nothing can trigger a model load while prod owns the GPU"
        ollama_sidecar stop
        return 0
    fi
    # Same constraint flush_ollama documents: a systemd unit with NoNewPrivileges=true
    # blocks sudo. Do NOT abort the
    # swap over it — prod vLLM still comes up — but be loud, because the wedge risk is back.
    warn "could not stop ollama (no sudo / absent). Models are flushed but the DAEMON IS UP:"
    warn "  a single inference request will reload a model and re-open the wedge window (#63)."
    warn "  stop it by hand on the DGX:  sudo systemctl stop ollama"
    return 0
}

# ollama mode has to undo what prod mode did, or it silently serves nothing: action_ollama
# only ever WARNED when the endpoint was unreachable, it never started the daemon.
start_ollama_daemon() {
    if systemctl is-active --quiet ollama 2>/dev/null; then
        return 0
    fi
    log "starting the ollama daemon"
    if $SUDO systemctl start ollama 2>/dev/null; then
        # The socket accepts connections before the runtime is ready to serve.
        local i
        for i in $(seq 1 30); do
            curl -fsS --max-time 2 "${OLLAMA_HOST:-http://127.0.0.1:11434}/api/ps" >/dev/null 2>&1 && break
            sleep 1
        done
        ok "ollama daemon started"
        ollama_sidecar start
    else
        warn "could not start ollama (no sudo / absent) — start it on the DGX: sudo systemctl start ollama"
    fi
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
        prod)         ok "prod serving vLLM up on :$PRODVLLM_PORT" ;;
        judging-a)    ok "judge-a vLLM up on :$JUDGE_A_PORT" ;;
        judging-b)    ok "judge-b vLLM up on :$JUDGE_B_PORT" ;;
        judging-qwen-next) ok "judge-qwen-next vLLM up on :$JUDGE_QWEN_NEXT_PORT" ;;
        judging-nemotron)  ok "judge-nemotron vLLM up on :$JUDGE_NEMOTRON_PORT" ;;
        free)         dim "all vLLM composes are down" ;;
        BROKEN-BOTH)  warn "MULTIPLE listening — GPU-contention failure mode" ;;
    esac
    # The co-resident translator, reported SEPARATELY from the mode. It is deliberately
    # excluded from current_mode()'s single-owner count -- it is legitimately up alongside
    # :8003, so counting it there would report BROKEN-BOTH for the correct state. But an
    # operator still has to be able to see whether translation is available, so say so.
    if grep -qx "$TRANSLATE_SVC" <<<"$(running_containers)"; then
        ok "translate vLLM up on :$TRANSLATE_PORT (co-resident)"
    else
        dim "translate vLLM down (:$TRANSLATE_PORT) — translation unavailable"
    fi
    dim "GPU: $(gpu_state_line)"
    ((JSON)) && emit_json "$mode" true || true
}

# Single-slot modes: done when that slot serves. do_swap fails the run otherwise.
swap_slot() {  # <mode> <dir> <port> <container> [model]
    do_swap "$@"
    ((JSON)) && emit_json "$1" true "port=$3" || true
}
action_code()     { swap_slot "code"     "$CODER_DIR"    "$CODER_PORT"    "$CODER_SVC"; }
action_research() { swap_slot "research" "$RESEARCH_DIR" "$RESEARCH_PORT" "$RESEARCH_SVC"; }

# prod = the serving vLLM on :8003 AND the co-resident translation vLLM on :8005, and it
# is done only when BOTH serve their models. It used to report success with translate down
# ("summaries still serve") — which is how the 2026-10-30 swaps ended with translation
# missing and a hand start needed. A half-done prod is a failed prod; re-run `prod` to
# finish it, which starts only what is missing.
action_prodvllm() {
    do_swap "prod" "$PRODVLLM_DIR" "$PRODVLLM_PORT" "$PRODVLLM_SVC" "$PRODVLLM_MODEL"
    if [[ "$TRANSLATE_WITH_PROD" == "1" ]]; then
        start_translate || fail "translate not serving on :$TRANSLATE_PORT — prod is NOT complete (:$PRODVLLM_PORT serves; re-run 'prod' to finish)"
    else
        dim "translate vLLM skipped (GPU_MODE_TRANSLATE_WITH_PROD=0)"
    fi
    # End state, re-checked as a whole: loading translate must not have cost :8003.
    serving_ok "$PRODVLLM_PORT" "$PRODVLLM_DIR" "$PRODVLLM_MODEL" \
        || fail "end-state check: :$PRODVLLM_PORT no longer serving $PRODVLLM_MODEL"
    if [[ "$TRANSLATE_WITH_PROD" == "1" ]]; then
        serving_ok "$TRANSLATE_PORT" "$TRANSLATE_DIR" "$TRANSLATE_MODEL" \
            || fail "end-state check: :$TRANSLATE_PORT not serving $TRANSLATE_MODEL"
    fi
    ok "prod complete: :$PRODVLLM_PORT ${PRODVLLM_MODEL:-serving}$([[ "$TRANSLATE_WITH_PROD" == "1" ]] && echo ", :$TRANSLATE_PORT ${TRANSLATE_MODEL:-serving}")"
    ((JSON)) && emit_json "prod" true "port=$PRODVLLM_PORT" || true
}

# Bring the translation vLLM up beside whatever owns :8003 and wait until it serves.
# Idempotent: `compose up -d` leaves a running container alone, so a re-run only starts
# a missing translator. Returns non-zero; the caller decides that this fails the mode.
start_translate() {
    if [[ ! -d "$TRANSLATE_DIR" ]]; then
        warn "translate stack dir missing: $TRANSLATE_DIR"
        return 1
    fi
    if grep -qx "$TRANSLATE_SVC" <<<"$(running_containers)"; then
        dim "translate container already running — checking it serves"
    else
        log "starting translate vLLM (co-resident, :$TRANSLATE_PORT)"
        remove_stale_container "$TRANSLATE_SVC"
        compose_up "$TRANSLATE_DIR" || { warn "compose up failed for $TRANSLATE_DIR"; return 1; }
    fi
    wait_serving "translate vLLM" "$TRANSLATE_PORT" "$TRANSLATE_DIR" "$TRANSLATE_SVC" "$TRANSLATE_MODEL"
}
action_judging_a() { swap_slot "judging-a" "$JUDGE_A_DIR" "$JUDGE_A_PORT" "$JUDGE_A_SVC"; }
action_judging_b() { swap_slot "judging-b" "$JUDGE_B_DIR" "$JUDGE_B_PORT" "$JUDGE_B_SVC"; }
action_judging_n() { swap_slot "judging-qwen-next" "$JUDGE_QWEN_NEXT_DIR" "$JUDGE_QWEN_NEXT_PORT" "$JUDGE_QWEN_NEXT_SVC"; }
action_judging_x() { swap_slot "judging-nemotron"  "$JUDGE_NEMOTRON_DIR"  "$JUDGE_NEMOTRON_PORT"  "$JUDGE_NEMOTRON_SVC"; }

action_free() {
    log "→ free (bringing all vLLM composes down)"
    local apps_before; apps_before=$(gpu_compute_app_count)
    # ...INCLUDING the co-resident translator: `free` means nothing holds the GPU, and
    # stop_all_composes omits it on purpose (a swap into prod must not kill it).
    stop_all_composes_including_translate
    sleep 2
    local left="" svc names; names="$(running_containers)"
    for svc in "$CODER_SVC" "$RESEARCH_SVC" "$PRODVLLM_SVC" "$TRANSLATE_SVC" "$JUDGE_A_SVC" "$JUDGE_B_SVC" "$JUDGE_QWEN_NEXT_SVC" "$JUDGE_NEMOTRON_SVC"; do
        grep -qx "$svc" <<<"$names" && left+=" $svc"
    done
    [[ -z "$left" ]] || fail "end-state check: still running after free:$left"
    local apps_after; apps_after=$(gpu_compute_app_count)
    ok "compute apps ${apps_before}→${apps_after}; now: $(gpu_state_line)"
    ((JSON)) && emit_json "free" true "compute_apps_before=${apps_before}" "compute_apps_after=${apps_after}" || true
}

# ── ollama (podcast_scraper pipeline) ────────────────────────────────────
#
# The pipeline's three GPU consumers are faster-whisper (:8000), pyannote
# (:8001) and Ollama (:11434) — none of them is a vLLM. A vLLM sitting in the
# research/prod slot holds ~79 GB and starves them, so "ollama" is precisely: no
# vLLM at all, plus the LLM the pipeline is actually evaluated against, kept warm.
#
# The model is PINNED, not incidental. ``qwen3.5:35b`` is the #928 summary/GI/KG
# championship winner (finale 5.00/5 Sonnet, 4.90 GPT-5.4, 100% judge agreement)
# and the 2026-07 judges matrix reconfirmed it ("June's champion holds up").
# Changing it is a decision that invalidates those evals, so it lives here as one
# named constant rather than being whatever happened to be loaded.
#
# Unlike the vLLM modes this does NOT flush Ollama — in ollama mode, Ollama *is* the point.
#
# Note: `status` will report `free`, because mode is derived from which vLLM owns
# the GPU and ollama mode deliberately runs none. That is accurate: no vLLM owns it.
OLLAMA_LLM_MODEL="${GPU_MODE_OLLAMA_LLM_MODEL:-qwen3.5:35b}"
OLLAMA_WHISPER_PORT="${GPU_MODE_OLLAMA_WHISPER_PORT:-8000}"
OLLAMA_DIARIZE_PORT="${GPU_MODE_OLLAMA_DIARIZE_PORT:-8001}"
OLLAMA_MOSS_PORT="${GPU_MODE_OLLAMA_MOSS_PORT:-8004}"

action_ollama() {
    log "→ ollama (pipeline: no vLLM; Ollama serves the pinned LLM)"
    local apps_before; apps_before=$(gpu_compute_app_count)

    stop_all_composes
    sleep 2

    # prod mode stops the daemon (#63), so bring it back before warming — otherwise this
    # mode reports "Ollama unreachable" and silently serves nothing.
    start_ollama_daemon

    local host="${OLLAMA_HOST:-http://127.0.0.1:11434}"
    local llm_ok=0
    if ! curl -fsS --max-time 3 "${host}/api/ps" >/dev/null 2>&1; then
        warn "Ollama unreachable at ${host} — the pipeline's summary/GI/KG stages will fail"
    else
        log "warming pinned ollama model: ${OLLAMA_LLM_MODEL} (cold load can take ~1-2 min)"
        if curl -fsS --max-time 600 -X POST "${host}/api/generate" \
                -H 'Content-Type: application/json' \
                -d "$(printf '{"model":"%s","prompt":"ok","keep_alive":"24h","stream":false}' "$OLLAMA_LLM_MODEL")" \
                >/dev/null 2>&1; then
            ok "Ollama warm: ${OLLAMA_LLM_MODEL} (keep_alive=24h)"
            llm_ok=1
        else
            warn "could not warm ${OLLAMA_LLM_MODEL} — pulled? try: ollama pull ${OLLAMA_LLM_MODEL}"
        fi
    fi

    local svc_ok=1
    if curl -fsS --max-time 5 -o /dev/null "http://127.0.0.1:${OLLAMA_WHISPER_PORT}/v1/models" 2>/dev/null; then
        ok "faster-whisper up on :${OLLAMA_WHISPER_PORT}"
    else
        warn "faster-whisper NOT responding on :${OLLAMA_WHISPER_PORT}"; svc_ok=0
    fi
    if curl -fsS --max-time 5 -o /dev/null "http://127.0.0.1:${OLLAMA_DIARIZE_PORT}/v1/models" 2>/dev/null; then
        ok "pyannote up on :${OLLAMA_DIARIZE_PORT}"
    else
        warn "pyannote NOT responding on :${OLLAMA_DIARIZE_PORT}"; svc_ok=0
    fi
    if curl -fsS --max-time 5 -o /dev/null "http://127.0.0.1:${OLLAMA_MOSS_PORT}/v1/models" 2>/dev/null; then
        ok "MOSS up on :${OLLAMA_MOSS_PORT}"
    else
        warn "MOSS NOT responding on :${OLLAMA_MOSS_PORT} (transcription falls back to faster-whisper)"
    fi

    local apps_after; apps_after=$(gpu_compute_app_count)
    ok "compute apps ${apps_before}→${apps_after}; now: $(gpu_state_line)"

    local all_ok=false
    [[ $llm_ok -eq 1 && $svc_ok -eq 1 ]] && all_ok=true
    ((JSON)) && emit_json "ollama" "$all_ok" "llm=${OLLAMA_LLM_MODEL}" "compute_apps_before=${apps_before}" "compute_apps_after=${apps_after}" || true
    if [[ "$all_ok" != true ]]; then
        FAIL_REASON="ollama mode incomplete: llm warm=$llm_ok, whisper+pyannote up=$svc_ok"
        return 1
    fi
}

do_swap() {
    local target=$1 start_dir=$2 start_port=$3 start_svc=${4:-} start_model=${5:-}
    require_dir "$start_dir"
    local current; current=$(current_mode)

    # Already in the target mode: no teardown, but not a blind no-op either — wait until the
    # slot actually serves (it may still be loading from a swap that was cut short). The
    # caller then starts whatever else the mode needs. current_mode() infers the mode from
    # WHICH COMPOSE SERVICE IS RUNNING, so a host messed with by hand (ollama started
    # manually, a model loaded) still reports the same mode; --force is the reset.
    if [[ "$current" == "$target" && $FORCE -eq 0 ]]; then
        log "already in $target mode — checking it serves (use --force to re-run the full swap)"
        wait_serving "$target vLLM" "$start_port" "$start_dir" "$start_svc" "$start_model" \
            || fail "$target vLLM not serving on :$start_port"
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
    #
    # ...and STOP the daemon, not merely flush it. Flushing leaves it listening, so one
    # request reloads a model, and that load/unload cycle is what wedged this host three
    # times (#63) — minutes after the release, with memory already recovered.
    #
    # Unconditional because do_swap IS the vLLM path: every one of its seven callers
    # (code, research, prod, judging-a/-b/-qwen-next/-nemotron) brings up a vllm-* service.
    # Keying off the mode NAME would silently miss the judging slots today and any vLLM
    # slot added later; keying off "a vLLM is about to own the GPU" cannot drift.
    # The modes where Ollama legitimately runs — `ollama` and `free` — never reach here.
    stop_ollama_daemon

    # research + prod are the heavy same-size vLLMs sharing the GPU with
    # Ollama — flush it + clear any stale container before starting. Code slot
    # is intentionally untouched here.
    if [[ "$target" == "research" || "$target" == "prod" ]]; then
        prepare_gpu_for_research
        remove_stale_container "${start_svc:-$RESEARCH_SVC}"
    fi

    compose_up "$start_dir" || fail "compose up failed for $start_dir"

    log "waiting for $target to serve (model load; up to ${START_TIMEOUT}s)"
    wait_serving "$target vLLM" "$start_port" "$start_dir" "$start_svc" "$start_model" \
        || fail "$target vLLM not serving on :$start_port"
    local apps_after; apps_after=$(gpu_compute_app_count)
    dim "compute apps ${apps_before}→${apps_after}; $(gpu_state_line)"
}

# ── detach, lock, record ─────────────────────────────────────────────────
#
# A swap takes minutes and must not die with whoever started it: on 2026-10-30 the
# caller's SSH session was cut three minutes in and the swap stopped between :8003 and
# translate. So the caller only launches and follows; the swap itself runs in its own
# session (setsid) with SIGHUP ignored (nohup) and every byte of output in its log, so
# nothing it does touches the caller's terminal. `setsid -w` hands the swap's exit code
# back to a caller that is still there.

# The caller side: start the detached swap, stream its log, return its exit code.
detach_and_follow() {
    mkdir -p "$STATE_DIR"
    local log="$STATE_DIR/swap-$(date -u +%Y%m%dT%H%M%SZ)-${MODE_LABEL}.log"
    : >"$log"
    ln -sfn "$(basename "$log")" "$STATE_DIR/last.log"
    # Keep the newest 50 logs.
    ls -1t "$STATE_DIR"/swap-*.log 2>/dev/null | tail -n +51 | xargs -r rm -f --
    GPU_MODE_DETACHED="$log" setsid -w nohup "$SCRIPT_PATH" "${ORIG_ARGS[@]}" \
        >>"$log" 2>&1 </dev/null &
    local pid=$! rc=0
    printf '[gpu-mode] %s swap running detached (pid %s); it carries on if this shell or SSH session ends\n[gpu-mode] log: %s\n' \
        "$MODE_LABEL" "$pid" "$log" >&2
    if (( JSON )); then
        tail -n +1 -F --pid="$pid" "$log" 2>/dev/null | grep -v '^{' >&2 || true
    else
        tail -n +1 -F --pid="$pid" "$log" >&2 2>/dev/null || true
    fi
    wait "$pid" || rc=$?
    (( JSON )) && { grep '^{' "$log" | tail -1 || true; }
    return "$rc"
}

# The swap side: the log's last line says how it ended, whatever path it took out.
finish() {
    local rc=$?
    if (( rc == 0 )); then
        printf 'MODE=%s OK\n' "$MODE_LABEL" >&2
    else
        printf 'MODE=%s FAILED: %s (exit %s)\n' "$MODE_LABEL" "${FAIL_REASON:-see the lines above}" "$rc" >&2
    fi
}

if [[ "$MODE" != status ]]; then
    if [[ -z "${GPU_MODE_DETACHED:-}" ]] && (( FOREGROUND == 0 )); then
        rc=0
        detach_and_follow || rc=$?
        exit "$rc"
    fi
    trap finish EXIT
    mkdir -p "$STATE_DIR"
    exec 9>>"$STATE_DIR/swap.lock"
    if ! flock -n 9; then
        fail 4 "another swap is running: $(cat "$STATE_DIR/swap.owner" 2>/dev/null || echo unknown)"
    fi
    printf 'pid %s, %s, log %s\n' "$$" "$MODE_LABEL" "${GPU_MODE_DETACHED:-foreground}" >"$STATE_DIR/swap.owner"
    log "$MODE_LABEL swap started $(date -u +%FT%TZ) as $(id -un) (pid $$)"
fi

# ── dispatch ─────────────────────────────────────────────────────────────

case "$MODE" in
    status)    action_status ;;
    code)      action_code ;;
    research)  action_research ;;
    free)      action_free ;;
    prod)      action_prodvllm ;;
    ollama)    action_ollama ;;
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
        echo "usage: $0 [code|research|free|prod|ollama|status|judging {a|b}] [--json] [--mode-only] [--no-color] [--force]" >&2
        exit 2
        ;;
esac
