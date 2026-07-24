#!/usr/bin/env bash
# signal-fleet MVP runner (on the homelab mini). Sources the creds the fleet
# reuses, then runs the orchestrator. No secrets in the repo — they come from the
# already-deployed stack .envs.
#   OPENROUTER_API_KEY   <- bugfix-fleet/.env  (shared with Fleet 1)
#   GRAFANA_ADMIN_USER/PASSWORD <- infra/observability/backend/.env
#   GLITCHTIP_TOKEN      <- export externally (the signal-fleet token) when needed
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
# All fleet creds live in ONE place — the fleet's own secrets file (not the repo,
# not other projects' .envs). Least-privilege set: a scoped GlitchTip token, a
# Grafana Viewer service-account token, the OpenRouter key, and the triage-fleet
# Langfuse keys. VictoriaMetrics/Logs/Traces need no auth on the tailnet.
FLEET_ENV="${SF_FLEET_ENV:-$HOME/signal-fleet/fleet.env}"
set -a
[ -f "$FLEET_ENV" ] && . "$FLEET_ENV"
set +a
exec python3 "$HERE/orchestrator.py" "$@"
