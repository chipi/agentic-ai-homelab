#!/bin/bash
# Mac mini — LAYER 0: the Docker engine itself.
#
# This is the script that was MISSING. bootstrap.sh brings up the CONTAINERS and
# assumes colima is running; mini-setup.sh installs the host COLLECTORS and
# assumes docker works. Neither creates the thing underneath them both: the
# _dockerhost service account, the colima VM spec, the boot daemon, and the
# shared socket relay. Until 2026-09-03 that layer existed only on the box and in
# prose in docs/wip/mac-mini-headless-server.md — so a from-scratch rebuild got
# as far as "brew installed, Tailscale up" and then stopped dead.
#
# Rebuild order:
#   1. ./infra/mini-engine-setup.sh          <- THIS (engine: account, VM, daemons)
#   2. ./infra/observability/bootstrap.sh    <- containers
#   3. ./infra/mini-setup.sh                 <- host collectors + alerts
#
# Idempotent: creates only what is missing, never clobbers a live config.
# Run as root:  sudo bash infra/mini-engine-setup.sh
set -uo pipefail

INFRA="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENGINE="$INFRA/engine"
DH_USER=_dockerhost
DH_UID=504            # live value on the mini (the WIP doc's "~460" was wrong)
DH_GID=20             # staff
DH_HOME=/var/_dockerhost
COLIMA_DIR="$DH_HOME/.colima/default"
LD=/Library/LaunchDaemons

[ "$(id -u)" -eq 0 ] || { echo "!! must run as root: sudo bash $0"; exit 1; }

echo "== 0. Preflight =="
for b in /usr/local/bin/colima /usr/local/bin/socat /usr/local/bin/docker; do
  if [ -x "$b" ]; then echo "   ok   $b"
  else echo "   !!   MISSING $b — run: brew bundle --file $INFRA/Brewfile"; fi
done

echo "== 1. ${DH_USER} service account =="
if dscl . -read "/Users/$DH_USER" >/dev/null 2>&1; then
  echo "   exists (uid $(id -u "$DH_USER" 2>/dev/null))"
else
  # Don't collide: if DH_UID is taken by someone else, take the next free one.
  if dscl . -search /Users UniqueID "$DH_UID" 2>/dev/null | grep -q .; then
    echo "   uid $DH_UID taken — scanning for a free one in 500-600"
    for u in $(seq 500 600); do
      dscl . -search /Users UniqueID "$u" 2>/dev/null | grep -q . || { DH_UID=$u; break; }
    done
  fi
  echo "   creating $DH_USER (uid $DH_UID, gid $DH_GID, home $DH_HOME)"
  dscl . -create "/Users/$DH_USER"
  dscl . -create "/Users/$DH_USER" UserShell /bin/bash
  dscl . -create "/Users/$DH_USER" RealName "Docker Engine Service Account"
  dscl . -create "/Users/$DH_USER" UniqueID "$DH_UID"
  dscl . -create "/Users/$DH_USER" PrimaryGroupID "$DH_GID"
  dscl . -create "/Users/$DH_USER" NFSHomeDirectory "$DH_HOME"
  # IsHidden keeps it off the login window — this is a daemon identity, not a person.
  dscl . -create "/Users/$DH_USER" IsHidden 1
  echo "   created"
fi

echo "== 2. Home directory =="
if [ -d "$DH_HOME" ]; then echo "   exists $DH_HOME"; else
  mkdir -p "$DH_HOME" && echo "   created $DH_HOME"; fi
chown -R "$DH_UID:$DH_GID" "$DH_HOME" 2>/dev/null || true
chmod 755 "$DH_HOME"

echo "== 3. colima VM spec =="
mkdir -p "$COLIMA_DIR"; chown -R "$DH_UID:$DH_GID" "$DH_HOME/.colima"
if [ -f "$COLIMA_DIR/colima.yaml" ]; then
  # Compare EFFECTIVE settings, not file text: both files carry different
  # comment blocks, so a raw diff would always cry wolf.
  strip() { grep -vE '^[[:space:]]*#|^[[:space:]]*$' "$1"; }
  if diff -q <(strip "$ENGINE/colima.yaml") <(strip "$COLIMA_DIR/colima.yaml") >/dev/null 2>&1; then
    echo "   live config matches the repo spec (comments aside)"
  else
    # NEVER clobber: colima rewrites this file itself, and a live VM's tuning
    # lives here. Report and move on.
    echo "   !! DIFFERS from the repo copy — leaving the live file alone."
    echo "      repo: $ENGINE/colima.yaml"
    echo "      live: $COLIMA_DIR/colima.yaml"
    echo "      effective-setting diff (repo -> live):"
    diff <(strip "$ENGINE/colima.yaml") <(strip "$COLIMA_DIR/colima.yaml") 2>/dev/null \
      | sed 's/^/        /' | head -25
  fi
else
  cp "$ENGINE/colima.yaml" "$COLIMA_DIR/colima.yaml"
  chown "$DH_UID:$DH_GID" "$COLIMA_DIR/colima.yaml"
  echo "   installed (fresh VM will boot with 8 cpu / 20 GB / 100 GB, qemu, sshfs /Users)"
fi

echo "== 4. Boot daemons =="
for d in com.homelab.colima com.homelab.docker-relay; do
  src="$ENGINE/$d.plist"
  [ -f "$src" ] || { echo "   skip $d (missing $src)"; continue; }
  if cmp -s "$src" "$LD/$d.plist"; then
    echo "   unchanged $d"
  else
    cp "$src" "$LD/$d.plist"
    chown root:wheel "$LD/$d.plist"; chmod 644 "$LD/$d.plist"
    launchctl bootout "system/$d" 2>/dev/null || true
    launchctl bootstrap system "$LD/$d.plist" 2>/dev/null \
      || launchctl load -w "$LD/$d.plist" 2>/dev/null || true
    echo "   installed + loaded $d"
  fi
done

echo "== 5. Global DOCKER_HOST (/etc/zshenv) =="
LINE='export DOCKER_HOST=unix:///var/run/docker.sock'
if [ -f /etc/zshenv ] && grep -qF "$LINE" /etc/zshenv; then
  echo "   already set"
else
  echo "$LINE" >> /etc/zshenv
  echo "   appended to /etc/zshenv (every user now finds the shared engine)"
fi

echo "== 6. Verify =="
echo -n "   colima socket: "
for _ in $(seq 1 30); do
  [ -S "$COLIMA_DIR/docker.sock" ] && break; sleep 2
done
[ -S "$COLIMA_DIR/docker.sock" ] && echo "present" || echo "NOT YET (VM may still be booting — check /tmp/colima-boot.log)"
echo -n "   shared socket: "
[ -S /var/run/docker.sock ] && echo "present ($(stat -f '%Sp' /var/run/docker.sock))" || echo "MISSING"
echo -n "   docker reachable: "
if DOCKER_HOST=unix:///var/run/docker.sock /usr/local/bin/docker ps -q >/dev/null 2>&1; then
  echo "yes ($(DOCKER_HOST=unix:///var/run/docker.sock /usr/local/bin/docker ps -q | wc -l | tr -d ' ') containers)"
else
  echo "no — see /tmp/colima-boot.log and /tmp/docker-relay.log"
fi

echo
echo "== done. Next: ./infra/observability/bootstrap.sh, then ./infra/mini-setup.sh"
echo "   NOT covered here (see infra/README.md Prerequisites): Xcode CLT, Homebrew,"
echo "   Tailscale (App Store), the age key, FileVault-off and pmset power settings."
