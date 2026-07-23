#!/usr/bin/env bash
# Bake-off eval runner (v1) — one bug × one harness, Scenario A (isolated).
# SWE-bench-style loop:
#   1. reset worktree to the bug's base commit (<fix>^)
#   2. apply the hidden oracle test, run it → record FAIL_TO_PASS + PASS_TO_PASS
#   3. hide the oracle (revert), hand the harness ONLY the bug description
#   4. re-apply the oracle FRESH (harness edits to it are discarded), run → grade
# Grade PASS iff every FAIL_TO_PASS now passes AND every PASS_TO_PASS still passes.
#
# Usage:  ./run.sh bugs/orrery-335-mission-event-merge.json claude
set -euo pipefail
export NODE_OPTIONS="--max-old-space-size=4096"   # drop harness's broken --require preload

BUG_JSON="$1"; HARNESS="$2"
ROOT="$HOME/.bugfix-fleet/bakeoff"
SRC="$ROOT/orrery-src"; WT="$ROOT/orrery"
HERE="$(cd "$(dirname "$0")" && pwd)"

jqr(){ jq -r "$1" "$BUG_JSON"; }
ID=$(jqr .id); FIX=$(jqr .fix_commit); BASE="${FIX}^"
ORACLE=$(jqr .oracle_test_file); DESC=$(jqr .description)
AUTHORED=$(jqr '.authored_oracle // empty')   # set when the fix shipped no test
OUT="$ROOT/results/$ID/$HARNESS"; mkdir -p "$OUT"

# model label (mirror the adapter defaults) + Langfuse creds (outside the repo)
case "$HARNESS" in
  claude)   MODEL="${CLAUDE_MODEL:-claude-sonnet-4-6}";;
  opencode) MODEL="${OPENCODE_MODEL:-openrouter/deepseek/deepseek-v4-pro}";;
  pi)       MODEL="${PI_MODEL:-deepseek/deepseek-v4-pro}";;
  *)        MODEL="unknown";;
esac
[ -f "$ROOT/langfuse.env" ] && { set -a; . "$ROOT/langfuse.env"; set +a; }

vitest_json(){ # $1 = output json path ; run the oracle file only
  ( cd "$WT" && npx vitest run "$ORACLE" --reporter=json --outputFile="$1" >/dev/null 2>&1 ) || true
}
titles(){ jq -r ".testResults[].assertionResults[] | select(.status==\"$2\") | .title" "$1" 2>/dev/null | sort; }
# Opt1: the fix shipped the test → apply that test-file hunk. Opt2 (authored):
# the fix shipped no test → drop our hold-out oracle file at ORACLE's path.
apply_oracle(){
  if [ -n "$AUTHORED" ]; then
    mkdir -p "$WT/$(dirname "$ORACLE")"; cp "$HERE/$AUTHORED" "$WT/$ORACLE"
  else
    git -C "$SRC" diff "$BASE" "$FIX" -- "$ORACLE" | git -C "$WT" apply
  fi
}

echo "══ [$ID → $HARNESS] reset to base $BASE ══"
git -C "$WT" reset --hard "$BASE" >/dev/null
git -C "$WT" clean -fd >/dev/null                       # keeps gitignored node_modules
( cd "$WT" && npm run i18n:compile >/dev/null 2>&1 ) || true

# Optional doc substrate (manifest .context_files): part of the PROBLEM STATE,
# committed onto the worktree so it never shows in the captured harness patch.
if jq -e '.context_files' "$BUG_JSON" >/dev/null 2>&1; then
  echo "══ inject context substrate ══"
  jq -r '.context_files[] | .repo_path + "\t" + .src' "$BUG_JSON" | while IFS=$'\t' read -r RP SP; do
    mkdir -p "$WT/$(dirname "$RP")"; cp "$HERE/$SP" "$WT/$RP"; git -C "$WT" add "$RP"
    echo "   + $RP"
  done
  git -C "$WT" -c user.email=bakeoff@local -c user.name=bakeoff commit -q -m "docs: module notes"
