#!/bin/bash
# Mini host metrics -> VictoriaMetrics. Everything carries instance=homelab so the
# box is queryable by one label (matching node_exporter + prod/dgx). Sources:
# node_exporter scrape (node_*) + custom mini_* summaries (CPU/mem/disk/IO/load,
# macOS-specific — darwin node_exporter omits mem + disk IO) + service_up health
# + docker stats. Custom metrics also keep host=mini for back-compat.
VM=http://localhost:8428/api/v1/import/prometheus
D=/usr/local/bin/docker
PAGE=$(sysctl -n hw.pagesize); TOTAL=$(sysctl -n hw.memsize)
SVCS="grafana:3000:/api/health glitchtip:8090:/_health/ langfuse:4000:/api/public/health umami:3001:/api/heartbeat litellm:4001:/health/liveliness victoriametrics:8428:/health victorialogs:9428:/health victoriatraces:10428:/health"
# CPU-temp reader (osx-cpu-temp, GPL — GPL so not vendored into this MIT repo).
# SELF-PROVISIONING: build it once, next to this script, if missing — so a fresh
# machine reinstall gets CPU temp with no manual step (needs Xcode CLT git+make +
# one network fetch; silently skips if unavailable). This is the reproducibility
# story for the tool — the collector installs its own dependency on first run.
TBIN="$(cd "$(dirname "$0")" && pwd)/osx-cpu-temp"
if [ ! -x "$TBIN" ] && command -v git >/dev/null 2>&1 && command -v make >/dev/null 2>&1; then
  _t=$(mktemp -d) && git clone --depth 1 -q https://github.com/lavoiesl/osx-cpu-temp "$_t" 2>/dev/null \
    && make -C "$_t" >/dev/null 2>&1 && cp "$_t/osx-cpu-temp" "$TBIN" && chmod +x "$TBIN"; rm -rf "$_t"
