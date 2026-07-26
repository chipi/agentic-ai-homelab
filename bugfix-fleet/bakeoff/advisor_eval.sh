#!/usr/bin/env bash
# Advisor-seat eval — the per-seat auction instrument (frozen-replay pattern).
# Replays the advisor episode against RECORDED kick-back evidence and scores
# the pin against the bug's known oracle target (manifest code_files).
# No chains, no workers: one bounded episode per (fixture × model × k).
#
# Usage: ./advisor_eval.sh [k] [model ...]
#   default k=3, models: flash, v4-pro, glm-5.2, kimi-k2.6
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$HOME/.bugfix-fleet/bakeoff"
K="${1:-3}"; shift 2>/dev/null || true
MODELS=("$@")
[ ${#MODELS[@]} -gt 0 ] || MODELS=(
  "deepseek/deepseek-v4-flash" "deepseek/deepseek-v4-pro"
  "z-ai/glm-5.2" "moonshotai/kimi-k2.6")

# fixtures: <name> <ticket-manifest (has fix_commit for base + code_files truth)> <frozen evidence dir>
FIXDIR="$HERE/advisor-eval/fixtures"
LEDGER="$ROOT/results/advisor_eval.tsv"
[ -f "$LEDGER" ] || printf 'ts\tfixture\tmodel\trun\tpin_file\tfile_ok\tfn_ok\twall\n' > "$LEDGER"

score_one() { # fixture model runidx
  local FX="$1" M="$2" R="$3"
  local TICKET="$FIXDIR/$FX/ticket.json" EV="$FIXDIR/$FX/evidence"
  local BASE EXPECT_FILE EXPECT_FN
  BASE="$(jq -r '.fix_commit + "^"' "$TICKET")"
  EXPECT_FILE="$(jq -r '.code_files[0]' "$TICKET")"
  EXPECT_FN="$(jq -r '.expect_function // ""' "$TICKET")"
  # worktree at the bug's base — the advisor reads real code
  git -C "$ROOT/orrery" reset --hard "$BASE" >/dev/null
  git -C "$ROOT/orrery" clean -fdq
  local TMPEV; TMPEV=$(mktemp -d)
  cp "$EV"/* "$TMPEV/"
  local T0=$SECONDS
  ADVISOR_MODEL="$M" "$HERE/advisor_run.sh" "$TICKET" "$TMPEV" >/dev/null 2>&1 || true
  local WALL=$((SECONDS - T0))
  local PIN FN FOK NOK
  PIN=$(jq -r '.file // ""' "$TMPEV/advisor.json" 2>/dev/null || echo "")
  FN=$(jq -r '.function // ""' "$TMPEV/advisor.json" 2>/dev/null || echo "")
  FOK=$([ "$PIN" = "$EXPECT_FILE" ] && echo 1 || echo 0)
  NOK=$([ -n "$EXPECT_FN" ] && echo "$FN" | grep -qi "$EXPECT_FN" && echo 1 || echo 0)
  printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' "$(date -u +%FT%TZ)" "$FX" "$M" "$R" "$PIN" "$FOK" "$NOK" "$WALL" >> "$LEDGER"
  echo "  $FX × $M #$R → pin=$PIN file_ok=$FOK fn_ok=$NOK (${WALL}s)"
  # keep raw episode output for post-hoc diagnosis (misses AND dead-calls)
  ARC="$HERE/advisor-eval/archive/$FX-$(echo "$M" | tr / _)-$R"
  mkdir -p "$ARC"; cp "$TMPEV"/advisor*.* "$ARC/" 2>/dev/null || true
  rm -rf "$TMPEV"
  # dead-call guard (measured 2026-07-26: OpenRouter org monthly cap → 403 =
  # instant empty completions across ALL models; 12 garbage rows before stop)
  if [ -z "$PIN" ] && [ "$WALL" -le 2 ]; then
    DEAD=$((DEAD + 1))
    if [ "$DEAD" -ge 3 ]; then
      echo "ABORT: $DEAD consecutive instant-empty episodes — provider dead-calls (check credits/caps), not model verdicts"
      exit 2
    fi
  else
    DEAD=0
  fi
}
DEAD=0

for FX in "$FIXDIR"/*/; do
  FX=$(basename "$FX")
  # FIXTURES="mission-arc look-angles" limits the sweep (grid-completion runs)
  if [ -n "${FIXTURES:-}" ]; then
    case " $FIXTURES " in *" $FX "*) ;; *) continue;; esac
  fi
  echo "════ fixture $FX ════"
  for M in "${MODELS[@]}"; do
    for R in $(seq 1 "$K"); do score_one "$FX" "$M" "$R"; done
  done
done

echo "════ SUMMARY (file_ok rate per fixture × model; dead-calls excluded) ════"
awk -F'\t' 'NR>1 && !($5=="" && $8<=2) {k=$2" × "$3; n[k]++; ok[k]+=$6} END {for (x in n) printf "%-55s %d/%d\n", x, ok[x], n[x]}' "$LEDGER" | sort
