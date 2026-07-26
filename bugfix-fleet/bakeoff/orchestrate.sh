#!/usr/bin/env bash
# Orchestrator MVP (v1) — the deterministic control loop of RFC-0002, minimum
# shape. One ticket end-to-end: triage → gate → fix → grade → kick-back → fix,
# bounded. No LLM in this file — LLMs are leaf calls inside triage_run.sh
# (triager episode), run.sh (specialist episode), and reporter_answer.sh
# (reporter-oracle, eval-only); this file only routes.
#
#   ticket (L0 manifest)
#     └─ triage ── reject → STOP
#          │       needs-info → reporter-oracle answers (eval-only, ≤REPORTER_MAX)
#          │                    → ticket re-filed with the Q&A → triage again
#          └─ actionable → specialist (rung-1) → grade vs hidden oracle
#               ├─ PASS → SHIPPED
#               └─ FAIL → kick-back: triage re-entry with the attempt as
#                  evidence (§6.2 2×2) → actionable → specialist again
#                  (≤KICKBACK_MAX) · needs-info → reporter loop again → STUCK
#
# In production the reporter is a human and needs-info parks the ticket on
# them; the reporter-oracle exists only because replayed bugs have knowable
# golden intent (bakeoff/reporter/*.md). Growth path unchanged: GitHub-issue
# adapter in, labels/branch/PR out, always-on service around this file.
#
# Usage:  ./orchestrate.sh bugs/orrery-mission-arc-L0.json [pi]
set -euo pipefail

TICKET="$1"; HARNESS="${2:-pi}"
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$HOME/.bugfix-fleet/bakeoff"
# 3 rounds: measured (2026-07-25) — the advisor-pin -> fail-at-pin ->
# acceptance-gap -> reporter transition needs the third round to complete
KICKBACK_MAX="${KICKBACK_MAX:-3}"
REPORTER_MAX="${REPORTER_MAX:-2}"
ID=$(jq -r .id "$TICKET")

FLOW="$ROOT/results/flow.tsv"
[ -f "$FLOW" ] || printf 'ticket\tstate\tdetail\ttag\n' > "$FLOW"
# ORC_TAG labels a whole chain run (e.g. v3-k1) so k-run sweeps segment cleanly
flow(){
  echo "FLOW: $1${2:+  ($2)}"
  printf '%s\t%s\t%s\t%s\n' "$ID" "$1" "${2:-}" "${ORC_TAG:-}" >> "$FLOW"
  # chain-state metric (dashboard fuel; terminal states drive the ship-rate panel)
  local VMU="${BAKEOFF_VM_URL:-http://homelab:8428}"
  [ -n "$VMU" ] && curl -s -m 5 -X POST "$VMU/api/v1/import/prometheus" --data-binary \
    "bugfix_fleet_flow{ticket=\"$ID\",state=\"$1\",tag=\"${ORC_TAG:-}\",service=\"bugfix-fleet\",environment=\"operations\"} 1" \
    >/dev/null 2>&1 || true
}

# the intent gate is enforced deterministically: an actionable verdict whose
# acceptance criteria are uncited (shape note from triage_run.sh) is an
# invention by construction — downgrade to needs-info, never dispatch it
triage_verdict(){
  V=$(jq -r '.verdict' "$1/triage.json" 2>/dev/null || echo none)
  if [ "$V" = "actionable" ] && grep -q 'uncited acceptance' "$1/shape.txt" 2>/dev/null; then V=needs-info; fi
  echo "$V"
}
worker_verdict(){ cut -f3 "$1/result.tsv"; }

# ask the reporter-oracle about a needs-info verdict; on success re-files the
# ticket (current description + Q&A transcript) into $TICKET and returns 0.
# Returns 1 (after logging why) when the loop must end as needs-info instead.
QA=0
PINS=""  # every advisor pin issued this run — survives reporter-QA restarts
         # (measured 2026-07-26 accfix-k1: resetting per inner loop lost the
         # pin across the QA round and the advisor re-invented a location)