fi

echo "══ establish oracle at base ══"
apply_oracle
vitest_json "$OUT/base.json"
# Bugs span many eras; node_modules from a prior base may not fit. If the oracle
# run produced no test results, the deps are stale → install and retry.
if ! jq -e '.testResults' "$OUT/base.json" >/dev/null 2>&1; then
  echo "   deps mismatch for this era → npm install…"
  ( cd "$WT" && PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1 npm install >/dev/null 2>&1; npm run i18n:compile >/dev/null 2>&1 )
  vitest_json "$OUT/base.json"
fi
titles "$OUT/base.json" failed  > "$OUT/fail_to_pass.txt"
titles "$OUT/base.json" passed  > "$OUT/pass_to_pass.txt"
FTP=$(wc -l < "$OUT/fail_to_pass.txt" | tr -d ' ')
PTP=$(wc -l < "$OUT/pass_to_pass.txt" | tr -d ' ')
echo "   FAIL_TO_PASS=$FTP  PASS_TO_PASS=$PTP"
[ "$FTP" -gt 0 ] || { echo "ABORT: bug does not reproduce at base (0 failing oracle tests)"; exit 2; }

# Hide the oracle from the harness: Opt1 tests revert to base; an authored
# (untracked) oracle must be removed outright — git checkout won't touch it.
hide_oracle(){ [ -n "$AUTHORED" ] && rm -f "$WT/$ORACLE" || git -C "$WT" checkout -- "$ORACLE"; }
echo "══ hide oracle, run harness ══"
hide_oracle
SECONDS=0
# stdout = the adapter's JSON result (usage/cost); stderr = its log.
# Wall-clock budget (BAKEOFF_MAX_WALL, default 1200s = ~2x the passing
# envelope measured 2026-07-23): a runaway attempt is cut and marked, since
# FAILs cost 2-4.5x their passing siblings (§6.3) — the cut itself is a
# spec-suspect signal. Kills the adapter + its direct child (pi/opencode/
# claude); short-lived tool-call grandchildren may briefly orphan.
MAX_WALL="${BAKEOFF_MAX_WALL:-1200}"
BUDGET=0
"$HERE/harnesses/$HARNESS.sh" "$WT" "$DESC" > "$OUT/harness.json" 2> "$OUT/harness.err" &
HPID=$!
while kill -0 "$HPID" 2>/dev/null; do
  if [ "$SECONDS" -ge "$MAX_WALL" ]; then
    BUDGET=1
    echo "   budget: wall ${MAX_WALL}s exceeded — cutting the attempt"
    pkill -P "$HPID" 2>/dev/null || true; kill "$HPID" 2>/dev/null || true
    sleep 2; pkill -9 -P "$HPID" 2>/dev/null || true; kill -9 "$HPID" 2>/dev/null || true
    break
  fi
  sleep 5
done
wait "$HPID" 2>/dev/null || true
# Per-harness output shapes, unified: claude = one result object; opencode =
# step_finish events (.part.cost/.part.tokens); pi = message events
# (.message.usage.cost.total/.output). Slurp (-s) → one value each, never a flood.
# COST + output tokens are incremental → sum; input tokens are cumulative → max.
WALL=$SECONDS
COST=$(jq -rs 'map(.total_cost_usd // .cost_usd // .part.cost // .message.usage.cost.total // empty) | add // 0' "$OUT/harness.json" 2>/dev/null || echo 0)
OUTTOK=$(jq -rs 'map(.usage.output_tokens // .part.tokens.output // .message.usage.output // empty) | add // 0' "$OUT/harness.json" 2>/dev/null || echo 0)
INTOK=$(jq -rs 'map(.usage.input_tokens // .part.tokens.input // .message.usage.input // empty) | max // 0' "$OUT/harness.json" 2>/dev/null || echo 0)
TURNS=$(jq -rs 'reduce .[] as $e (0; if ($e.num_turns) then $e.num_turns elif ($e.type=="step_finish" or $e.type=="turn_start") then .+1 else . end)' "$OUT/harness.json" 2>/dev/null || echo 0)
echo "   harness: ${WALL}s  \$$COST  ${TURNS} turns  (in=$INTOK out=$OUTTOK)"

