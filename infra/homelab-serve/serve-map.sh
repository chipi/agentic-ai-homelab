#!/bin/bash
# Reconstruct the homelab tailnet HTTPS entry points (tailscale serve) on the mini.
#
# The serve config lives in tailscaled state (persists across reboots), but is
# NOT otherwise captured as code — this script IS that capture. Run it to
# rebuild the full map on a fresh mini, after a `serve reset`, or to reconcile
# drift. It is idempotent: re-asserting an unchanged mount is a no-op.
#
#   ./serve-map.sh            # apply the map (idempotent)
#   ./serve-map.sh --reset    # clean slate first (brief blip on all mounts)
#   ./serve-map.sh --status   # just print current serve status
#
# Must run ON the mini (needs the App-Store Tailscale app context). The
# /usr/local/bin/tailscale wrapper no-ops over SSH; use the real binary below.
# No sudo needed. Tailnet-only (serve, not funnel).
#
# ACL: each published port must be granted to tag:homelab-host in
# podcast_scraper/tailscale/policy.hujson (currently 443 + 8443 + 8444, applied
# by the Tailscale GitOps action on merge to main — ADR-128, NOT tofu). A mount
# here is unreachable from other devices until the ACL grants its port.
set -euo pipefail

TS="/Applications/Tailscale.app/Contents/MacOS/Tailscale"

# :443 path mounts. tailscale serve --set-path STRIPS the /path prefix before
# proxying, so the backend receives requests at root — fine for APIs and for
# GlitchTip ingest. Web UIs that emit root-absolute assets need extra app config
# (see README): Grafana uses GRAFANA_ROOT_URL. Langfuse can't do a subpath at
# all, so it lives ONLY on :8443 below (no /langfuse path mount).
#   path       backend (loopback:port)
MOUNTS_443="
/grafana    3000
/glitchtip  8090
/litellm    4001
/vm         8428
/vlogs      9428
/vtraces    10428
/home       8888
"
# NOTE: /umami is intentionally NOT here — Umami (Next.js) can't serve under a
# stripped subpath (its /_next assets 404), so its ONLY entry point is the
# dedicated :8444 TLS port below. /litellm stays as the path-tolerant gateway
# API (its UI is likewise on the dedicated :10000 port).

apply() {
  while read -r path port; do
    [ -z "${path:-}" ] && continue
    "$TS" serve --bg --https=443 --set-path="$path" "http://127.0.0.1:$port"
  done <<< "$MOUNTS_443"
  # :8443 — dedicated TLS port for the Langfuse UI (Next.js can't serve under a
  # stripped subpath). Root path, so its absolute assets resolve. Needs
  # AUTH_TRUST_HOST=true on langfuse-web (set in infra/langfuse/) for login.
  "$TS" serve --bg --https=8443 http://127.0.0.1:4000
  # :8444 — dedicated TLS port for the Umami UI, same reason as Langfuse: Umami
  # (Next.js) emits root-absolute /_next assets that 404 under the stripped
  # /umami subpath. Root-mounted here so they resolve. NOTE: the /umami :443 path
  # mount above still serves Umami's (broken) shell — the working UI is ONLY on
  # :8444, which is where the homepage links.
  "$TS" serve --bg --https=8444 http://127.0.0.1:3001
  # :10000 — dedicated TLS port for the LiteLLM admin UI, same Next.js reason:
  # LiteLLM emits root-absolute /litellm-asset-prefix/_next assets that 404 under
  # the stripped /litellm subpath. The /litellm :443 mount above still fronts the
  # gateway API (path-tolerant); the UI works ONLY on :10000 (homepage → :10000/ui/).
  "$TS" serve --bg --https=10000 http://127.0.0.1:4001
  # :8445 — dedicated TLS port for the GlitchTip admin UI. GlitchTip's Angular
  # frontend emits <base href="/"> so its /static assets resolve to root and 404
  # under the stripped /glitchtip subpath. Root-mounted here so they resolve —
  # also requires GLITCHTIP_DOMAIN=https://homelab.<tailnet>:8445 (infra/glitchtip/
  # .env) so Django ALLOWED_HOSTS/CSRF accept this origin. The /glitchtip :443
  # mount above stays as the path-tolerant ingest API.
  "$TS" serve --bg --https=8445 http://127.0.0.1:8090
  echo "applied. current status:"
  "$TS" serve status
}

case "${1:-apply}" in
  --reset)  "$TS" serve reset; apply ;;
  --status) "$TS" serve status ;;
  apply|"") apply ;;
  *) echo "usage: $0 [--reset|--status]" >&2; exit 2 ;;
esac
