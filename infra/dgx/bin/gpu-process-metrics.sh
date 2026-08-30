#!/bin/bash
# Per-process GPU memory WITH container attribution -> VictoriaMetrics.
#
# WHY THIS EXISTS (2026-08-30). The DGX's GB10 is unified memory: it has no
# framebuffer, so every DCGM_FI_DEV_FB_* field is silently unavailable and
# `nvidia-smi -q -d MEMORY` reports N/A. Device-level GPU memory simply cannot
# be read here. But `nvidia-smi --query-compute-apps` DOES work, so per-process
# memory is available — and each PID's cgroup carries its docker container id,
# which lets us attribute GPU memory to a container by name.
#
# That makes this the ONLY source on this box for "which service is eating the
# GPU", which is the co-tenancy question that matters when an LLM run shares the
# GB10 with live production ASR (pyannote / faster-whisper / moss).
#
# Emits:
#   dgx_gpu_process_memory_bytes{container,process}  per (container, process)
#   dgx_gpu_memory_used_bytes                        sum across all GPU processes
#   dgx_gpu_process_count                            how many processes hold GPU memory
#   dgx_gpu_metrics_last_run_timestamp               dead-man (alert: dgx-gpu-metrics-stale)
#
# CARDINALITY: deliberately NO pid label. PIDs churn on every container restart
# and would mint a new series each time; container+process is bounded and stable.
#
# Source of truth is this file in the repo. The DGX runs a COPY at
# /usr/local/bin/gpu-process-metrics.sh (the ops checkout is intentionally not
# pulled — see infra/dgx/AGENTS.md), so redeploy = scp this file over that one.
set -uo pipefail

VM_URL="${VM_URL:-https://vm.tail6d0ed4.ts.net}"
INSTANCE="${HOMELAB_INSTANCE:-dgx-llm-1}"

command -v nvidia-smi >/dev/null || { echo "nvidia-smi not found" >&2; exit 1; }

# container id (full 64-hex) -> friendly name, resolved once per run
declare -A CNAME
while read -r cid cname; do
  [ -n "${cid:-}" ] && CNAME["$cid"]="$cname"
done < <(docker ps --no-trunc --format '{{.ID}} {{.Names}}' 2>/dev/null)

declare -A AGG   # "container|process" -> bytes
total=0
nproc=0

while IFS=, read -r pid pname mem; do
  pid="${pid// /}"; pname="${pname# }"; mem="${mem// /}"
  [[ "$pid" =~ ^[0-9]+$ ]] || continue
  [[ "$mem" =~ ^[0-9]+$ ]] || continue

  # /proc/<pid>/cgroup carries .../docker-<64hex>.scope under cgroup v2 + systemd
  cid=$(grep -oE 'docker-[0-9a-f]{64}' "/proc/$pid/cgroup" 2>/dev/null | head -1)
  cid="${cid#docker-}"
  container="${CNAME[$cid]:-}"
  [ -z "$container" ] && container=$( [ -n "$cid" ] && echo "unknown-container" || echo "host" )

  bytes=$(( mem * 1024 * 1024 ))
  key="${container}|${pname}"
  AGG["$key"]=$(( ${AGG["$key"]:-0} + bytes ))
  total=$(( total + bytes ))
  nproc=$(( nproc + 1 ))
done < <(nvidia-smi --query-compute-apps=pid,process_name,used_memory --format=csv,noheader,nounits 2>/dev/null)

payload=""
for key in "${!AGG[@]}"; do
  container="${key%%|*}"; process="${key#*|}"
  process="${process//\"/}"            # keep the label value quote-safe
  payload+="dgx_gpu_process_memory_bytes{instance=\"$INSTANCE\",container=\"$container\",process=\"$process\"} ${AGG[$key]}"$'\n'
done
payload+="dgx_gpu_memory_used_bytes{instance=\"$INSTANCE\"} $total"$'\n'
payload+="dgx_gpu_process_count{instance=\"$INSTANCE\"} $nproc"$'\n'
# dead-man LAST, so it only stamps a run that produced everything above
payload+="dgx_gpu_metrics_last_run_timestamp{instance=\"$INSTANCE\"} $(date +%s)"$'\n'

if [ "${DRY_RUN:-0}" = "1" ]; then
  printf '%s' "$payload"
  exit 0
fi

curl -sS --max-time 10 --data-binary "$payload" \
  "$VM_URL/api/v1/import/prometheus" || { echo "push failed" >&2; exit 1; }
