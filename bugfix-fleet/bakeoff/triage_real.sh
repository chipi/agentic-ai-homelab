#!/usr/bin/env bash
# Stage B1 — shadow triage on the REAL backlog (rollout plan, Track B).
# Reads a GitHub issue (read-only; writes NOTHING to GitHub), shapes it into
# a ticket, runs the first-pass triager against CURRENT main, and records the
# L1-or-needs-info verdict for operator review.
#
# Usage:  ./triage_real.sh <issue-number> [repo]     # default repo chipi/orrery
set -euo pipefail
ISSUE="$1"; REPO="${2:-chipi/orrery}"
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$HOME/.bugfix-fleet/bakeoff"

# freshen main so triage recon sees the current code
git -C "$ROOT/orrery-src" fetch -q origin main

J=$(gh issue view "$ISSUE" -R "$REPO" --json number,title,body,labels,url)
TITLE=$(echo "$J" | jq -r .title)
BODY=$(echo "$J" | jq -r '.body // ""')
URL=$(echo "$J" | jq -r .url)
SLUG=$(echo "$REPO" | cut -d/ -f2)
ID="real-${SLUG}-${ISSUE}"

TICKET="$HERE/bugs/real/${ID}.json"
mkdir -p "$HERE/bugs/real"
jq -n --arg id "$ID" --arg desc "$TITLE"$'\n\n'"$BODY" --arg url "$URL" \
  '{id: $id, repo: "orrery", level: "L0-real", source_url: $url,
    description: $desc, oracle_test_file: "", code_files: []}' > "$TICKET"

echo "══ B1 shadow triage: $REPO#$ISSUE → $ID (base = current main) ══"
TRIAGE_BASE=origin/main "$HERE/triage_run.sh" "$TICKET" pi

# operator-review ledger (separate from the eval ledgers)
OUT="$ROOT/results/${ID}-triage/pi"
V=$(jq -r '.verdict // "none"' "$OUT/triage.json" 2>/dev/null || echo none)
RL="$ROOT/results/real_triage.tsv"
[ -f "$RL" ] || printf 'ts\trepo\tissue\tverdict\tsummary\n' > "$RL"
printf '%s\t%s\t%s\t%s\t%s\n' "$(date -u +%FT%TZ)" "$REPO" "$ISSUE" "$V" \
  "$(jq -r '(.problem.symptom // .reason // "") | .[0:160]' "$OUT/triage.json" 2>/dev/null | tr '\t\n' '  ')" >> "$RL"
echo "B1 RESULT: $V  (review ledger: results/real_triage.tsv; full: $OUT/triage.json)"
