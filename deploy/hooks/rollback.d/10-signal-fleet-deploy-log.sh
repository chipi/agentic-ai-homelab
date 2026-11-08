#!/usr/bin/env bash
# Rollbacks (git reset --hard) do not fire the post-merge hook, so the fleet's deploy log records
# them here. Leaves with the fleet when it moves to flotilla.
SF_CHECKOUT="$CHECKOUT" bash "$CHECKOUT/signal-fleet/deploy/log_deploy.sh" rollback "$NOW" "$PREV" deploy.sh
