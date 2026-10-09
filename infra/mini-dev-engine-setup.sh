#!/bin/bash
# Mac mini — the on-demand DEV Docker engine (ADR-0009). Separate from production's
# engine (infra/mini-engine-setup.sh) on purpose: it never touches _dockerhost, the
# production VM or /var/run/docker.sock.
#
# Installs: the _dockerdev service account, /usr/local/libexec/devengine-colima (the
# privileged half), /usr/local/bin/devengine (the command), /etc/sudoers.d/devengine,
# the /var/run/docker-dev.sock relay and the idle auto-stop job. It does NOT start the
# VM — the first `devengine start` creates it.
#
# Idempotent. Run as root:  sudo bash infra/mini-dev-engine-setup.sh
# Undo:  devengine stop; launchctl bootout system/com.homelab.docker-dev-relay
#        system/com.homelab.devengine-idle; rm the two plists, /etc/sudoers.d/devengine,
#        /usr/local/bin/devengine, /usr/local/libexec/devengine-colima; then
#        (VM data) sudo -u _dockerdev env HOME=/var/_dockerdev colima delete -f
set -uo pipefail

DEV="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/engine/dev"
DD_USER=_dockerdev
DD_GID=20             # staff
DD_HOME=/var/_dockerdev
LD=/Library/LaunchDaemons

[ "$(id -u)" -eq 0 ] || { echo "!! must run as root: sudo bash $0"; exit 1; }

echo "== 1. ${DD_USER} service account =="
if dscl . -read "/Users/$DD_USER" >/dev/null 2>&1; then
  echo "   exists (uid $(id -u "$DD_USER"))"
else
  DD_UID=""
  for u in $(seq 505 600); do
    dscl . -search /Users UniqueID "$u" 2>/dev/null | grep -q . || { DD_UID=$u; break; }
  done
  [ -n "$DD_UID" ] || { echo "!! no free uid in 505-600"; exit 1; }
  dscl . -create "/Users/$DD_USER"
  dscl . -create "/Users/$DD_USER" UserShell /bin/bash
  dscl . -create "/Users/$DD_USER" RealName "Dev Docker Engine Service Account"
  dscl . -create "/Users/$DD_USER" UniqueID "$DD_UID"
  dscl . -create "/Users/$DD_USER" PrimaryGroupID "$DD_GID"
  dscl . -create "/Users/$DD_USER" NFSHomeDirectory "$DD_HOME"
  dscl . -create "/Users/$DD_USER" IsHidden 1
  echo "   created (uid $DD_UID)"
fi
mkdir -p "$DD_HOME"; chown "$DD_USER:staff" "$DD_HOME"; chmod 755 "$DD_HOME"

echo "== 2. control scripts =="
mkdir -p /usr/local/libexec
install -o root -g wheel -m 755 "$DEV/devengine-colima" /usr/local/libexec/devengine-colima
install -o root -g wheel -m 755 "$DEV/devengine" /usr/local/bin/devengine
echo "   /usr/local/libexec/devengine-colima, /usr/local/bin/devengine (root-owned 755)"

echo "== 3. sudoers rule =="
tmp=$(mktemp)
cp "$DEV/devengine.sudoers" "$tmp"
if visudo -cf "$tmp" >/dev/null; then
  install -o root -g wheel -m 440 "$tmp" /etc/sudoers.d/devengine
  echo "   /etc/sudoers.d/devengine (validated with visudo -c)"
else
  echo "!! sudoers rule failed validation — NOT installed"; rm -f "$tmp"; exit 1
fi
rm -f "$tmp"

echo "== 4. launchd: dev socket relay + idle auto-stop =="
for d in com.homelab.docker-dev-relay com.homelab.devengine-idle; do
  if [ -f "$LD/$d.plist" ] && cmp -s "$DEV/$d.plist" "$LD/$d.plist"; then
    echo "   unchanged $d"
  else
    install -o root -g wheel -m 644 "$DEV/$d.plist" "$LD/$d.plist"
    launchctl bootout "system/$d" 2>/dev/null || true
    launchctl bootstrap system "$LD/$d.plist"
    echo "   installed + loaded $d"
  fi
done

echo "== 5. verify =="
ls -l /var/run/docker-dev.sock 2>&1 | sed 's/^/   /'
sudo -n -u "$DD_USER" /usr/local/libexec/devengine-colima status | sed 's/^/   /'
echo "== done. First use: devengine start   (creates the VM: vz, 4 CPU / 6 GiB / 60 GiB)"
