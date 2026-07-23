#!/bin/bash
# DGX telemetry -> local VictoriaMetrics: scrape GPU (dcgm) + container (cadvisor)
# exporters over LAN + TCP health-check each DGX service. host=dgx.
# TCP-open (not HTTP) is the health signal: the inference servers saturate under
# load and stop answering HTTP /health promptly while still serving (MOSS during
# load tests) — TCP-listening is the honest "is it up" check. A crashed service
# closes its port (e.g. openai-whisper :8002).
DGX=192.168.1.111
VM="http://localhost:8428/api/v1/import/prometheus?extra_label=host=dgx&extra_label=instance=dgx-llm-1"
SVCS="ollama:11434 whisper:8000 diarization:8001 openai-whisper:8002 moss:8004 cadvisor:8080 dcgm:9400"
while true; do
  {
    curl -s -m5 "http://$DGX:9400/metrics"
    curl -s -m5 "http://$DGX:8080/metrics"
    for s in $SVCS; do
      n=${s%%:*}; port=${s##*:}
      nc -z -G2 "$DGX" "$port" 2>/dev/null && up=1 || up=0
      printf 'dgx_service_up{service="%s"} %s\n' "$n" "$up"
    done
  } | curl -s -o /dev/null --data-binary @- "$VM"
  sleep 20
done
