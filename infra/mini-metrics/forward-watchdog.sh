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
VM=http://localhost:8428/api/v1/import/prometheus
D=/usr/local/bin/docker   # reaches the VM's dockerd via the socat relay (/var/run/docker.sock)

while true; do
  # Canonical "host can talk to the VM" test — the exact path the operator's CLI
  # and the mini-metrics collector use. Fails the instant the forward breaks.
  if $D ps -q >/dev/null 2>&1; then
    printf 'mini_forward_up{box="mini"} 1\n' \
      | curl -s -m8 -o /dev/null --data-binary @- "$VM" || true
  fi
  sleep 30
done
