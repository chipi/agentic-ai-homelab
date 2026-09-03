#!/bin/bash
# Mac mini host<->VM forward watchdog — NOTIFY-FIRST (resilience #2a).
#
# colima runs Docker in a Linux VM; lima forwards the VM's docker socket + every
# published port to the Mac host over an SSH ControlMaster mux. When that master
# goes away the host loses the docker socket + all loopback ports while the VM and
# every container keep running. It does NOT self-heal (see
# docs/recipes/colima-lima-forwarding-recovery.md).
#
# This is a DEAD-MAN'S SWITCH, deliberately, and it does NOT restart anything
# (that's the opt-in #2b). Every 30s it proves the host can reach the VM's docker
# socket, and — only then — heart-beats mini_forward_up=1 to VictoriaMetrics over
# the *forwarded* :8428. Both the probe and the publish ride the same lima
# forward, so when the forward breaks the heartbeat STOPS. The absence is the
# signal: the "mini-forward-down" alert fires after 5m of no samples -> email.
# Recovery is a human `colima restart`.
#
# AUTO-CAPTURE (2026-09-03): the recovery action DESTROYS the evidence — a
# `colima restart` recreates ha.stderr.log — so after both the 2026-08-18 and
# 2026-09-03 breaks the artifact that would identify the TRIGGER was gone before
# anyone looked. On the FIRST failed probe of a break this dumps a forensic
# snapshot to /tmp/forward-break-*.txt BEFORE any recovery. Once per break
# (marker cleared when the forward returns); every guest probe timeout-bounded.
#
# WHAT WE KNOW (2026-09-03 guest-journal analysis): the mux does not half-open or
# time out. sshd logged `Received disconnect ... :11: disconnected by user` at the
# break second in BOTH incidents — a clean, client-initiated SSH disconnect. That
# is either `ssh -O exit`/`-O stop` from a mux client, or a signal (SIGTERM/INT/
# HUP) to the master. The two are distinguished by ONE string in ha.stderr.log:
# a signal death prints "Killed by signal N."; an -O exit prints nothing. Hence
# the full-file copy + grep below rather than a tail.
#
# NOTE we deliberately do NOT poll the master with `ssh -O check` on the healthy
# path: mux client commands are a SUSPECT in closing the master (port-forward
# churn was heavy before both breaks), so the steady-state tracking is passive
# `ps`. `-O check` is issued once, at break time, when the master is already gone.
VM=http://localhost:8428/api/v1/import/prometheus
D=/usr/local/bin/docker   # reaches the VM's dockerd via the socat relay (/var/run/docker.sock)
DH="sudo -n -u _dockerhost env HOME=/var/_dockerhost PATH=/usr/local/bin:$PATH"
LIMA=/var/_dockerhost/.colima/_lima/colima
MARKER=/tmp/.forward-break-captured
PIDFILE=/tmp/.forward-master-pid
PIDLOG=/tmp/forward-master-pid.log

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

# Passive: the SSH ControlMaster's PID. The master detaches (PPID 1) and renames
# itself to `ssh: <ControlPath> [mux]` — note "ssh:" not "ssh ", which is why the
# match is on [mux] rather than the ssh binary. Its death IS the break.
master_pid() {
  ps -axo pid,command 2>/dev/null \
    | grep 'ssh\.sock' | grep '\[mux\]' | grep -v grep | awk '{print $1}' | head -1
}

# Record master PID transitions — the tick it changes is the break second (30s res).
track_master() {
  local now prev
  now="$(master_pid)"
  prev="$(cat "$PIDFILE" 2>/dev/null)"
  if [ "$now" != "$prev" ]; then
    echo "$(date '+%Y-%m-%dT%H:%M:%S%z') master pid: '${prev:-none}' -> '${now:-none}'" >> "$PIDLOG"
    echo "$now" > "$PIDFILE"
  fi
}

