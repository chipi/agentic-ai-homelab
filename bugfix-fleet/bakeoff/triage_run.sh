#!/usr/bin/env bash
# Triage intake eval (v1) — one L0 bug × the active triager (agents/triage.md).
# First-pass intake only (kickback_round=0):
#   1. reset worktree to the bug's base (bug present, no oracle, no substrate)
#   2. run the triager (rung-0 model) with the agent definition + the raw ticket
#   3. extract its JSON verdict, shape-check it (gate fields, L1 boundaries)
#   4. render an actionable verdict into a *triaged manifest* under bugs/triaged/
#      so the standard worker leg (run.sh) can measure the outcome end-to-end
# The triager must not touch code: any worktree diff is recorded as a violation.
#
# Usage:  ./triage_run.sh bugs/orrery-mission-arc-L0.json [pi]
# Kick-back second pass (a worker attempt FAILed; §6.2 2×2 routing):
#   ./triage_run.sh <original-L0.json> pi <worker-result-dir> <prior-triage.json>
set -euo pipefail
export NODE_OPTIONS="--max-old-space-size=4096"

BUG_JSON="$1"; HARNESS="${2:-pi}"
KB_EVIDENCE="${3:-}"; KB_PRIOR="${4:-}"       # both set → kick-back re-entry
ROOT="$HOME/.bugfix-fleet/bakeoff"
WT="$ROOT/orrery"
HERE="$(cd "$(dirname "$0")" && pwd)"

jqr(){ jq -r "$1" "$BUG_JSON"; }
ID=$(jqr .id); FIX=$(jqr .fix_commit); BASE="${FIX}^"; DESC=$(jqr .description)
MODEL="${TRIAGE_MODEL:-deepseek/deepseek-v4-flash}"   # rung 0 (BAKEOFF §4.1)
KB_ROUND=0
if [ -n "$KB_EVIDENCE" ]; then
  [ -f "$KB_PRIOR" ] || { echo "ABORT: kick-back needs the prior triage.json"; exit 2; }
  KB_ROUND=$(( $(jq -r '.kickback_round // 0' "$KB_PRIOR") + 1 ))
fi
SUFFIX=""; [ "$KB_ROUND" -gt 0 ] && SUFFIX="-kb$KB_ROUND"
OUT="$ROOT/results/${ID}-triage${SUFFIX}/$HARNESS"; mkdir -p "$OUT"
[ -f "$ROOT/langfuse.env" ] && { set -a; . "$ROOT/langfuse.env"; set +a; }

echo "══ [$ID → triage/$HARNESS/$MODEL] reset to base $BASE ══"
git -C "$WT" reset --hard "$BASE" >/dev/null
git -C "$WT" clean -fd >/dev/null

# agent definition body (frontmatter stripped) + the task wrapper
AGENT_DEF=$(awk '/^---$/{c++;next} c>=2' "$HERE/../agents/triage.md")
if [ "$KB_ROUND" -eq 0 ]; then
  read -r -d '' TASK <<EOF || true
