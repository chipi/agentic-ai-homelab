# dgx-scrape — DGX telemetry bridge (interim)

A launchd loop **on the mini** that pulls DGX telemetry into VictoriaMetrics,
because OrbStack containers on the mini can't reach the DGX LAN IP but the mini
host shell can. Every 20s it:

1. **Scrapes the DGX exporters over LAN** — dcgm (`:9400`, GPU) + cadvisor
   (`:8080`, containers) → VM with `host=dgx`, `instance=dgx-llm-1`.
2. **TCP health-check** each DGX service → `dgx_service_up{service=…}` for
   ollama/whisper/diarization/openai-whisper/moss/cadvisor/dcgm. **TCP-open, not
   HTTP**: the inference servers saturate under load and stop answering HTTP
   `/health` while still serving (MOSS during load tests) — a listening port is
   the honest "is it up" signal; a crashed service closes its port.

## Interim
This is a stopgap. The designed model is a push-collector **on the DGX** itself
(node-exporter + Alloy) shipping to the mini — blocked on the DGX's login being
wedged (no shell). Until then this LAN pull gives GPU + container metrics +
service health, but **not** DGX host CPU/mem/disk (node-exporter :9100 is down
on the box) or per-container names (cadvisor there exposes only cgroup ids).

## Install
```sh
cp push.sh ~/obs-dgx-scrape/push.sh && chmod +x ~/obs-dgx-scrape/push.sh
cp com.homelab.dgx-scrape.plist ~/Library/LaunchAgents/
launchctl load -w ~/Library/LaunchAgents/com.homelab.dgx-scrape.plist
```
