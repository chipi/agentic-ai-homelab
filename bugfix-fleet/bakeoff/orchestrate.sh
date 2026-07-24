#!/usr/bin/env bash
# Orchestrator MVP (v1) — the deterministic control loop of RFC-0002, minimum
# shape. One ticket end-to-end: triage → gate → fix → grade → kick-back → fix,
# bounded. No LLM in this file — LLMs are leaf calls inside triage_run.sh
# (triager episode) and run.sh (specialist episode); this file only routes.
#
#   ticket (L0 manifest)
#     └─ triage (first pass, rung-0) ──── needs-info / reject → STOP
#          └─ actionable → specialist (rung-1) → grade vs hidden oracle
#               ├─ PASS → SHIPPED
#               └─ FAIL → kick-back: triage re-entry with the attempt as
#                  evidence (§6.2 2×2) → specialist again … bounded by
#                  KICKBACK_MAX (default 2, per agents/triage.md) → STUCK
#
# Growth path (deliberately not built yet): the ticket source becomes a
# GitHub issue adapter, the result sink becomes labels/branch/PR, and this
# loop moves into an always-on service. The state machine stays this file.
#
# Usage:  ./orchestrate.sh bugs/orrery-mission-arc-L0.json [pi]
set -euo pipefail

TICKET="$1"; HARNESS="${2:-pi}"
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$HOME/.bugfix-fleet/bakeoff"
KICKBACK_MAX="${KICKBACK_MAX:-2}"
ID=$(jq -r .id "$TICKET")

FLOW="$ROOT/results/flow.tsv"
[ -f "$FLOW" ] || printf 'ticket\tstate\tdetail\n' > "$FLOW"
flow(){ echo "FLOW: $1${2:+  ($2)}"; printf '%s\t%s\t%s\n' "$ID" "$1" "${2:-}" >> "$FLOW"; }

# the intent gate is enforced deterministically: an actionable verdict whose
# acceptance criteria are uncited (shape note from triage_run.sh) is an
# invention by construction — downgrade to needs-info, never dispatch it
triage_verdict(){
  V=$(jq -r '.verdict' "$1/triage.json" 2>/dev/null || echo none)
  if [ "$V" = "actionable" ] && grep -q 'uncited acceptance' "$1/shape.txt" 2>/dev/null; then V=needs-info; fi
  echo "$V"
}
worker_verdict(){ cut -f3 "$1/result.tsv"; }

# ── 1 · triage, first pass ──────────────────────────────────────────────────
flow "triaging"
"$HERE/triage_run.sh" "$TICKET" "$HARNESS" || { flow "stuck" "triage episode crashed (exit $?)"; exit 1; }
TOUT="$ROOT/results/${ID}-triage/$HARNESS"
V=$(triage_verdict "$TOUT")
case "$V" in
  needs-info) flow "needs-info" "$(jq -cr '.missing' "$TOUT/triage.json")"; exit 0;;
  reject)     flow "rejected"   "$(jq -r '.reject_reason' "$TOUT/triage.json")"; exit 0;;
  actionable) ;;
  *)          flow "stuck" "triage produced no usable verdict ($V)"; exit 1;;
esac

# ── 2 · specialist attempt on the triaged problem, kick-back loop ───────────
ROUND=0
MANIFEST="bugs/triaged/${ID}-triaged.json"
while :; do
  flow "fixing" "round=$ROUND manifest=$MANIFEST"
  BAKEOFF_RUN_IDX="orc-r$ROUND" "$HERE/run.sh" "$HERE/$MANIFEST" "$HARNESS" \
    || { flow "stuck" "specialist episode crashed (exit $?)"; exit 1; }
  WOUT="$ROOT/results/$(jq -r .id "$HERE/$MANIFEST")/$HARNESS"
  WV=$(worker_verdict "$WOUT")
  if [ "$WV" = "PASS" ]; then flow "shipped" "round=$ROUND"; exit 0; fi

  ROUND=$((ROUND + 1))
  if [ "$ROUND" -gt "$KICKBACK_MAX" ]; then
    flow "stuck" "kick-back budget exhausted ($KICKBACK_MAX) — operator"
    exit 1
  fi
  flow "kick-back" "round=$ROUND evidence=$WOUT"
  if [ "$ROUND" -gt 1 ]; then KB_SUFF="-kb$((ROUND-1))"; else KB_SUFF=""; fi
  PRIOR="$ROOT/results/${ID}-triage${KB_SUFF}/$HARNESS/triage.json"
  "$HERE/triage_run.sh" "$TICKET" "$HARNESS" "$WOUT" "$PRIOR" \
    || { flow "stuck" "kick-back triage episode crashed (exit $?)"; exit 1; }
  KOUT="$ROOT/results/${ID}-triage-kb$ROUND/$HARNESS"
  KV=$(triage_verdict "$KOUT")
  case "$KV" in
    needs-info) flow "needs-info" "after round $ROUND"; exit 0;;
    reject)     flow "rejected"   "after round $ROUND"; exit 0;;
    actionable) MANIFEST="bugs/triaged/${ID}-triaged-kb$ROUND.json";;
    *)          flow "stuck" "kick-back triage produced no usable verdict"; exit 1;;
  esac
done
