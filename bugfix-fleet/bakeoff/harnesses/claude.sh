#!/usr/bin/env bash
# Claude harness adapter — headless single fix attempt inside $WT.
# Gets ONLY the bug description (no oracle test). Edits files in place.
# The runner grades afterward with the hidden oracle.
set -euo pipefail
WT="$1"; DESC="$2"
MODEL="${CLAUDE_MODEL:-claude-opus-4-8}"     # OPEN: reference-tier model

read -r -d '' PROMPT <<EOF || true
You are fixing a bug in the repository at the current working directory.

Bug report:
$DESC

Diagnose the cause in the source and fix it. Add or update a regression test if
appropriate. Keep the change tight and correct; do not touch unrelated code.
When done, stop — do not commit, push, or open a PR.
EOF

cd "$WT"
export NODE_OPTIONS="--max-old-space-size=4096"   # drop harness's broken --require preload
claude -p "$PROMPT" --model "$MODEL" --dangerously-skip-permissions
