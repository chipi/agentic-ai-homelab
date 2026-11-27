#!/usr/bin/env bash
# The X3's host jobs, run every minute by the user timer x3-host.timer (from the deploy checkout):
#   1. container inventory: `docker inspect` through the shared mini-metrics/ctr.py (box="x3"), the same
#      series the mini and the DGX send (container_uptime_seconds), so the hub's Hosts tab, the incident
#      timeline and the briefing see the X3's containers like any other box's;
#   2. service_up{box="x3",service=...} for the two services here that are units, not containers: the
#      Ollama (the ollama unit, :11435) and its Alloy collector (alloy-research);
#   3. a size cap on Ollama's log (logrotate is not installed here): over CAP_MB it is copied to
#      ollama.log.1 and truncated in place. The ollama unit appends (>>), and Alloy's file tail follows a
#      truncation, so neither needs a restart;
#   4. storage errors in this boot's kernel log, by kind, as x3_storage_kernel_errors{kind=fsverity|btrfs|
#      nvme|io}: a count since boot (it only grows until a reboot; the alert x3-storage-errors uses increase()).
#      Nothing else reads the X3's kernel log: fs-verity refused 27 corrupted reads during docker builds on
#      2026-11-06..13 and nobody saw them until robotics-lab's commits failed on 11-20.
#   5. the CI runners' cap (gh-runner's user slice, ADR-0015): CPU used and throttled, memory against its high
#      and max, pressure stall time, OOM kills, all as counters or gauges from the slice's cgroup files
#      (x3_ci_*). The cap is shared by every runner, so a throttled slice slows every job at once; nothing
#      recorded it before (player's e2e timeouts of 2026-11-26 could not be tied to it or ruled out).
#   6. each runner's disk, its downloads and its engine, from the runners' sync (log/ci-sizes.prom), and the
#      free space under /var/lib/gh-runner: the budget is 5 GB + 10 GB a runner (entrypoint.sh prunes to it);
#   7. hourly, the dev engine's disk by type (mini-metrics/engine-df.py, docker_engine_*{box="x3",engine="dev"}).
# Pushes to VictoriaMetrics over the tailnet, as the X3's Alloy does. Each part is best effort: one failing
# never stops the others.
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
VM="${X3_VM_IMPORT:-https://vm.tail6d0ed4.ts.net/api/v1/import/prometheus}"
OLLAMA="${X3_OLLAMA_URL:-http://100.92.54.65:11435/api/version}"
LOG="${X3_OLLAMA_LOG:-$HOME/.local/state/ollama/ollama.log}"
CAP_MB="${X3_OLLAMA_LOG_CAP_MB:-50}"

# push stdin to VictoriaMetrics; a refused push goes to the journal (stderr), it is not silent
push() { local what=$1 code; code=$(curl -s -m8 -o /dev/null -w '%{http_code}' --data-binary @- "$VM") || true
  case "$code" in 2??) ;; *) echo "x3-host: $what push to $VM failed: HTTP ${code:-none}" >&2 ;; esac; }

# 1. containers (the inspect format ctr.py reads; see its docstring)
ids=$(docker ps -aq 2>/dev/null)
if [ -n "$ids" ]; then
  docker inspect $ids --format '{{.Name}}	{{.State.Status}}	{{.State.StartedAt}}	{{index .Config.Labels "com.docker.compose.project"}}	{{json .NetworkSettings.Ports}}	{{.State.ExitCode}}	{{if .State.Health}}{{.State.Health.Status}}{{else}}-{{end}}' 2>/dev/null \
    | python3 "$HERE/../mini-metrics/ctr.py" x3 | push containers
fi

# 2. the units
code=$(curl -s -o /dev/null -m3 -w '%{http_code}' "$OLLAMA")
a=0; [ "$code" = 200 ] && a=1
c=0; systemctl --user is-active --quiet alloy-research && c=1
printf 'service_up{box="x3",service="ollama"} %s\nservice_up{box="x3",service="alloy-research"} %s\nx3_host_last_push_timestamp %s\n' \
  "$a" "$c" "$(date +%s)" | push units

# 3. Ollama's log
if [ -f "$LOG" ] && [ "$(stat -c %s "$LOG")" -gt $((CAP_MB * 1024 * 1024)) ]; then
  cp -p "$LOG" "$LOG.1" && : > "$LOG"
fi

