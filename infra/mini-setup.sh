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
REPO="$(cd "$INFRA/.." && pwd)"
# LaunchDAEMONS, not LaunchAgents. An agent needs a user login session and this
# box boots to the login window: on 2026-09-08 the mini lost power and every
# agent-hosted collector stayed dead for 30h while the containers were back in
# 81s. See infra/tailscale/README.md.
LD="/Library/LaunchDaemons"
if ! sudo -n true 2>/dev/null; then
  echo "!! installs into $LD and needs passwordless sudo; re-run where available"
  exit 1
fi

echo "== 1. Homebrew packages (Brewfile: colima, docker, node_exporter, sops, age) =="
if command -v brew >/dev/null 2>&1; then
  # --no-upgrade: install only what's MISSING; never upgrade an installed formula
  # on a routine re-run (a colima/docker upgrade would bounce every container).
  brew bundle install --no-upgrade --file "$INFRA/Brewfile" && echo "   brew bundle satisfied"
  # NOT 'brew services start' -- that installs a LaunchAgent, which dies with the
  # login window. node_exporter is installed as a LaunchDaemon in step 3.
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

echo "== 3. launchd host services as DAEMONS (run in-place from this repo) =="
# Every host service the mini must have with nobody logged in. Sources stay beside
# their stack so `git pull` ships updates; only the plist is copied into $LD.
for rel in \
  infra/mini-metrics/com.homelab.mini-metrics.plist \
  infra/mini-metrics/com.homelab.forward-watchdog.plist \
  infra/mini-metrics/com.homelab.openrouter-spend.plist \
  infra/dgx-scrape/com.homelab.dgx-scrape.plist \
  infra/ci-ops-poller/com.homelab.ci-ops-poller.plist \
  infra/docker-maintenance/com.homelab.docker-prune.plist \
  infra/caffeinate/com.homelab.caffeinate.plist \
  infra/node-exporter/homebrew.mxcl.node_exporter.plist \
  infra/tailscale/com.homelab.tailscale-up.plist \
  bugfix-fleet/deploy/com.homelab.bugfix-metrics.plist \
  fleetd/deploy/com.homelab.fleetd.plist ; do
  src="$REPO/$rel"
  b=$(basename "$rel")
  label=${b%.plist}
  [ -f "$src" ] || { echo "   skip $b (missing)"; continue; }
  d=$(dirname "$src")
  for sc in push.sh forward-watchdog.sh openrouter-spend.sh tailscale-up.sh run-metrics.sh; do
    [ -f "$d/$sc" ] && chmod +x "$d/$sc" 2>/dev/null || true
  done
  sudo cp "$src" "$LD/$b"
  sudo chown root:wheel "$LD/$b"
  sudo chmod 644 "$LD/$b"
  sudo launchctl bootout "system/$label" 2>/dev/null || true
  if sudo launchctl bootstrap system "$LD/$b" 2>/dev/null; then
    echo "   bootstrapped $label"
  else
    echo "   !! failed to bootstrap $label"
  fi
done
# A leftover LaunchAgent double-runs the same label the moment anyone logs in.
for stale in "$HOME"/Library/LaunchAgents/com.homelab.*.plist; do
  [ -e "$stale" ] || continue
  echo "   !! legacy LaunchAgent present: $stale (remove -- superseded by $LD)"
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
