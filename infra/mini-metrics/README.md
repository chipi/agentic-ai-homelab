# mini-metrics — Mac mini host metrics collector to VictoriaMetrics

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
   `mini_container_mem_bytes{name}` + `compose_app_up/running/total{app,box}`
   (which compose stacks are up).
5. **CPU temperature** (`mini_cpu_temp_celsius`) — the mini runs 24/7, so thermals
   matter. macOS has no `node_hwmon`; read via the SMC (no sudo). See below.
6. **Disk IO** (`mini_disk_io_bytes_per_sec`, `mini_disk_tps`) via `iostat`
   (darwin node_exporter omits `node_disk_*`).

## CPU temperature — `osx-cpu-temp` (GPL, self-provisioning, not vendored)
macOS exposes CPU die temp only via the SMC. `osx-cpu-temp` reads it **without
sudo** on Intel Macs. It's GPL, so it's **not vendored** into this MIT repo.

**Reproducibility (config management):** `push.sh` **builds it itself on first
run** if the binary is missing (`git clone` + `make`, next to the script,
gitignored) — so a fresh machine reinstall gets CPU temp with **no manual step**.
It needs Xcode Command-Line Tools (`git`+`make`) present and one network fetch;
if either is missing it silently skips and the temp metric is just absent. To
force/verify the build manually:
```sh
git clone --depth 1 https://github.com/lavoiesl/osx-cpu-temp /tmp/osx-cpu-temp
make -C /tmp/osx-cpu-temp && cp /tmp/osx-cpu-temp/osx-cpu-temp ./osx-cpu-temp
```
(Apple-Silicon Macs need a different reader; this box is Intel i7-8700B.)

## Install (run-in-place from the repo — no copy-out)
The plist points at `push.sh` **in this repo checkout**
(`…/agentic-ai-homelab/infra/mini-metrics/push.sh`), so a `git pull` ships
script updates with no re-copy.
```sh
chmod +x push.sh
cp com.homelab.mini-metrics.plist ~/Library/LaunchAgents/
launchctl load -w ~/Library/LaunchAgents/com.homelab.mini-metrics.plist
```
The plist hardcodes `/Users/markodragoljevic/...` (operator restore). After
editing `push.sh`, `pkill -f mini-metrics/push.sh` — launchd respawns with the
new script (bash caches the running copy).

## Forward watchdog — `forward-watchdog.sh`

A **second** launchd job (`com.homelab.forward-watchdog`), separate from the 20s
collector: every 30s it proves `docker ps` works, then heart-beats
`mini_forward_up{box="mini"}=1` over the **forwarded** `:8428`. Because the
heartbeat rides the same lima forward, it stops the instant colima's host↔VM
forward breaks on a network transition — and the `mini-forward-down` alert
(`rules.yaml`, a dead-man's switch) fires. Detect-only; recovery is a human
`colima restart`. Full story + resilience roadmap:
[colima/lima forwarding recovery](../../docs/recipes/colima-lima-forwarding-recovery.md).

```sh
cp com.homelab.forward-watchdog.plist ~/Library/LaunchAgents/
launchctl load -w ~/Library/LaunchAgents/com.homelab.forward-watchdog.plist
```

## Related

- Systems index: [`infra/README.md`](../README.md)
- Global docs: [Pillar 2 — Local AI infra](https://github.com/chipi/agentic-ai-homelab/blob/main/docs/local-ai-infra.md)
