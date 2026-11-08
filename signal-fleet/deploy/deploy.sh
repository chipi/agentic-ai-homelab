#!/usr/bin/env bash
# signal-fleet/deploy/deploy.sh — kept as a wrapper so old habits and scripts still work.
#
# The mini's deploy is now repo-wide: deploy/mini-deploy.sh pulls main, runs every registered gate
# (the triage fleet's gates are one hook, deploy/hooks/gate.d/10-signal-fleet.sh ->
# signal-fleet/deploy/gates.sh), and rolls back if any is red. See deploy/README.md. Split out
# 2026-11-08 so the fleet can move to flotilla without taking the homelab's deploy with it.
#
# Run ON the mini:   bash signal-fleet/deploy/deploy.sh   (same as bash deploy/mini-deploy.sh)
set -euo pipefail
CHECKOUT="${SF_CHECKOUT:-$HOME/agentic-ai-homelab}"
HOMELAB_CHECKOUT="$CHECKOUT" exec bash "$CHECKOUT/deploy/mini-deploy.sh" "$@"
