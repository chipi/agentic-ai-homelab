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
"$HERE/harnesses/$HARNESS.sh" "$WT" "$DESC" > "$OUT/harness.json" 2> "$OUT/harness.err" || true
WALL=$SECONDS
COST=$(jq -r '.total_cost_usd // .cost_usd // 0' "$OUT/harness.json" 2>/dev/null || echo 0)
INTOK=$(jq -r '.usage.input_tokens // 0' "$OUT/harness.json" 2>/dev/null || echo 0)
OUTTOK=$(jq -r '.usage.output_tokens // 0' "$OUT/harness.json" 2>/dev/null || echo 0)
TURNS=$(jq -r '.num_turns // 0' "$OUT/harness.json" 2>/dev/null || echo 0)
echo "   harness: ${WALL}s  \$$COST  ${TURNS} turns  (in=$INTOK out=$OUTTOK)"

echo "══ capture harness patch (code only) ══"
hide_oracle 2>/dev/null || true                          # protect oracle: discard harness edits to it
git -C "$WT" add -A >/dev/null && git -C "$WT" diff --cached > "$OUT/harness.patch"
git -C "$WT" reset >/dev/null

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
echo "VERDICT: $VERDICT   | ${WALL:-?}s  \$${COST:-?}  ${TURNS:-?} turns"
# one-line machine-readable result for aggregation
printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\n' "$ID" "$HARNESS" "$VERDICT" "${WALL:-}" "${COST:-}" "${TURNS:-}" "${OUTTOK:-}" > "$OUT/result.tsv"
echo "$VERDICT" > "$OUT/verdict.txt"
echo "artifacts → $OUT"
