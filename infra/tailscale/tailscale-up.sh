#!/bin/bash
# Bring the mini's own Tailscale node up at boot, with no user session.
#
# WHY THIS EXISTS. The mini runs the *macsys* Tailscale (the notarised app bundle,
# not the sandboxed App Store one). Its tunnel is started by the GUI app, which
# lives in a user login session — so on a machine that boots to the login window,
# the host never rejoins the tailnet. On 2026-09-08 the mini lost power; the
# LaunchDaemons brought all 29 containers back 81s after boot, but `homelab`
# itself stayed off the tailnet for 30 hours because nobody logged in. SSH and
# anything addressing `homelab` directly (e.g. Umami ingest on :3001) were dead
# the whole time, while the per-service Caddy tailnet nodes looked fine.
#
# The system network extension runs as root independently of any session, and the
# in-bundle CLI can drive it, so a LaunchDaemon can do the job the GUI would.
#
# NOTE: `--accept-routes` is this node's saved preference. `tailscale up` refuses
# to run unless every non-default flag is restated, and `--reset` would silently
# drop that preference. Restate flags here; never "fix" this with --reset.
set -uo pipefail

TS="/Applications/Tailscale.app/Contents/MacOS/Tailscale"
# NOT /usr/local/bin/tailscale — that is a shim that only fakes `tailscale ip`
# and exit 0s everything else, so failures there are invisible.

[ -x "$TS" ] || { echo "$(date -u +%FT%TZ) tailscale binary missing at $TS"; exit 1; }

for attempt in $(seq 1 30); do
    if "$TS" status --json 2>/dev/null | grep -q '"BackendState"[[:space:]]*:[[:space:]]*"Running"'; then
        echo "$(date -u +%FT%TZ) already Running (attempt $attempt)"
        exit 0
    fi
    if "$TS" up --timeout=45s --accept-routes 2>&1; then
        echo "$(date -u +%FT%TZ) tailscale up succeeded (attempt $attempt)"
        exit 0
    fi
    echo "$(date -u +%FT%TZ) attempt $attempt failed; retrying in 10s"
    sleep 10
done

echo "$(date -u +%FT%TZ) gave up after 30 attempts"
exit 1