ask_reporter(){ # $1 = the triage.json carrying .missing
  QA=$((QA + 1))
  if [ "$QA" -gt "$REPORTER_MAX" ]; then flow "needs-info" "reporter rounds exhausted"; return 1; fi
  if ! jq -e '.missing | length > 0' "$1" >/dev/null 2>&1; then
    flow "needs-info" "no questions to relay (downgraded verdict)"; return 1
  fi
  flow "asking-reporter" "round=$QA"
  RE_OUT="$ROOT/results/${ID}-reporter-q$QA/$HARNESS"
  if ! "$HERE/reporter_answer.sh" "$TICKET" "$1" "$RE_OUT"; then
    flow "needs-info" "no reporter available (facts missing or answer failed)"; return 1
  fi
  QA_TEXT=$(jq -r '.answers | map("Q: " + .question + "\nA: " + .answer) | join("\n\n")' "$RE_OUT/answers.json")
  NEWTICKET="$HERE/bugs/triaged/${ID}-qa$QA.json"
  jq --arg id "${ID}-qa$QA" --arg qa "$QA_TEXT" \
     '.id=$id | .description=(.description + "\n\n## Reporter answers (follow-up)\n\n" + $qa)' \
     "$TICKET" > "$NEWTICKET"
  TICKET="$NEWTICKET"
}

while :; do # ── outer: one triage pass over the current (possibly QA-augmented) ticket
  flow "triaging" "qa-rounds=$QA"
  "$HERE/triage_run.sh" "$TICKET" "$HARNESS" || { flow "stuck" "triage episode crashed (exit $?)"; exit 1; }
  TOUT="$ROOT/results/$(jq -r .id "$TICKET")-triage/$HARNESS"
  V=$(triage_verdict "$TOUT")
  case "$V" in
    reject)     flow "rejected" "$(jq -r '.reject_reason' "$TOUT/triage.json")"; exit 0;;
    needs-info) ask_reporter "$TOUT/triage.json" && continue || exit 0;;
    actionable) ;;
    *)          flow "stuck" "triage produced no usable verdict ($V)"; exit 1;;
  esac

  # ── inner: specialist attempts + kick-back loop on this triaged problem ──
  TID=$(jq -r .id "$TICKET")        # differs from $ID after reporter QA rounds
  ROUND=0
  MANIFEST="bugs/triaged/${TID}-triaged.json"
  while :; do
    flow "fixing" "round=$ROUND manifest=$MANIFEST"
    BAKEOFF_RUN_IDX="orc-r$ROUND" "$HERE/run.sh" "$HERE/$MANIFEST" "$HARNESS" \
      || { flow "stuck" "specialist episode crashed (exit $?)"; exit 1; }
    WOUT="$ROOT/results/$(jq -r .id "$HERE/$MANIFEST")/$HARNESS"
    WV=$(worker_verdict "$WOUT")
    # dead-call guard: a ~zero-token 1-turn episode is a provider/billing
    # failure (measured 2026-07-24: credit exhaustion = silent empty
    # completions), never a model verdict — do not grade or kick back on it
    WTURNS=$(cut -f6 "$WOUT/result.tsv"); WTOK=$(cut -f7 "$WOUT/result.tsv")
    if [ "${WTURNS:-0}" -le 1 ] && [ "${WTOK:-0}" -lt 10 ]; then
      flow "stuck" "provider dead-call (turns=$WTURNS outtok=$WTOK) — check credits/provider"
      exit 1
    fi
    if [ "$WV" = "PASS" ]; then flow "shipped" "round=$ROUND"; exit 0; fi

    ROUND=$((ROUND + 1))
    if [ "$ROUND" -gt "$KICKBACK_MAX" ]; then
      flow "stuck" "kick-back budget exhausted ($KICKBACK_MAX) — operator"
      exit 1
    fi
    flow "kick-back" "round=$ROUND evidence=$WOUT"
    # acceptance-transition (measured 2026-07-26, advfull k=3 all stuck): a fix
    # AT the advisor's pin that still fails is an acceptance gap by definition.
    # Re-consulting the advisor only makes it invent a new location (all 3
    # chains pivoted to the call site). Route to the reporter deterministically.
    ACC_GAP=0; ACC_PIN=""
    while IFS= read -r P; do
      [ -n "$P" ] || continue
      if grep -qxF "$P" "$WOUT/touched.txt" 2>/dev/null; then
        ACC_GAP=1; ACC_PIN="$P"; break
      fi
    done <<PINSEOF
