#!/bin/bash
# Mac mini host<->VM forward watchdog — NOTIFY-FIRST (resilience #2a).
#
# colima runs Docker in a Linux VM; lima forwards the VM's docker socket + every
# published port to the Mac host over an SSH channel. A network transition
# (internet outage, link flap, sleep/wake) can half-open that channel — the host
# loses the docker socket + all loopback ports while the VM and every container
# keep running. It does NOT self-heal (see
# docs/recipes/colima-lima-forwarding-recovery.md).
#
# This is a DEAD-MAN'S SWITCH, deliberately, and it does NOT restart anything
# (that's the opt-in #2b). Every 30s it proves the host can reach the VM's docker
# socket, and — only then — heart-beats mini_forward_up=1 to VictoriaMetrics over
# the *forwarded* :8428. Both the probe and the publish ride the same lima
# forward, so when the forward breaks the heartbeat STOPS. The absence is the
# signal: the "mini-forward-down" alert (rules.yaml, same pattern as dgx-silent)
# fires after 5m of no samples -> email. Recovery is a human `colima restart`.
#
# AUTO-CAPTURE (added 2026-09-03, resilience #2a-bis): the recovery action
# (`colima restart`) DESTROYS the evidence — lima recreates ha.stderr.log, so
# after both the 2026-08-18 and 2026-09-03 breaks the only artifact that could
# identify the *trigger* was gone before anyone looked. On the FIRST failed probe
# of a break this now dumps a forensic snapshot to /tmp/forward-break-*.txt,
# BEFORE any human touches the box. Capture happens once per break (marker file,
# cleared when the forward returns) and every step is timeout-bounded so a wedged
# guest can never stall the heartbeat loop.
VM=http://localhost:8428/api/v1/import/prometheus
D=/usr/local/bin/docker   # reaches the VM's dockerd via the socat relay (/var/run/docker.sock)
DH="sudo -n -u _dockerhost env HOME=/var/_dockerhost PATH=/usr/local/bin:$PATH"
LIMA=/var/_dockerhost/.colima/_lima/colima
MARKER=/tmp/.forward-break-captured

# Bounded runner — macOS has no `timeout`. A wedged guest must never hang the loop.
run_to() {
  local secs="$1"; shift
  "$@" & local pid=$!
  ( sleep "$secs"; kill -9 "$pid" 2>/dev/null ) >/dev/null 2>&1 & local killer=$!
  wait "$pid" 2>/dev/null; local rc=$?
  kill -9 "$killer" 2>/dev/null
  [ $rc -ne 0 ] && echo "   [timed out/failed after ${secs}s]"
  return $rc
}

capture_break() {
  local out="/tmp/forward-break-$(date +%Y%m%d-%H%M%S).txt"
  {
    echo "### host<->VM forward break — captured $(date) by forward-watchdog"
    echo "### (captured BEFORE any restart; a colima restart recreates ha.stderr.log)"

    echo; echo "== host =="
    uptime
    ps aux | grep -E 'qemu-system|limactl' | grep -v grep

    echo; echo "== colima sockets =="
    ls -la /var/_dockerhost/.colima/default/ 2>&1

    echo; echo "== ha.stderr.log (THE artifact — lima's own view of the break) =="
    sudo -n tail -300 "$LIMA/ha.stderr.log" 2>&1 || echo "(need root; sudo -n failed)"

    echo; echo "== serial.log: OOM / panic / hung task =="
    sudo -n grep -iE 'oom|killed process|panic|hung task|blocked for more than' \
      "$LIMA/serial.log" 2>&1 | tail -30 || echo "(none / need root)"

    echo; echo "== relay log around the break =="
    tail -40 /tmp/docker-relay.log 2>&1

    echo; echo "== colima status =="
    run_to 20 $DH colima status 2>&1

    # Guest probes LAST: they may hang if the guest is wedged. Host evidence above
    # is already written, and each call is capped.
    echo; echo "== guest: process states (zombie accumulation?) =="
    run_to 20 $DH colima ssh -- sh -c 'awk "/^State:/{print \$2}" /proc/[0-9]*/status | sort | uniq -c | sort -rn' 2>&1
    echo; echo "== guest: load + top =="
    run_to 20 $DH colima ssh -- top -b -n 1 2>&1 | head -14
    echo; echo "== guest: dockerd =="
    run_to 20 $DH colima ssh -- sudo systemctl is-active docker 2>&1
    echo; echo "== guest: containers =="
    run_to 25 $DH colima ssh -- docker ps -a --format '{{.Names}}\t{{.Status}}' 2>&1

    echo; echo "### end of capture"
  } > "$out" 2>&1
  echo "$out" > "$MARKER"
  echo "$(date) forward break — forensics captured to $out"
}

while true; do
  # Canonical "host can talk to the VM" test — the exact path the operator's CLI
  # and the mini-metrics collector use. Fails the instant the forward breaks.
  if $D ps -q >/dev/null 2>&1; then
    printf 'mini_forward_up{box="mini"} 1\n' \
      | curl -s -m8 -o /dev/null --data-binary @- "$VM" || true
    # Forward is healthy — re-arm capture for the next break.
    rm -f "$MARKER" 2>/dev/null || true
  else
    # Forward is down. Capture ONCE per break, immediately, before any recovery.
    [ -f "$MARKER" ] || capture_break || true
  fi
  sleep 30
done