fi
while true; do
  curl -s -m5 http://localhost:9100/metrics | curl -s -o /dev/null --data-binary @- "$VM?extra_label=instance=homelab"
  IDLE=$(top -l2 -n0 | grep "CPU usage" | tail -1 | sed "s/.*, \([0-9.]*\)% idle.*/\1/")
  CPU=$(echo "100 - ${IDLE:-100}" | bc -l 2>/dev/null)
  read AW CW WW < <(vm_stat | awk '/Pages active/{a=$3}/Pages wired/{w=$4}/Pages occupied by compressor/{c=$5}END{gsub("[.]","",a);gsub("[.]","",w);gsub("[.]","",c);print a,c,w}')
  USED_B=$(( (${AW:-0}+${CW:-0}+${WW:-0})*PAGE )); MEMPCT=$(echo "scale=2;$USED_B*100/$TOTAL"|bc -l)
  read AVAIL CAP < <(df -k / | tail -1 | awk '{print $4,$5}'); FREE_B=$(( ${AVAIL:-0}*1024 )); DPCT=${CAP%\%}
  read L1 L5 L15 < <(sysctl -n vm.loadavg | awk '{print $2,$3,$4}')
  SWAP_MB=$(sysctl -n vm.swapusage | sed 's/.*used = \([0-9.]*\)M.*/\1/'); SWAP_B=$(echo "${SWAP_MB:-0}*1048576/1"|bc)
  BOOT=$(sysctl -n kern.boottime | sed 's/.*{ sec = \([0-9]*\).*/\1/'); UP=$(( $(date +%s) - ${BOOT:-0} ))
  # Disk IO (macOS has no node_disk_* — darwin node_exporter omits it). iostat's
  # 1s sample: $2=transfers/s, $3=MB/s total (read+write; macOS doesn't split).
  read IOTPS IOMBPS < <(iostat -d -w1 -c2 disk0 2>/dev/null | tail -1 | awk '{print $2,$3}'); IOBPS=$(echo "${IOMBPS:-0}*1048576/1"|bc 2>/dev/null)
  # CPU temp via the self-provisioned osx-cpu-temp (TBIN set + built above);
  # silent if the build wasn't possible.
  TEMP=$([ -x "$TBIN" ] && "$TBIN" 2>/dev/null | awk '{print $1}')
  RUN=$($D ps -q 2>/dev/null | wc -l | tr -d " "); TOT=$($D ps -aq 2>/dev/null | wc -l | tr -d " ")
  RST=$($D ps --filter status=restarting -q 2>/dev/null | wc -l | tr -d " ")
  UNH=$($D ps --filter health=unhealthy -q 2>/dev/null | wc -l | tr -d " ")
  # Compose apps: running/total containers per compose project (the production
  # load) — so the page can show "which apps are up", not just a count.
  # total EXCLUDES cleanly-exited one-shots (Exited (0) — migrate/init jobs), so a
  # healthy app with a done init container reads all-green not amber. If nothing is
  # running, fall back to the raw count so a fully-stopped project still shows red.
  COMPOSE=$($D ps -a --format '{{.Label "com.docker.compose.project"}}|{{.State}}|{{.Status}}' 2>/dev/null \
    | awk -F'|' '$1!=""{a[$1]++; if($2=="running")r[$1]++; else if($3 ~ /^Exited \(0\)/)e0[$1]++}
        END{for(p in a){run=r[p]+0; tot=a[p]-(e0[p]+0); if(run==0)tot=a[p]; printf "%s %d %d\n",p,run,tot}}')
  {
    printf 'mini_cpu_used_percent %s\nmini_mem_used_percent %s\nmini_mem_used_bytes %s\nmini_mem_total_bytes %s\nmini_disk_free_bytes %s\nmini_disk_used_percent %s\nmini_disk_io_bytes_per_sec %s\nmini_disk_tps %s\nmini_load1 %s\nmini_load5 %s\nmini_load15 %s\nmini_swap_used_bytes %s\nmini_uptime_seconds %s\n' \
      "$CPU" "$MEMPCT" "$USED_B" "$TOTAL" "$FREE_B" "$DPCT" "${IOBPS:-0}" "${IOTPS:-0}" "$L1" "$L5" "$L15" "$SWAP_B" "$UP"
    [ -n "$TEMP" ] && printf 'mini_cpu_temp_celsius %s\n' "$TEMP"
    printf 'mini_docker_running %s\nmini_docker_total %s\nmini_docker_restarting %s\nmini_docker_unhealthy %s\n' "$RUN" "$TOT" "$RST" "$UNH"
    echo "$COMPOSE" | while read -r app run tot; do
      [ -z "$app" ] && continue
      up=0; [ "${run:-0}" = "${tot:-0}" ] && [ "${tot:-0}" -gt 0 ] && up=1
      printf 'compose_app_up{app="%s",box="mini"} %s\ncompose_app_running{app="%s",box="mini"} %s\ncompose_app_total{app="%s",box="mini"} %s\n' \
        "$app" "$up" "$app" "${run:-0}" "$app" "${tot:-0}"
    done
    for s in $SVCS; do
      n=${s%%:*}; r=${s#*:}; port=${r%%:*}; path=${r#*:}
      code=$(curl -s -o /dev/null -m3 -w "%{http_code}" "http://localhost:$port$path")
      up=0; [ "$code" = "200" ] && up=1; printf 'service_up{service="%s"} %s\n' "$n" "$up"
    done
    $D stats --no-stream --format '{{.Name}}|{{.CPUPerc}}|{{.MemUsage}}' 2>/dev/null | while IFS='|' read -r name cpu mem; do
      cpuv=${cpu%\%}; memu=${mem%% *}
      memb=$(echo "$memu" | awk '{v=$0;gsub(/[A-Za-z]/,"",v);u=$0;gsub(/[0-9.]/,"",u);m=(u=="GiB"?1073741824:(u=="MiB"?1048576:(u=="KiB"?1024:1)));printf "%d",v*m}')
      printf 'mini_container_cpu_percent{name="%s"} %s\nmini_container_mem_bytes{name="%s"} %s\n' "$name" "${cpuv:-0}" "$name" "${memb:-0}"
    done
  } | curl -s -o /dev/null --data-binary @- "$VM?extra_label=instance=homelab&extra_label=host=mini"
  # per-container detail (name/state/uptime/port) for the landing page's Containers
  # table — via ctr.py (shared with dgx-scrape). Carries its own box label.
  CFMT=$(printf '{{.Name}}\t{{.State.Status}}\t{{.State.StartedAt}}\t{{index .Config.Labels "com.docker.compose.project"}}\t{{json .NetworkSettings.Ports}}\t{{.State.ExitCode}}\t{{if .State.Health}}{{.State.Health.Status}}{{else}}-{{end}}')
  $D inspect $($D ps -aq) --format "$CFMT" 2>/dev/null \
    | python3 "$(cd "$(dirname "$0")" && pwd)/ctr.py" mini \
    | curl -s -m8 -o /dev/null --data-binary @- "$VM" || true
  # per-container cpu/mem BY NAME via docker stats (cAdvisor can't see containers on
  # colima's cgroup v2). --no-stream snapshot (~5s). Feeds container_cpu_percent /
  # container_memory_bytes{box="mini",name=…}.
  $D stats --no-stream --no-trunc --format '{{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}' 2>/dev/null \
    | python3 "$(cd "$(dirname "$0")" && pwd)/stats.py" mini \
    | curl -s -m10 -o /dev/null --data-binary @- "$VM" || true
  sleep 20
done
