#!/usr/bin/env bash
# The triage fleet's 18 deterministic gates and the filing gate (signal-fleet/deploy/gates.sh).
# Leaves with the fleet when it moves to flotilla.
exec bash "$CHECKOUT/signal-fleet/deploy/gates.sh"
