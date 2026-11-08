#!/usr/bin/env bash
# The triage fleet's deploy log: install the post-merge hook that logs every pull, so each fleet
# decision can be replayed on the code its cycle ran (signal-fleet/deploy/install_deploy_log.sh).
# Leaves with the fleet when it moves to flotilla.
SF_CHECKOUT="$CHECKOUT" bash "$CHECKOUT/signal-fleet/deploy/install_deploy_log.sh" >/dev/null 2>&1 \
  || { echo "deploy log: install failed (the deploy continues)"; exit 1; }
