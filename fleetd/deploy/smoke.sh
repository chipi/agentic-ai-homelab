#!/usr/bin/env bash
# fleetd smoke: exercises cycle-run, spend accounting, STOP flag, budget pause.
set -euo pipefail
cd "$(dirname "$0")/.."
T=$(mktemp -d)
trap 'rm -rf "$T"' EXIT
cat > "$T/cfg.json" <<EOF
{"vm_url":"","vl_url":"","state_file":"$T/state.json","fleets":[
 {"name":"smoke","enabled":true,"interval":"1m",
  "cycle_cmd":"echo cycle ran; echo 0.0123 > $T/spend",
  "workdir":"$T","stop_flag":"$T/STOP","budget_day_usd":1.0,
  "spend_file":"$T/spend","stage":"shadow","cycle_timeout":"1m"}]}
EOF
OUT=$(./fleetd -config "$T/cfg.json" -once 2>&1)
echo "$OUT" | grep -q "cycle smoke-.*: ok" || { echo "cycle did not run ok:"; echo "$OUT"; exit 1; }
grep -q '"smoke":0.0123' "$T/state.json" || { echo "spend accounting wrong:"; cat "$T/state.json"; exit 1; }
touch "$T/STOP"
./fleetd -config "$T/cfg.json" -once 2>&1 | grep -q "STOP flag present" || { echo "stop flag not honored"; exit 1; }
rm "$T/STOP"
python3 - "$T/cfg.json" <<'PY'
import json,sys
p=sys.argv[1]; c=json.load(open(p)); c["fleets"][0]["budget_day_usd"]=0.01
json.dump(c,open(p,"w"))
PY
./fleetd -config "$T/cfg.json" -once 2>&1 | grep -q "daily budget reached" || { echo "budget guard not honored"; exit 1; }
echo "smoke: cycle+spend+stopflag+budget all honored"