echo "══ capture harness patch (code only) ══"
hide_oracle 2>/dev/null || true                          # protect oracle: discard harness edits to it
git -C "$WT" add -A >/dev/null && git -C "$WT" diff --cached > "$OUT/harness.patch"
git -C "$WT" reset >/dev/null

# Scope signal (kick-back payload, §6.2): non-test files touched vs the
# manifest's code_files. A FAIL whose patch is entirely off-scope is the
# wrong-layer signature — machine-detectable without reading the patch.
TOUCHED=$(grep -E '^\+\+\+ b/' "$OUT/harness.patch" 2>/dev/null | sed 's|^+++ b/||' | grep -vE '\.(test|spec)\.' || true)
SCOPE_HIT=no
while IFS= read -r cf; do
  { [ -n "$cf" ] && echo "$TOUCHED" | grep -qxF "$cf" && SCOPE_HIT=yes; } || true
done < <(jq -r '.code_files[]?' "$BUG_JSON")
OFF_SCOPE=$(echo "$TOUCHED" | grep -vxF -f <(jq -r '.code_files[]?' "$BUG_JSON") 2>/dev/null | grep -v '^$' | paste -sd, - || true)
echo "   scope: hit=$SCOPE_HIT${OFF_SCOPE:+  off_scope=$OFF_SCOPE}"

echo "══ re-apply hidden oracle, grade ══"
apply_oracle
vitest_json "$OUT/after.json"
AFTER_PASS="$OUT/after_pass.txt"; titles "$OUT/after.json" passed > "$AFTER_PASS"

FTP_FAIL=$(comm -23 "$OUT/fail_to_pass.txt" "$AFTER_PASS" | wc -l | tr -d ' ')  # required-green still failing
PTP_FAIL=$(comm -23 "$OUT/pass_to_pass.txt" "$AFTER_PASS" | wc -l | tr -d ' ')  # regressions

echo "──────────────────────────────"
if [ "$FTP_FAIL" -eq 0 ] && [ "$PTP_FAIL" -eq 0 ]; then
  VERDICT="PASS"
else
  VERDICT="FAIL (ftp_still_failing=$FTP_FAIL, regressions=$PTP_FAIL)"
fi
# a budget cut still grades the partial patch (data is data) but is marked —
# it is a spec/cost verdict, not a clean model grade
if [ "$BUDGET" -eq 1 ]; then VERDICT="BUDGET_EXCEEDED(${MAX_WALL}s) $VERDICT"; fi
echo "VERDICT: $VERDICT   | ${WALL:-?}s  \$${COST:-?}  ${TURNS:-?} turns  scope=$SCOPE_HIT"
# one-line machine-readable result for aggregation (v2: +scope_hit +budget)
printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' "$ID" "$HARNESS" "$VERDICT" "${WALL:-}" "${COST:-}" "${TURNS:-}" "${OUTTOK:-}" "$SCOPE_HIT" "$BUDGET" > "$OUT/result.tsv"
echo "$VERDICT" > "$OUT/verdict.txt"
# push trace + per-call generations + passed score to Langfuse (no-op without creds)
python3 "$HERE/langfuse_push.py" "$ID" "$HARNESS" "$MODEL" "$VERDICT" "${COST:-0}" "${TURNS:-0}" "${WALL:-0}" "$OUT/harness.json" 2>&1 | sed 's/^/   /' || true
echo "artifacts → $OUT"