This is a FIRST PASS (kickback_round = 0) on the issue below. The repository
you are in is the codebase the issue is about. Do not edit any file — you
only read. End your response with the JSON verdict and nothing after it,
in a \`\`\`json fenced block.

## Issue to triage (verbatim)

$DESC
EOF
else
  WVERDICT=$(cut -f3 "$KB_EVIDENCE/result.tsv"); WSCOPE=$(cut -f8 "$KB_EVIDENCE/result.tsv")
  WWALL=$(cut -f4 "$KB_EVIDENCE/result.tsv"); WTURNS=$(cut -f6 "$KB_EVIDENCE/result.tsv")
  WOUTTOK=$(cut -f7 "$KB_EVIDENCE/result.tsv")
  WOFFSCOPE=$(cat "$KB_EVIDENCE/off_scope.txt" 2>/dev/null || echo "")
  read -r -d '' TASK <<EOF || true
This is a KICK-BACK SECOND PASS (kickback_round = $KB_ROUND). A specialist
attempted your normalized problem and FAILED. Route by the verdict × scope
2×2 from your definition. Do not edit any file — you only read. End your
response with the JSON verdict and nothing after it, in a \`\`\`json fenced
block. Set kickback_round to $KB_ROUND in your output.

## Original issue (verbatim)

$DESC

## Your prior normalized problem

$(jq -c .problem "$KB_PRIOR")

## Failed attempt — evidence

- verdict: $WVERDICT
- scope_hit (patch touched the expected area): $WSCOPE
- off-scope files the patch touched instead: ${WOFFSCOPE:-none}
- burn: ${WWALL}s wall, ${WTURNS} turns, ${WOUTTOK} output tokens
EOF
fi
read -r -d '' PROMPT <<EOF || true
$AGENT_DEF

---

$TASK
EOF

echo "══ run triager ══"
SECONDS=0
MAX_WALL="${TRIAGE_MAX_WALL:-900}"
( cd "$WT" && pi -p --mode json --model "$MODEL" "$PROMPT" < /dev/null ) \
  > "$OUT/harness.json" 2> "$OUT/harness.err" &
HPID=$!
while kill -0 "$HPID" 2>/dev/null; do
  if [ "$SECONDS" -ge "$MAX_WALL" ]; then
    echo "   budget: wall ${MAX_WALL}s exceeded — cutting"
    pkill -P "$HPID" 2>/dev/null || true; kill "$HPID" 2>/dev/null || true
    sleep 2; pkill -9 -P "$HPID" 2>/dev/null || true; kill -9 "$HPID" 2>/dev/null || true
    break
  fi
  sleep 5
done
wait "$HPID" 2>/dev/null || true
WALL=$SECONDS
COST=$(jq -rs 'map(.message.usage.cost.total // empty) | add // 0' "$OUT/harness.json" 2>/dev/null || echo 0)
OUTTOK=$(jq -rs 'map(.message.usage.output // empty) | add // 0' "$OUT/harness.json" 2>/dev/null || echo 0)
echo "   triager: ${WALL}s  \$$COST  (out=$OUTTOK)"

# triager must not write: any diff is a role violation (recorded, not fatal)
TOUCHED=$(git -C "$WT" status --porcelain | wc -l | tr -d ' ')
[ "$TOUCHED" -gt 0 ] && echo "   VIOLATION: triager touched $TOUCHED file(s)"

echo "══ extract + shape-check verdict ══"
# extractor failure (no/malformed JSON from the model) is a triage verdict
# ("none"), not a runner crash — downstream shape-check handles the miss
python3 - "$OUT/harness.json" "$OUT/triage.json" <<'PY' || true
import json, re, sys
events = []
with open(sys.argv[1]) as f:
    for line in f:
        line = line.strip()
        if not line: continue
        try: events.append(json.loads(line))
        except json.JSONDecodeError: pass
text = ""
for e in events:
    m = e.get("message") or {}
    if m.get("role") == "assistant":
        for part in m.get("content") or []:
            if isinstance(part, dict) and part.get("type") == "text":
                text += part.get("text") or ""
blocks = re.findall(r"```json\s*(.*?)```", text, re.S)
raw = blocks[-1] if blocks else None
if raw is None:  # fall back: last balanced {...} in the text
    starts = [i for i, c in enumerate(text) if c == "{"]
    for s in reversed(starts):
        depth = 0
        for i in range(s, len(text)):
            if text[i] == "{": depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    raw = text[s:i+1]; break
        if raw:
            try: json.loads(raw); break
            except json.JSONDecodeError: raw = None
if raw is None:
    print("EXTRACT: no JSON found"); sys.exit(3)
try:
    verdict = json.loads(raw)
except json.JSONDecodeError as e:
    print(f"EXTRACT: invalid JSON ({e})"); sys.exit(3)
with open(sys.argv[2], "w") as f:
    json.dump(verdict, f, indent=2)
print("EXTRACT: ok")
PY

SHAPE="PASS"; NOTES=""
note(){ SHAPE="FAIL"; NOTES="$NOTES$1; "; }
if [ ! -f "$OUT/triage.json" ]; then
  note "no parseable JSON verdict"
  VERDICT="none"
else
  VERDICT=$(jq -r '.verdict // "missing"' "$OUT/triage.json")
  LEVEL=$(jq -r '.level // "missing"' "$OUT/triage.json")
  case "$VERDICT" in actionable|needs-info|reject) ;; *) note "bad verdict '$VERDICT'";; esac
  if [ "$VERDICT" = "actionable" ]; then
    [ "$(jq -r '.problem.acceptance | length' "$OUT/triage.json" 2>/dev/null || echo 0)" -gt 0 ] || note "empty acceptance"
    [ -n "$(jq -r '.problem.symptom // ""' "$OUT/triage.json")" ] || note "empty symptom"
    [ -n "$(jq -r '.problem.expected // ""' "$OUT/triage.json")" ] || note "empty expected"
    if [ "$KB_ROUND" -eq 0 ]; then
      [ "$LEVEL" = "L1" ] || note "first pass must be L1 (got $LEVEL)"
      [ "$(jq -r '.problem.pin.file // ""' "$OUT/triage.json")" = "" ] || note "pin set on first pass"
      # de-trap heuristic: L1 prose naming concrete source paths/symbols = smuggled
      # localization (camelCase symbols with or without parens, src/ paths)
      SMUGGLE=$(jq -r '[.problem.symptom, .problem.expected, (.problem.acceptance|join(" "))] | join(" ")' "$OUT/triage.json" \
        | grep -oE 'src/[A-Za-z0-9_./-]+|\b[a-z][a-zA-Z0-9]*[A-Z][a-zA-Z0-9]*\(?\)?' | sort -u | paste -sd, - || true)
      [ -n "$SMUGGLE" ] && note "localization smuggled: $SMUGGLE"
    else
      # kick-back: an L2 pin is sanctioned; if the failed attempt was off-scope
      # (topology gap) the pin is REQUIRED
      if [ "$LEVEL" = "L2-pinned" ]; then
        [ -n "$(jq -r '.problem.pin.file // ""' "$OUT/triage.json")" ] || note "L2-pinned without pin.file"
      elif [ "$(cut -f8 "$KB_EVIDENCE/result.tsv" 2>/dev/null)" = "no" ]; then
        note "scope=no kick-back must pin L2 (got $LEVEL)"
      fi
    fi
  fi
fi
[ "$TOUCHED" -gt 0 ] && note "edited worktree ($TOUCHED files)"

# render an actionable verdict into a worker-ready manifest (bugs/triaged/)
TRIAGED=""
if [ "$VERDICT" = "actionable" ] && [ -f "$OUT/triage.json" ]; then
  mkdir -p "$HERE/bugs/triaged"
  TRIAGED="bugs/triaged/${ID}-triaged${SUFFIX}.json"
  TDESC=$(jq -r '.problem | .symptom + "\n\nExpected: " + .expected
    + "\n\nAcceptance criteria:\n" + (.acceptance | map("- " + .) | join("\n"))
    + (if (.domain_facts | length) > 0 then "\n\nDomain facts:\n" + (.domain_facts | map("- " + .) | join("\n")) else "" end)
    + (if (.pin.file // "") != "" then "\n\nTarget: " + .pin.file + (if (.pin.function // "") != "" then " — " + .pin.function else "" end)
       + (if (.pin.decoy // "") != "" then "\nDo NOT change " + .pin.decoy + " — it is not the owner of this symptom." else "" end) else "" end)' "$OUT/triage.json")
  jq --arg id "${ID}-triaged${SUFFIX}" --arg desc "$TDESC" --arg lvl "$([ "$KB_ROUND" -eq 0 ] && echo L1-triaged || echo L2-triaged-kb$KB_ROUND)" \
     '.id=$id | .description=$desc | .level=$lvl' "$BUG_JSON" > "$HERE/$TRIAGED"
  echo "   triaged manifest → $TRIAGED"
fi

echo "──────────────────────────────"
echo "TRIAGE: verdict=$VERDICT  shape=$SHAPE${NOTES:+  [$NOTES]}  | ${WALL}s \$$COST"
LEDGER="$ROOT/results/triage_runs.tsv"
[ -f "$LEDGER" ] || printf 'run_idx\tmodel\tid\tverdict\tshape\twall\tcost\touttok\tnotes\n' > "$LEDGER"
printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' "${BAKEOFF_RUN_IDX:-1}" "$MODEL" "${ID}${SUFFIX}" "$VERDICT" "$SHAPE" "$WALL" "$COST" "$OUTTOK" "${NOTES:-—}" >> "$LEDGER"
python3 "$HERE/langfuse_push.py" "${ID}-triage${SUFFIX}" "$HARNESS" "$MODEL" "$VERDICT/$SHAPE" "${COST:-0}" "0" "${WALL:-0}" "$OUT/harness.json" 2>&1 | sed 's/^/   /' || true
echo "artifacts → $OUT"
