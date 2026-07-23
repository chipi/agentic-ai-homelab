#!/usr/bin/env bash
# pi harness adapter — headless single fix attempt inside $WT.
set -euo pipefail
WT="$1"; DESC="$2"
MODEL="${PI_MODEL:-deepseek/deepseek-v4-pro}"
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
pi -p --mode json --model "$MODEL" "$PROMPT"
