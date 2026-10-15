#!/bin/bash
# Load the Langfuse init-admin credentials from the mini (never printed), then run a script.
cd "$(dirname "$0")"
eval "$(ssh -i ~/.ssh/homelab_mini -o IdentitiesOnly=yes homelab 'grep -E "^LANGFUSE_INIT_USER_(EMAIL|PASSWORD)=" ~/agentic-ai-homelab/infra/langfuse/.env' | sed 's/^/export /')"
exec python3 "$@"
