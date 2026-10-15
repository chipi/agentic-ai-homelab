#!/bin/bash
# Load the homelab Langfuse admin credentials from the mini (never printed), then run a script.
cd "$(dirname "$0")"
# Another instance: export LF_UI and LANGFUSE_INIT_USER_EMAIL/_PASSWORD first and this is skipped.
if [ -z "${LANGFUSE_INIT_USER_EMAIL:-}" ] || [ -z "${LANGFUSE_INIT_USER_PASSWORD:-}" ]; then
  eval "$(ssh -i ~/.ssh/homelab_mini -o IdentitiesOnly=yes homelab 'grep -E "^LANGFUSE_INIT_USER_(EMAIL|PASSWORD)=" ~/agentic-ai-homelab/infra/langfuse/.env' | sed 's/^/export /')"
fi
exec python3 "$@"
