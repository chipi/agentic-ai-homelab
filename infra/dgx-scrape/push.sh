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
  sleep 20
done
