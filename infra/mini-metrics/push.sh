#!/bin/bash
# Mini host metrics -> VictoriaMetrics: node_exporter scrape (node_*, instance=homelab)
# + custom mini_* summaries + service health + docker stats (host=mini).
VM=http://localhost:8428/api/v1/import/prometheus
D=/usr/local/bin/docker
PAGE=$(sysctl -n hw.pagesize); TOTAL=$(sysctl -n hw.memsize)
SVCS="grafana:3000:/api/health glitchtip:8090:/_health/ langfuse:4000:/api/public/health umami:3001:/api/heartbeat victoriametrics:8428:/health"
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
  RUN=$($D ps -q 2>/dev/null | wc -l | tr -d " "); TOT=$($D ps -aq 2>/dev/null | wc -l | tr -d " ")
  RST=$($D ps --filter status=restarting -q 2>/dev/null | wc -l | tr -d " ")
  UNH=$($D ps --filter health=unhealthy -q 2>/dev/null | wc -l | tr -d " ")
  {
    printf 'mini_cpu_used_percent %s\nmini_mem_used_percent %s\nmini_mem_used_bytes %s\nmini_mem_total_bytes %s\nmini_disk_free_bytes %s\nmini_disk_used_percent %s\nmini_load1 %s\nmini_load5 %s\nmini_load15 %s\nmini_swap_used_bytes %s\nmini_uptime_seconds %s\n' \
      "$CPU" "$MEMPCT" "$USED_B" "$TOTAL" "$FREE_B" "$DPCT" "$L1" "$L5" "$L15" "$SWAP_B" "$UP"
    printf 'mini_docker_running %s\nmini_docker_total %s\nmini_docker_restarting %s\nmini_docker_unhealthy %s\n' "$RUN" "$TOT" "$RST" "$UNH"
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
  } | curl -s -o /dev/null --data-binary @- "$VM?extra_label=host=mini"
  sleep 20
done
