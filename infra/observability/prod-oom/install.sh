#!/usr/bin/env bash
# Install (or remove) the prod OOM classifier as a system LaunchDaemon on the mini, running as the
# operator account every 120 s (like com.homelab.hub-status).
#   install.sh             install or update, run once, show the result
#   install.sh --remove
set -euo pipefail
LABEL=com.homelab.prod-oom-classify
PLIST=/Library/LaunchDaemons/$LABEL.plist
LOG=/tmp/prod-oom-classify.log
DIR="$(cd "$(dirname "$0")" && pwd)"
if [ "${1:-}" = --remove ]; then
  sudo launchctl bootout system/$LABEL 2>/dev/null || true; sudo rm -f "$PLIST"; echo "REMOVED $LABEL"; exit 0
fi
T="$(mktemp)"
cat > "$T" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key><string>$LABEL</string>
    <key>UserName</key><string>$(id -un)</string>
    <key>ProgramArguments</key>
    <array><string>/usr/bin/python3</string><string>$DIR/classify.py</string><string>--push</string></array>
    <key>StartInterval</key><integer>120</integer>
    <key>StandardOutPath</key><string>$LOG</string>
    <key>StandardErrorPath</key><string>$LOG</string>
</dict>
</plist>
EOF
plutil -lint "$T" >/dev/null
sudo launchctl bootout system/$LABEL 2>/dev/null || true
sudo install -m 644 -o root -g wheel "$T" "$PLIST"; rm -f "$T"
sudo launchctl bootstrap system "$PLIST"
sudo launchctl kickstart -k system/$LABEL
sleep 6; echo "installed $LABEL; last log line:"; tail -1 "$LOG"