capture_break() {
  local out="/tmp/forward-break-$(date +%Y%m%d-%H%M%S).txt"
  local stamp; stamp="$(date +%Y%m%d-%H%M%S)"
  {
    echo "### host<->VM forward break — captured $(date) by forward-watchdog"
    echo "### captured BEFORE any restart (a colima restart recreates ha.stderr.log)"
    echo "### last known SSH master pid: $(cat "$PIDFILE" 2>/dev/null || echo unknown)"

    # ---- 1. THE decisive artifact: full lima logs + signal-vs-exit grep ----
    echo; echo "== ha.stderr.log / ha.stdout.log copied to /tmp/ha-*-$stamp.log =="
    sudo -n cp "$LIMA/ha.stderr.log" "/tmp/ha-stderr-$stamp.log" 2>&1 && \
      sudo -n chmod 644 "/tmp/ha-stderr-$stamp.log" 2>&1
    sudo -n cp "$LIMA/ha.stdout.log" "/tmp/ha-stdout-$stamp.log" 2>&1 && \
      sudo -n chmod 644 "/tmp/ha-stdout-$stamp.log" 2>&1
    ls -l "/tmp/ha-stderr-$stamp.log" "/tmp/ha-stdout-$stamp.log" 2>&1

    echo; echo "== SIGNAL vs -O exit (a signal death prints 'Killed by signal N'; -O exit prints nothing) =="
    sudo -n grep -nE 'Killed by signal|closed by remote host|Timeout|Corrupted|Bad packet|out of memory|-O exit|-O stop|shutting down the SSH master|Received SIG' \
      "$LIMA/ha.stderr.log" 2>&1 | tail -40 || echo "(no match / need root)"

    # ---- 2. Who is alive right now ----
    echo; echo "== ssh / limactl / qemu / socat processes =="
    ps -axo pid,ppid,pgid,sess,user,lstart,etime,stat,command 2>/dev/null \
      | grep -E '[s]sh|[l]imactl|[q]emu|[s]ocat' | head -25
    echo; echo "== master pid transition log =="
    tail -10 "$PIDLOG" 2>/dev/null
    echo; echo "== ssh -O check (single mux command, master is already gone) =="
    run_to 15 $DH ssh -O check -S "$LIMA/ssh.sock" 127.0.0.1 2>&1

    # ---- 3. Actor hunt: sudo logs every command it runs ----
    echo; echo "== unified log, last 5m (sudo/ssh/limactl/colima/jetsam) =="
    sudo -n log show --last 5m --style compact --predicate \
      'process == "sudo" OR process == "ssh" OR process == "limactl" OR process == "colima" OR eventMessage CONTAINS "_dockerhost" OR (process == "kernel" AND (eventMessage CONTAINS "memorystatus" OR eventMessage CONTAINS "jetsam"))' \
      2>&1 | tail -120 || echo "(need root)"

    # ---- 4. lima dirs + usernet ----
    echo; echo "== _lima/colima + usernet =="
    sudo -n ls -la "$LIMA/" 2>&1 | head -20
    sudo -n ls -la /var/_dockerhost/.colima/_lima/_networks/user-v2/ 2>&1 | head -12
    sudo -n tail -20 /var/_dockerhost/.colima/_lima/_networks/user-v2/*.log 2>&1 | tail -25

    # ---- 5. Host pressure ----
    echo; echo "== host =="
    uptime; sysctl vm.swapusage 2>&1; vm_stat 2>&1 | head -8
    ps -axo rss,user,pid,comm 2>/dev/null | sort -rn | head -15

    echo; echo "== relay log tail =="
    tail -30 /tmp/docker-relay.log 2>&1

    echo; echo "== colima status =="
    run_to 20 $DH colima status 2>&1

    # ---- 6. Guest LAST: `colima ssh` RE-CREATES the master, changing the state ----
    echo; echo "== GUEST PROBES START $(date) — note: colima ssh re-creates the SSH master =="
    echo "-- sshd disconnect reason + logind (the decisive guest-side line) --"
    run_to 25 $DH colima ssh -- sudo journalctl -o short-iso --since -15min --no-pager 2>&1 \
      | grep -viE 'dockerd|containerd|SyncTime' | tail -40
    echo "-- kernel --"
    run_to 20 $DH colima ssh -- sudo journalctl -k --since -15min --no-pager 2>&1 | tail -20
    echo "-- zombies with parents --"
    run_to 20 $DH colima ssh -- sh -c "ps -eo pid,ppid,stat,user,etime,comm | awk '\$3 ~ /Z/'" 2>&1 | head -20
    echo "-- pressure / load --"
    run_to 15 $DH colima ssh -- sh -c 'cat /proc/pressure/cpu /proc/loadavg' 2>&1
    echo "-- docker events (in-memory, LOST on restart) --"
    run_to 25 $DH colima ssh -- docker events --since 15m --until 0s 2>&1 | tail -40
    echo "-- containers --"
    run_to 25 $DH colima ssh -- docker ps -a --format '{{.Names}}\t{{.Status}}\t{{.CreatedAt}}' 2>&1

    echo; echo "### end of capture"
  } > "$out" 2>&1
  echo "$out" > "$MARKER"
  echo "$(date) forward break — forensics captured to $out"
}

while true; do
  track_master
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
