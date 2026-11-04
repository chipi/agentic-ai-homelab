#!/usr/bin/env bash
# The X3's host jobs, run every minute by the user timer x3-host.timer (from the deploy checkout):
#   1. container inventory: `docker inspect` through the shared mini-metrics/ctr.py (box="x3"), the same
#      series the mini and the DGX send (container_uptime_seconds), so the hub's Hosts tab, the incident
#      timeline and the briefing see the X3's containers like any other box's;
#   2. service_up{box="x3",service=...} for the two services here that are units, not containers: the
#      assistant (ollama-assistant, :11435) and its Alloy collector (alloy-research);
#   3. a size cap on the assistant's log (logrotate is not installed here): over CAP_MB it is copied to
#      ollama.log.1 and truncated in place. ollama-assistant appends (>>), and Alloy's file tail follows a
#      truncation, so neither needs a restart.
# Pushes to VictoriaMetrics over the tailnet, as the X3's Alloy does. Each part is best effort: one failing
# never stops the others.
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
VM="${X3_VM_IMPORT:-https://vm.tail6d0ed4.ts.net/api/v1/import/prometheus}"
ASSISTANT="${X3_ASSISTANT_URL:-http://100.92.54.65:11435/api/version}"
LOG="${X3_ASSISTANT_LOG:-$HOME/.local/state/ollama-assistant/ollama.log}"
CAP_MB="${X3_ASSISTANT_LOG_CAP_MB:-50}"

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
code=$(curl -s -o /dev/null -m3 -w '%{http_code}' "$ASSISTANT")
a=0; [ "$code" = 200 ] && a=1
c=0; systemctl --user is-active --quiet alloy-research && c=1
printf 'service_up{box="x3",service="assistant"} %s\nservice_up{box="x3",service="alloy-research"} %s\nx3_host_last_push_timestamp %s\n' \
  "$a" "$c" "$(date +%s)" | push units

# 3. the assistant's log
if [ -f "$LOG" ] && [ "$(stat -c %s "$LOG")" -gt $((CAP_MB * 1024 * 1024)) ]; then
  cp -p "$LOG" "$LOG.1" && : > "$LOG"
fi
