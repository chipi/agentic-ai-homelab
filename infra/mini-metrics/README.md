# mini-metrics — mac mini host collector

A launchd loop on the mini that feeds VictoriaMetrics the signals macOS can't
get from a containerized exporter. Every 20s it:

1. **Scrapes the local `node_exporter`** (`:9100`) → VM as `node_*` with
   `instance=homelab` — this is what the "Homelab — Mac mini" Grafana dashboard
   queries. (node_exporter runs natively via brew; a container can't read the
   macOS host.)
2. Pushes custom summaries for the start page: `mini_cpu/mem/disk`, `mini_load*`,
   `mini_swap_used_bytes`, `mini_uptime_seconds` (`host=mini`).
3. **Service health** — `service_up{service=…}` for grafana/glitchtip/langfuse/
   umami/victoriametrics (HTTP health checks).
4. **Docker stats** via the docker CLI — `mini_docker_running/total/restarting/
   unhealthy` + per-container `mini_container_cpu_percent{name}` /
   `mini_container_mem_bytes{name}`.

## Install
```sh
cp push.sh ~/mini-metrics/push.sh && chmod +x ~/mini-metrics/push.sh
cp com.homelab.mini-metrics.plist ~/Library/LaunchAgents/
launchctl load -w ~/Library/LaunchAgents/com.homelab.mini-metrics.plist
```
The plist hardcodes `/Users/markodragoljevic/...` paths (operator restore).
Editing `push.sh` requires `pkill -f mini-metrics/push.sh` (launchd respawns
with the new script — bash caches the running copy).