$PINS
PINSEOF
    if [ "$ACC_GAP" = "1" ]; then
      flow "acceptance-gap" "fixed at pin $ACC_PIN, still failing — reporter"
    fi
    # advisor consultation (§4.2): premium reasoning only at the stuck point.
    # Best-effort — a failed advisor episode never blocks the kick-back.
    if [ "${ADVISOR:-1}" = "1" ] && [ "$ACC_GAP" = "0" ]; then
      flow "advising" "model=${ADVISOR_MODEL:-z-ai/glm-5.2}"
      "$HERE/advisor_run.sh" "$TICKET" "$WOUT" || flow "advising" "no usable advisor output"
      NEWPIN=$(jq -r '.file // ""' "$WOUT/advisor.json" 2>/dev/null || echo "")
      [ -z "$NEWPIN" ] || PINS="$PINS
$NEWPIN"
    fi
    if [ "$ROUND" -gt 1 ]; then KB_SUFF="-kb$((ROUND-1))"; else KB_SUFF=""; fi
    PRIOR="$ROOT/results/${TID}-triage${KB_SUFF}/$HARNESS/triage.json"
    ACCEPTANCE_GAP=$ACC_GAP "$HERE/triage_run.sh" "$TICKET" "$HARNESS" "$WOUT" "$PRIOR" \
      || { flow "stuck" "kick-back triage episode crashed (exit $?)"; exit 1; }
    KOUT="$ROOT/results/${TID}-triage-kb$ROUND/$HARNESS"
    KV=$(triage_verdict "$KOUT")
    # mechanical enforcement — acceptance mode may not re-pin (prompt is a hope)
    if [ "$ACC_GAP" = "1" ] && [ "$KV" = "actionable" ]; then
      flow "downgrade" "acceptance-gap triage returned actionable — forcing needs-info"
      KV=needs-info
    fi
    # a downgraded/question-less needs-info gives the reporter nothing to
    # answer (measured accfix-k1: chain died as bare needs-info) — synthesize
    # the acceptance question from the pin + failure so ask_reporter can relay
    if [ "$ACC_GAP" = "1" ] && [ "$KV" = "needs-info" ] \
       && ! jq -e '.missing | length > 0' "$KOUT/triage.json" >/dev/null 2>&1; then
      PINQ="The fix modified $ACC_PIN (the advisor-confirmed owner) and the hidden acceptance still fails ($WV). Localization is settled — what is the exact expected behavior at that location: formulas, units, reference values, and edge-case handling?"
      jq --arg q "$PINQ" '.missing = [$q]' "$KOUT/triage.json" > "$KOUT/triage.acc.json" \
        && mv "$KOUT/triage.acc.json" "$KOUT/triage.json"
    fi
    case "$KV" in
      needs-info) ask_reporter "$KOUT/triage.json" && continue 2 || exit 0;;
      reject)     flow "rejected" "after round $ROUND"; exit 0;;
      actionable) MANIFEST="bugs/triaged/${TID}-triaged-kb$ROUND.json";;
      *)          flow "stuck" "kick-back triage produced no usable verdict"; exit 1;;
    esac
  done
done
