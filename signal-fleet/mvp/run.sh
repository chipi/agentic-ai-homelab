#!/usr/bin/env bash
# signal-fleet MVP runner (on the homelab mini). Sources the creds the fleet
# reuses, then runs the orchestrator. No secrets in the repo — they come from the
# already-deployed stack .envs.
#   OPENROUTER_API_KEY   <- bugfix-fleet/.env  (shared with Fleet 1)
#   GRAFANA_ADMIN_USER/PASSWORD <- infra/observability/backend/.env
#   GLITCHTIP_TOKEN      <- export externally (the signal-fleet token) when needed
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="${SF_REPO:-$HOME/agentic-ai-homelab}"
set -a
[ -f "$REPO/bugfix-fleet/.env" ] && . "$REPO/bugfix-fleet/.env"
[ -f "$REPO/infra/observability/backend/.env" ] && . "$REPO/infra/observability/backend/.env"
set +a
exec python3 "$HERE/orchestrator.py" "$@"
