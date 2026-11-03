#!/bin/bash
# Run a labelled set N times in each evaluation UI, alternating, one results file per run.
#   ./run-evalset-repeat.sh [N=3] [set=evalsets/h4-h5.json]
# The login comes from ~/assistant-ui-eval-accounts.env (never printed). One line per question, a SCORE per run.
set -uo pipefail
cd "$(dirname "$0")"
N=${1:-3}; SET=${2:-evalsets/h4-h5.json}
export EVAL_USER=$(grep '^ASSISTANT_EVAL_USER=' ~/assistant-ui-eval-accounts.env | cut -d= -f2-)
export EVAL_PW=$(grep '^ASSISTANT_EVAL_PASSWORD=' ~/assistant-ui-eval-accounts.env | cut -d= -f2-)
for run in $(seq 1 "$N"); do
  for ui in librechat openwebui; do
    echo "== run $run $ui $(date -u +%T)"
    timeout 900 node run-evalset.mjs "$ui" "$SET" 2>&1 | cut -c1-220
  done
done
echo "DONE $(date -u +%T)"
