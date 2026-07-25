#!/usr/bin/env bash
# Advisor episode (BAKEOFF §4.2 / ADR-0003 advisor pattern) — a stronger
# reasoner consulted ONCE at the stuck point. Read-only: it locates the true
# owner of the symptom and produces a pin + rationale; it never fixes.
# Spends premium tokens only where the cheap seats measurably fail
# (fly-physics: pure owner-localization, 0/3 without a pin, 3/3 with).
#
# Usage: ./advisor_run.sh <ticket.json> <worker-result-dir>
# Output: <worker-result-dir>/advisor.json  {file, function, decoy, rationale}
set -euo pipefail
export NODE_OPTIONS="--max-old-space-size=4096"

BUG_JSON="$1"; WOUT="$2"
ROOT="$HOME/.bugfix-fleet/bakeoff"
WT="$ROOT/orrery"
HERE="$(cd "$(dirname "$0")" && pwd)"
MODEL="${ADVISOR_MODEL:-z-ai/glm-5.2}"   # ladder rung 2 (reasoner); swappable

DESC=$(jq -r .description "$BUG_JSON")
WTOUCHED=$(paste -sd, "$WOUT/touched.txt" 2>/dev/null | sed 's/^,*//;s/,*$//')
WVERDICT=$(cut -f3 "$WOUT/result.tsv" 2>/dev/null || echo "FAIL")

read -r -d '' PROMPT <<EOF || true
You are a senior engineer doing a READ-ONLY consultation. A cheaper agent
tried to fix the bug below and FAILED — its patch touched the wrong place.
Your ONLY job: locate the true owner of the symptom in this repository.
Do not fix anything. Do not edit any file.

## Bug report
$DESC

## Failed attempt evidence
- verdict: $WVERDICT
- files the failed patch touched: ${WTOUCHED:-unknown}

Investigate the code (trace the symptom's actual runtime path: which module
computes the value / owns the behavior the report describes — beware
look-alike functions in other layers). Then reply with ONLY a JSON object
in a \`\`\`json fenced block:
{"file": "path of the true owner", "function": "the function to change",
 "decoy": "the wrong-but-tempting path the failed patch fell into",
 "rationale": "2-3 sentences: why this owner, traced how"}
EOF

echo "══ advisor episode ($MODEL) ══"
SECONDS=0
( cd "$WT" && pi -p --mode json --model "$MODEL" "$PROMPT" < /dev/null ) \
  > "$WOUT/advisor-raw.json" 2> "$WOUT/advisor.err" || true
WALL=$SECONDS
python3 - "$WOUT/advisor-raw.json" "$WOUT/advisor.json" <<'PY' || true
import json, re, sys
text = ""
for line in open(sys.argv[1]):
    line = line.strip()
    if not line: continue
    try: e = json.loads(line)
    except json.JSONDecodeError: continue
    m = e.get("message") or {}
    if m.get("role") == "assistant":
        for p in m.get("content") or []:
            if isinstance(p, dict) and p.get("type") == "text":
                text += p.get("text") or ""
blocks = re.findall(r"```json\s*(.*?)```", text, re.S)
if not blocks:
    print("ADVISOR: no JSON"); sys.exit(3)
try:
    obj = json.loads(blocks[-1])
except json.JSONDecodeError as ex:
    print(f"ADVISOR: bad JSON ({ex})"); sys.exit(3)
json.dump(obj, open(sys.argv[2], "w"), indent=2)
print("ADVISOR: ok")
PY
if [ -f "$WOUT/advisor.json" ]; then
  echo "ADVISOR PIN: $(jq -r '.file + " :: " + .function' "$WOUT/advisor.json")  (${WALL}s)"
else
  echo "ADVISOR: no usable output (${WALL}s)"; exit 4
fi