# 4. storage errors in this boot's kernel log (one journalctl pass, sorted into kinds by awk). The patterns
# match none of this boot's normal nvme/BTRFS info lines ("using crc32c checksum algorithm" included).
journalctl -k -b --no-pager -q \
  --grep 'fs-verity .*FILE CORRUPTED|BTRFS (error|critical)|csum failed|checksum error|nvme[0-9n]*: .*(I/O error|timeout|resetting controller|Abort status|failed)|blk_update_request|I/O error, dev|Buffer I/O error' \
  2>/dev/null | awk '
    /fs-verity .*FILE CORRUPTED/ { f++; next }
    /BTRFS (error|critical)|csum failed|checksum error/ { b++; next }
    /nvme[0-9n]*: / { n++; next }
    { i++ }
    END { printf "x3_storage_kernel_errors{box=\"x3\",kind=\"fsverity\"} %d\nx3_storage_kernel_errors{box=\"x3\",kind=\"btrfs\"} %d\nx3_storage_kernel_errors{box=\"x3\",kind=\"nvme\"} %d\nx3_storage_kernel_errors{box=\"x3\",kind=\"io\"} %d\n", f, b, n, i }' \
  | push storage

# 5. the CI runners' cap. Rates come from the counters: throttled share = rate(throttled_periods) / rate(periods).
CI_UID=$(id -u gh-runner 2>/dev/null) && CG="/sys/fs/cgroup/user.slice/user-$CI_UID.slice" && [ -r "$CG/cpu.stat" ] && {
  awk '
    FILENAME ~ /cpu.stat$/      { s[$1] = $2 }
    FILENAME ~ /cpu.max$/       { q = ($1 == "max") ? 0 : $1 / $2 }
    FILENAME ~ /memory.events$/ { e[$1] = $2 }
    FILENAME ~ /cpu.pressure$/    && $1 == "some" { split($5, t, "="); cps = t[2] }
    FILENAME ~ /memory.pressure$/ && $1 == "some" { split($5, t, "="); mps = t[2] }
    FILENAME ~ /memory.current$/ { mc = $1 }
    FILENAME ~ /memory.peak$/    { mp = $1 }
    FILENAME ~ /memory.max$/     { mm = ($1 == "max") ? 0 : $1 }
    FILENAME ~ /memory.high$/    { mh = ($1 == "max") ? 0 : $1 }
    END {
      L = "{box=\"x3\"}"
      printf "x3_ci_cpu_usage_seconds_total%s %.3f\n", L, s["usage_usec"] / 1e6
      printf "x3_ci_cpu_periods_total%s %d\nx3_ci_cpu_throttled_periods_total%s %d\n", L, s["nr_periods"], L, s["nr_throttled"]
      printf "x3_ci_cpu_throttled_seconds_total%s %.3f\nx3_ci_cpu_quota_cores%s %g\n", L, s["throttled_usec"] / 1e6, L, q
      printf "x3_ci_cpu_pressure_seconds_total%s %.3f\nx3_ci_memory_pressure_seconds_total%s %.3f\n", L, cps / 1e6, L, mps / 1e6
      printf "x3_ci_memory_bytes%s %d\nx3_ci_memory_peak_bytes%s %d\nx3_ci_memory_max_bytes%s %d\nx3_ci_memory_high_bytes%s %d\n", L, mc, L, mp, L, mm, L, mh
      printf "x3_ci_memory_high_events_total%s %d\nx3_ci_memory_max_events_total%s %d\nx3_ci_oom_kills_total%s %d\n", L, e["high"], L, e["max"], L, e["oom_kill"]
    }' "$CG/cpu.stat" "$CG/cpu.max" "$CG/memory.events" "$CG/cpu.pressure" "$CG/memory.pressure" "$CG/memory.current" "$CG/memory.peak" "$CG/memory.max" "$CG/memory.high" \
  | push ci-cap
}

# 6. each runner's disk (its downloads and its engine), measured at its last start and written by the
# runners' sync into its log folder, plus the free space where they live. Pushed as it is.
SIZES=/srv/ci-runner-src/log/ci-sizes.prom
[ -r "$SIZES" ] && push ci-sizes < "$SIZES"
df -B1 --output=avail,size /var/lib/gh-runner 2>/dev/null | awk 'NR == 2 { printf "x3_ci_disk_free_bytes{box=\"x3\"} %d\nx3_ci_disk_size_bytes{box=\"x3\"} %d\n", $1, $2 }' | push ci-disk

# 7. the dev engine's disk (the local system engine, context dev), hourly: `docker system df` walks every
# layer. For the Hub's Docker disk table, beside dev-engine-prune's weekly run.
STAMP=~/.cache/x3-host-engine-df
if [ ! -e "$STAMP" ] || [ -n "$(find "$STAMP" -mmin +59 2>/dev/null)" ]; then
  mkdir -p "${STAMP%/*}" && touch "$STAMP"
  timeout 120 docker --context dev system df --format '{{json .}}' 2>/dev/null | python3 "$HERE/../mini-metrics/engine-df.py" x3 dev | push engine-df
fi
