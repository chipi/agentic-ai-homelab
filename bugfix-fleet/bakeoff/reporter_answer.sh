#!/usr/bin/env bash
# Reporter-oracle (eval-only) — answers a needs-info question set in the
# reporter's voice, from the per-bug facts file authored off the golden fix.
# NOT part of the production fleet: there the reporter is a human. Guard
# rails: answers ONLY what is asked, ONLY from the facts, never names
# files/functions (the facts files carry no localization to begin with),
# says "I don't know" when the facts are silent.
#
# Usage: ./reporter_answer.sh <bug.json> <triage.json-with-missing> <out-dir>
set -euo pipefail
BUG_JSON="$1"; TRIAGE_JSON="$2"; OUT="$3"; mkdir -p "$OUT"
ROOT="$HOME/.bugfix-fleet/bakeoff"
HERE="$(cd "$(dirname "$0")" && pwd)"
ID=$(jq -r .id "$BUG_JSON")
FAMILY=$(echo "$ID" | sed -E 's/-(L[0-9]+(-[a-z0-9]+)*|qa[0-9]+)$//')
FACTS="$HERE/reporter/$FAMILY.md"
[ -f "$FACTS" ] || { echo "REPORTER: no facts file for $FAMILY"; exit 4; }
MODEL="${REPORTER_MODEL:-deepseek/deepseek-v4-flash}"
[ -f "$ROOT/langfuse.env" ] && { set -a; . "$ROOT/langfuse.env"; set +a; }

QUESTIONS=$(jq -r '.missing[]? | "- " + .' "$TRIAGE_JSON")
[ -n "$QUESTIONS" ] || { echo "REPORTER: no questions in $TRIAGE_JSON"; exit 4; }

read -r -d '' PROMPT <<EOF || true
You are the person who reported a bug, being asked follow-up questions by
the triager. Everything you know is in the notes below — nothing else.

Rules:
- Answer ONLY the questions asked, ONLY from the notes.
- If the notes do not answer a question, reply exactly "I don't know."
- You are a reporter, not a developer: never name source files, functions,
  or code — you don't know them.
- Be concrete and complete where the notes are; do not volunteer topics
  that were not asked about.

## Your notes

$(cat "$FACTS")

## The triager's questions

$QUESTIONS

Reply with ONLY a JSON object in a \`\`\`json fenced block:
{"answers": [{"question": "...", "answer": "..."}]}
EOF

# neutral cwd — the reporter must have no repo access
SECONDS=0
( cd /tmp && pi -p --mode json --model "$MODEL" "$PROMPT" < /dev/null ) \
  > "$OUT/harness.json" 2> "$OUT/harness.err" || true
WALL=$SECONDS
python3 - "$OUT/harness.json" "$OUT/answers.json" <<'PY' || true
import json, re, sys
text = ""
with open(sys.argv[1]) as f:
    for line in f:
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
    print("REPORTER EXTRACT: no JSON"); sys.exit(3)
try:
    obj = json.loads(blocks[-1])
except json.JSONDecodeError as e:
    print(f"REPORTER EXTRACT: invalid ({e})"); sys.exit(3)
with open(sys.argv[2], "w") as f:
    json.dump(obj, f, indent=2)
print("REPORTER EXTRACT: ok")
PY
[ -f "$OUT/answers.json" ] || { echo "REPORTER: extraction failed"; exit 4; }
N=$(jq '.answers | length' "$OUT/answers.json")
echo "REPORTER: answered $N question(s)  | ${WALL}s"
