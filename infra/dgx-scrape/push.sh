#!/bin/bash
# DGX telemetry -> local VictoriaMetrics: scrape GPU (dcgm) + container (cadvisor)
# + FastAPI app metrics (moss, diarization) + TCP health-check each DGX service.
# host=dgx, instance=dgx-llm-1. Scraped from the mini (not pushed from the DGX).
#
# Reached over the TAILNET (dgx-llm-1) — was the LAN IP 192.168.1.111, but that's
# fragile (DHCP-assigned, changed when the DGX dropped off the home LAN while
# staying up on the tailnet). The tailnet name is stable. Requires the tailnet
# ACL to grant tag:homelab-host -> tag:dgx-llm-host (podcast_scraper-infra
# tailscale/policy.hujson) — until that's applied, these scrapes are ACL-denied.
#
# TCP-open (not HTTP) is the health signal: the inference servers saturate under
# load and stop answering HTTP /health promptly while still serving (MOSS during
# load tests) — TCP-listening is the honest "is it up" check. A crashed service
# closes its port (e.g. openai-whisper :8002).
DGX=dgx-llm-1
VM="http://localhost:8428/api/v1/import/prometheus?extra_label=host=dgx&extra_label=instance=dgx-llm-1"
SVCS="ollama:11434 whisper:8000 diarization:8001 openai-whisper:8002 moss:8004 cadvisor:8080 dcgm:9400"
while true; do
  {
    curl -s -m5 "http://$DGX:9400/metrics"
    curl -s -m5 "http://$DGX:8080/metrics"
    for s in $SVCS; do
      n=${s%%:*}; port=${s##*:}
      nc -z -G2 -w2 "$DGX" "$port" 2>/dev/null && up=1 || up=0
      printf 'dgx_service_up{service="%s"} %s\n' "$n" "$up"
    done
  } | curl -s -m8 -o /dev/null --data-binary @- "$VM"
  # FastAPI app metrics over LAN, labelled by job so the DGX-Services board's
  # $service (= label_values(http_requests_total, job)) + FastAPI panels light up.
  # Only apps exposing a Prometheus /metrics endpoint; a down/empty one is skipped.
  for app in moss-app:8004 pyannote-app:8001; do
    job=${app%%:*}; port=${app##*:}
    curl -s -m5 "http://$DGX:$port/metrics" \
      | curl -s -m8 -o /dev/null --data-binary @- \
        "http://localhost:8428/api/v1/import/prometheus?extra_label=host=dgx&extra_label=instance=dgx-llm-1&extra_label=job=$job"
  done
  sleep 20
done
