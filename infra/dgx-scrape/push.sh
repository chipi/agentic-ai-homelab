#!/bin/bash
# DGX service health -> local VictoriaMetrics: TCP health-check each DGX service,
# emitting dgx_service_up{service}. host=dgx, instance=dgx-llm-1. Runs on the mini.
#
# METRICS + LOGS now ship from Grafana Alloy running ON the DGX (host/GPU/cadvisor/
# vLLM/ollama metrics + container logs -> mini). This script is trimmed to the ONE
# signal Alloy doesn't provide: dgx_service_up (TCP reachability of each service).
# It no longer scrapes dcgm/cadvisor/app /metrics — that would duplicate Alloy.
#
# Reached over the TAILNET (dgx-llm-1). TCP-open (not HTTP) is the health signal:
# inference servers saturate under load and stop answering HTTP /health promptly
# while still serving (MOSS during load tests) — a listening port is the honest
# "is it up". A crashed service closes its port (e.g. openai-whisper :8002).
DGX=dgx-llm-1
VM="http://localhost:8428/api/v1/import/prometheus?extra_label=host=dgx&extra_label=instance=dgx-llm-1"
VMPLAIN="http://localhost:8428/api/v1/import/prometheus"
# openai-whisper (:8002) retired — speaches (:8000) won the #952 transcription
# bake-off; its files stay on the DGX but it's no longer a monitored service.
SVCS="ollama:11434 whisper:8000 diarization:8001 moss:8004 cadvisor:8080 dcgm:9400"
while true; do
  {
    for s in $SVCS; do
      n=${s%%:*}; port=${s##*:}
      nc -z -G2 -w2 "$DGX" "$port" 2>/dev/null && up=1 || up=0
      printf 'dgx_service_up{service="%s"} %s\n' "$n" "$up"
    done
  } | curl -s -m8 -o /dev/null --data-binary @- "$VM"
  # Compose-app inventory, mirroring the mini's compose_app_* metrics. The DGX's
  # cadvisor only exposes cgroup ids (no container names), so read `docker ps`
  # over keyless Tailscale SSH (mini -> dgx, ACL tag:homelab-host -> :22). Emits
  # compose_app_up/running/total{app,box="dgx"} to the PLAIN endpoint (no host/
  # instance labels — a per-box inventory metric, queried by box like the mini).
  # Non-fatal: an SSH/DGX hiccup skips this cycle, health checks above still ship.
  # total EXCLUDES cleanly-exited one-shots (Exited (0)); fall back to the raw count
  # when nothing runs, so a fully-stopped project still reads red (see mini-metrics).
  ssh -o BatchMode=yes -o ConnectTimeout=8 -o StrictHostKeyChecking=accept-new ops@"$DGX" \
      'docker ps -a --format "{{.Label \"com.docker.compose.project\"}}|{{.State}}|{{.Status}}"' 2>/dev/null \
    | awk -F'|' '$1!=""{a[$1]++; if($2=="running")r[$1]++; else if($3 ~ /^Exited \(0\)/)e0[$1]++}
        END{for(p in a){run=r[p]+0; tot=a[p]-(e0[p]+0); if(run==0)tot=a[p]; u=(run==tot && tot>0)?1:0;
          printf "compose_app_up{app=\"%s\",box=\"dgx\"} %d\ncompose_app_running{app=\"%s\",box=\"dgx\"} %d\ncompose_app_total{app=\"%s\",box=\"dgx\"} %d\n",p,u,p,run,p,tot}}' \
    | curl -s -m8 -o /dev/null --data-binary @- "$VMPLAIN" || true
  # per-container detail (name/state/uptime/port) for the DGX Containers table,
  # via the shared ctr.py (runs here on the mini over the SSH'd inspect output).
  CFMT=$(printf '{{.Name}}\t{{.State.Status}}\t{{.State.StartedAt}}\t{{index .Config.Labels "com.docker.compose.project"}}\t{{json .NetworkSettings.Ports}}\t{{.State.ExitCode}}\t{{if .State.Health}}{{.State.Health.Status}}{{else}}-{{end}}')
  ssh -o BatchMode=yes -o ConnectTimeout=8 ops@"$DGX" "docker inspect \$(docker ps -aq) --format '$CFMT'" 2>/dev/null \
    | python3 "$(cd "$(dirname "$0")" && pwd)/../mini-metrics/ctr.py" dgx \
    | curl -s -m8 -o /dev/null --data-binary @- "$VMPLAIN" || true
  sleep 20
done
