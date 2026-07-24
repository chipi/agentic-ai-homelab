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
# OpenRouter key only — bugfix-fleet/.env also holds a multiline PEM (GitHub App
# key) that breaks `source`, so extract the one var instead of sourcing the file.
if [ -f "$REPO/bugfix-fleet/.env" ]; then
  OPENROUTER_API_KEY="$(sed -n 's/^OPENROUTER_API_KEY=//p' "$REPO/bugfix-fleet/.env" | head -1)"
fi
[ -f "$REPO/infra/observability/backend/.env" ] && . "$REPO/infra/observability/backend/.env"
[ -f "$HOME/signal-fleet/fleet.env" ] && . "$HOME/signal-fleet/fleet.env"   # GLITCHTIP_TOKEN (not in repo)
set +a
exec python3 "$HERE/orchestrator.py" "$@"
