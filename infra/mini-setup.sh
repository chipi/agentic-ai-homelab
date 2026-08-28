#!/usr/bin/env bash
# mini-setup.sh — provision the Mac mini's HOST-level homelab bits (idempotent).
#
# The counterpart to infra/observability/bootstrap.sh: bootstrap brings up the
# CONTAINERS (Grafana + Victoria* + GlitchTip + Langfuse + Umami); THIS installs
# the non-container, host-level pieces a fresh-machine rebuild also needs —
# node_exporter, the launchd collectors, the CPU-temp reader, and the Grafana
# alert-provisioning reload. Together they rebuild the mini from the repo.
#
#   git clone <repo> ~/agentic-ai-homelab
#   cd ~/agentic-ai-homelab && ./infra/observability/bootstrap.sh   # containers
#   ./infra/mini-setup.sh                                            # host bits (this)
#
# Idempotent: installs only what's missing, reloads what changed. Everything runs
# IN-PLACE from this checkout (no copy-outs) so `git pull` ships updates.
set -euo pipefail
INFRA="$(cd "$(dirname "$0")" && pwd)"
LA="$HOME/Library/LaunchAgents"
mkdir -p "$LA"

echo "== 1. Homebrew packages (Brewfile: colima, docker, node_exporter, sops, age) =="
if command -v brew >/dev/null 2>&1; then
  # --no-upgrade: install only what's MISSING; never upgrade an installed formula
  # on a routine re-run (a colima/docker upgrade would bounce every container).
  brew bundle install --no-upgrade --file "$INFRA/Brewfile" && echo "   brew bundle satisfied"
  brew services list 2>/dev/null | grep -q '^node_exporter.*started' || brew services start node_exporter
else
  echo "   !! Homebrew missing — install it first (see infra/README.md Prerequisites),"
  echo "      then re-run this script: it runs 'brew bundle --file infra/Brewfile'."
fi

echo "== 2. CPU-temp reader (osx-cpu-temp, GPL — also self-builds in mini-metrics) =="
TBIN="$INFRA/mini-metrics/osx-cpu-temp"
if [ -x "$TBIN" ]; then echo "   present"
elif command -v git >/dev/null 2>&1 && command -v make >/dev/null 2>&1; then
  t=$(mktemp -d); git clone --depth 1 -q https://github.com/lavoiesl/osx-cpu-temp "$t" 2>/dev/null \
    && make -C "$t" >/dev/null 2>&1 && cp "$t/osx-cpu-temp" "$TBIN" && chmod +x "$TBIN" && echo "   built" \
    || echo "   !! build failed (needs Xcode CLT + network)"; rm -rf "$t"
else echo "   !! no git/make (Xcode CLT) — CPU temp will be absent until built"; fi

echo "== 3. launchd collectors (run in-place from this repo) =="
for a in mini-metrics dgx-scrape ci-ops-poller; do
  plist="$INFRA/$a/com.homelab.$a.plist"
  [ -f "$plist" ] || { echo "   skip $a (no plist)"; continue; }
  [ -f "$INFRA/$a/push.sh" ] && chmod +x "$INFRA/$a/push.sh" 2>/dev/null || true
  cp "$plist" "$LA/"
  launchctl unload "$LA/com.homelab.$a.plist" 2>/dev/null || true
  launchctl load -w "$LA/com.homelab.$a.plist" && echo "   loaded com.homelab.$a"
done
# ci-ops-poller needs its .env (GITHUB_TOKEN) staged IN-PLACE — never committed.
[ -f "$INFRA/ci-ops-poller/.env" ] || \
  echo "   !! stage $INFRA/ci-ops-poller/.env (GITHUB_TOKEN) — see ci-ops-poller/.env.example"

echo "== 4. Grafana alert-provisioning reload (alerts don't hot-reload like dashboards) =="
ENVF="$INFRA/observability/backend/.env"
if [ -f "$ENVF" ]; then
  PW=$(grep "^GRAFANA_ADMIN_PASSWORD=" "$ENVF" | cut -d= -f2-)
  if curl -sf -u "admin:$PW" -X POST http://localhost:3000/api/admin/provisioning/alerting/reload >/dev/null 2>&1; then
    echo "   reloaded"; else echo "   (Grafana not up yet — run bootstrap.sh first, or reload later)"; fi
else echo "   (no backend/.env — run bootstrap.sh first)"; fi

echo
echo "== done. homelab launchd agents now loaded:"
launchctl list | grep com.homelab | sed 's/^/   /' || true
echo "Note: node_exporter runs via its own homebrew launchd plist; bugfix-metrics /"
echo "fleetd / caffeinate are managed separately (not this script)."
