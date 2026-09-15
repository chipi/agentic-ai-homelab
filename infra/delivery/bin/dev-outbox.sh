#!/usr/bin/env bash
# dev-outbox.sh — point the homelab delivery worker's `podcast-dev` tenant at whichever
# machine is running the dev API (`make serve-api`, :8000, serves /internal/outbox), and
# restart the channel workers so it takes effect. Mirrors the gpu-mode-swap.sh ergonomics.
#
# Why: the dev outbox moves with where you're coding — your laptop (over the tailnet) or a
# worktree on the mini itself. This flips the worker's PODCAST_DEV_OUTBOX_URL without you
# hand-editing .env each time. The prod `podcast` tenant is never touched.
#
# Modes:
#   dev-outbox laptop [host] [port]  → point at the laptop over the tailnet (default host
#                                      markos-macbook-pro-1.tail6d0ed4.ts.net, port 8000)
#   dev-outbox mini [port]           → point at a dev API on the mini host (host.docker.internal)
#   dev-outbox off                   → unset the override (revert to the tenants.yaml default)
#   dev-outbox status                → show the current target + whether it answers
#
# The dev API must be reachable: on the laptop, `make serve-api` now binds 0.0.0.0 by default
# (tailnet-ready, no flags). The shared INTERNAL_OUTBOX_TOKEN must already match on both sides.
#
# Config (env-overridable):
#   DEV_OUTBOX_DIR       delivery compose dir (default: repo infra/delivery next to this script)
#   DEV_OUTBOX_LAPTOP    default laptop tailnet host
#   DEV_OUTBOX_PORT      default dev API port (8000)
#   DEV_OUTBOX_DOCKER    docker command (default: docker)
#
# Exit: 0 ok · 2 usage · 3 config (compose dir / .env missing)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DIR="${DEV_OUTBOX_DIR:-$(cd "$SCRIPT_DIR/.." && pwd)}"
ENV_FILE="$DIR/.env"
LAPTOP_HOST="${DEV_OUTBOX_LAPTOP:-markos-macbook-pro-1.tail6d0ed4.ts.net}"
PORT="${DEV_OUTBOX_PORT:-8000}"
DOCKER="${DEV_OUTBOX_DOCKER:-docker}"
KEY="PODCAST_DEV_OUTBOX_URL"
# email+push drain podcast-dev; events is cross-tenant and needs no restart for a URL change.
SERVICES=(delivery-email delivery-push)

log()  { printf '[dev-outbox] %s\n' "$*" >&2; }
die()  { printf '[dev-outbox] ✗ %s\n' "$*" >&2; exit "${2:-2}"; }

[[ -d "$DIR" ]]      || die "compose dir missing: $DIR" 3
[[ -f "$ENV_FILE" ]] || die ".env missing: $ENV_FILE (this must run where the worker .env lives)" 3

current_url() { grep -E "^${KEY}=" "$ENV_FILE" 2>/dev/null | tail -1 | cut -d= -f2-; }

set_url() {
  local url="$1"
  # replace-in-place if present, else append; never duplicate the key
  if grep -qE "^${KEY}=" "$ENV_FILE"; then
    # portable in-place edit (BSD + GNU sed): write a temp then move, preserving perms
    local tmp; tmp="$(mktemp)"; grep -vE "^${KEY}=" "$ENV_FILE" > "$tmp"
    printf '%s=%s\n' "$KEY" "$url" >> "$tmp"
    cat "$tmp" > "$ENV_FILE"; rm -f "$tmp"
  else
    printf '%s=%s\n' "$KEY" "$url" >> "$ENV_FILE"
  fi
}

unset_url() {
  local tmp; tmp="$(mktemp)"; grep -vE "^${KEY}=" "$ENV_FILE" > "$tmp" || true
  cat "$tmp" > "$ENV_FILE"; rm -f "$tmp"
}

restart() { ( cd "$DIR" && $DOCKER compose up -d "${SERVICES[@]}" ) >&2; }

probe() {
  local url="$1"
  local code
  code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 "${url}/internal/outbox/pending?channel=email&limit=1" 2>/dev/null || echo 000)"
  # 401 = reachable but token mismatch; 200 = reachable+authed; 503 = up but token unset;
  # 000 = unreachable (dev API not running / not bound to the tailnet)
  echo "$code"
}

show_status() {
  local url; url="$(current_url)"
  if [[ -z "$url" ]]; then
    log "override UNSET — podcast-dev uses the tenants.yaml default (host.docker.internal:${PORT})"
  else
    log "target: $url   (reachability: HTTP $(probe "$url"))"
  fi
}

MODE="${1:-status}"
case "$MODE" in
  laptop)
    host="${2:-$LAPTOP_HOST}"; port="${3:-$PORT}"
    url="http://${host}:${port}"
    set_url "$url"; log "→ laptop: $url"; restart; show_status
    ;;
  mini)
    port="${2:-$PORT}"
    url="http://host.docker.internal:${port}"
    set_url "$url"; log "→ mini host: $url"; restart; show_status
    ;;
  off)
    unset_url; log "→ override removed (tenants.yaml default)"; restart; show_status
    ;;
  status)
    show_status
    ;;
  -h|--help)
    sed -n '2,30p' "$0" | sed 's/^# \{0,1\}//'
    ;;
  *)
    die "usage: $0 [laptop [host] [port] | mini [port] | off | status]" 2
    ;;
esac
