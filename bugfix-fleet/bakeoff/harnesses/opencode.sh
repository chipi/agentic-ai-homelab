#!/usr/bin/env bash
# opencode harness adapter — headless single fix attempt inside $WT.
# Same fleet/model story as the other harnesses; Phase 1 = single agent.
set -euo pipefail
WT="$1"; DESC="$2"
MODEL="${OPENCODE_MODEL:-openrouter/deepseek/deepseek-v4-pro}"
read -r -d '' PROMPT <<EOF || true
You are fixing a bug in the repository at the current working directory.

Bug report:
$DESC

Diagnose the cause in the source and fix it. Add or update a regression test if
appropriate. Keep the change tight and correct; do not touch unrelated code.
When done, stop — do not commit, push, or open a PR.
EOF
cd "$WT"
export NODE_OPTIONS="--max-old-space-size=4096"
# </dev/null: headless run must not inherit caller stdin (see pi.sh 2026-07-23)
opencode run --pure -m "$MODEL" --format json "$PROMPT" < /dev/null
