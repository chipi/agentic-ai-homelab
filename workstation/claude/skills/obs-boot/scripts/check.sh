#!/usr/bin/env bash
# Read-only health check of the self-hosted observability stack (backend on the Mac mini,
# collectors on the mini, the DGX and prod). Prints PASS/FAIL per check; exit 1 on any FAIL.
#
#   check.sh [--stale-seconds 600]
# Env: HOMELAB_SSH (default: the Mac mini), DGX_SSH (default: ssh markodragoljevic@dgx-llm-1;
# a bare `ssh dgx-llm-1` logs in as the local user, which the tailnet refuses from the X3)
set -uo pipefail
STALE="${2:-600}"; [ "${1:-}" = "--stale-seconds" ] || STALE=600
MINI="${HOMELAB_SSH:-ssh -i $HOME/.ssh/homelab_mini -o IdentitiesOnly=yes markodragoljevic@homelab}"
DGX="${DGX_SSH:-ssh -o ConnectTimeout=10 markodragoljevic@dgx-llm-1}"
fail=0
ok()  { printf 'PASS  %s\n' "$*"; }
bad() { printf 'FAIL  %s\n' "$*"; fail=1; }

echo "== backend + services on the mini"
out=$($MINI 'export PATH=/usr/local/bin:$PATH
  for u in 3000/api/health 8428/health 9428/health 10428/health 8090/_health/; do
    echo "health $u $(curl -s -o /dev/null -w "%{http_code}" -m5 http://127.0.0.1:$u)"; done
  for c in victoriametrics victorialogs victoriatraces grafana glitchtip-web-1 alloy-homelab caddy; do
    echo "container $c $(docker inspect -f "{{.State.Status}}" $c 2>/dev/null || echo missing)"; done
  for l in dgx-scrape mini-metrics forward-watchdog; do
    echo "launchd $l $(sudo -n launchctl print system/com.homelab.$l 2>/dev/null | grep -m1 "state =" | sed "s/.*state = //" || echo missing)"; done
  curl -s http://127.0.0.1:8428/api/v1/query --data-urlencode "query=time() - max by (instance) (timestamp(up))" \
    | python3 -c "import sys,json; [print(\"fresh\", r[\"metric\"].get(\"instance\",\"?\"), round(float(r[\"value\"][1]))) for r in json.load(sys.stdin)[\"data\"][\"result\"]]"
  curl -s http://127.0.0.1:8428/api/v1/query --data-urlencode "query=time() - max by (job) (timestamp(up{job=\"postgres\",instance=\"prod-podcast\"}))" \
    | python3 -c "import sys,json; [print(\"jobfresh\", r[\"metric\"].get(\"job\",\"?\"), round(float(r[\"value\"][1]))) for r in json.load(sys.stdin)[\"data\"][\"result\"]]"
  curl -s http://127.0.0.1:8428/api/v1/query --data-urlencode "query=time() - max(last_over_time(closelistening_pg_backup_last_success_timestamp_seconds{instance=\"prod-podcast\",run_id=\"\"}[3d]))" \
    | python3 -c "import sys,json; [print(\"backupage\", \"postgres\", round(float(r[\"value\"][1]))) for r in json.load(sys.stdin)[\"data\"][\"result\"]]"' 2>&1)
[ -n "$out" ] || bad "could not reach the mini over ssh"
while read -r kind what val; do
  case "$kind" in
    health)    [ "$val" = 200 ] && ok "endpoint :$what -> $val" || bad "endpoint :$what -> $val" ;;
    container) [ "$val" = running ] && ok "container $what running" || bad "container $what: $val" ;;
    launchd)   [ "$val" = running ] && ok "loop $what running" || bad "loop $what: ${val:-not running} (a periodic loop between runs shows 'not running' — check its log before acting)" ;;
    fresh)     [ "$val" -le "$STALE" ] && ok "metrics from $what: last sample ${val}s ago" || bad "metrics from $what: last sample ${val}s ago (> ${STALE}s)" ;;
    jobfresh)  [ "$val" -le "$STALE" ] && ok "prod $what exporter scraped ${val}s ago" || bad "prod $what exporter: last scrape ${val}s ago (> ${STALE}s)" ;;
    backupage) [ "$val" -le 93600 ] && ok "prod $what backup ${val}s old" || bad "prod $what backup ${val}s old (> 26 h)" ;;
  esac
done <<< "$out"
for inst in homelab dgx-llm-1 prod-podcast; do
  grep -q "^fresh $inst " <<< "$out" || bad "no metrics at all from $inst"
done
grep -q "^jobfresh postgres " <<< "$out" || bad "no metrics from the prod Postgres exporter (job=postgres)"
grep -q "^backupage postgres " <<< "$out" || bad "no prod Postgres backup pushed in 3 days"

echo "== collectors on the DGX"
d=$($DGX 'for c in alloy dcgm-exporter cadvisor; do echo "$c $(docker inspect -f "{{.State.Status}}" $c 2>/dev/null || echo missing)"; done' 2>&1)
[ -n "$d" ] || bad "could not reach the DGX over ssh"
while read -r c st; do
  [ "$st" = running ] && ok "DGX $c running" || bad "DGX $c: $st"
done <<< "$d"

echo "== alert rules: repo vs live Grafana"
r=$($MINI 'cd ~/agentic-ai-homelab && python3 infra/observability/rules-drift/drift.py --repo infra/observability/backend/grafana/provisioning/alerting/rules.yaml --grafana http://localhost:3000 --env infra/observability/backend/.env 2>&1 | head -1')
case "$r" in "drift: 0 rule(s)"*) ok "$r" ;; *) bad "${r:-drift check produced no output}" ;; esac

echo
[ "$fail" = 0 ] && echo "RESULT: PASS" || echo "RESULT: FAIL"
exit "$fail"
