#!/usr/bin/env bash
# Claude harness adapter — headless single fix attempt inside $WT.
# Gets ONLY the bug description (no oracle test). Edits files in place.
# The runner grades afterward with the hidden oracle.
set -euo pipefail
WT="$1"; DESC="$2"
# Phase 1 (B): single fix-agent smoke test on sonnet. Dispatch + architect
# escalation (full fleet) come later.
MODEL="${CLAUDE_MODEL:-claude-sonnet-4-6}"

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
# --output-format json → the agent still edits files via tools, and the final
# JSON carries usage/cost/num_turns/duration (parsed by run.sh for scoring).
claude -p "$PROMPT" --model "$MODEL" --dangerously-skip-permissions --output-format json
