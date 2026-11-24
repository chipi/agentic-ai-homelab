#!/bin/bash
# The X3 — robotics-lab's staging Docker engine (ADR-0013): its own containerd and dockerd as system
# units, data on two new Btrfs subvolumes, a socket only the service user `robotics` can open, and
# one sudoers-allowed deploy script. The system engine (docker.service, containerd.service,
# /var/lib/docker, /var/lib/containerd, /etc/docker) is never touched.
#
# Idempotent. Run as root from the deploy checkout:
#   sudo bash ~/deploy/agentic-ai-homelab/infra/x3/x3-staging-engine-setup.sh
# The first run creates the subvolumes and stops: add the two fstab lines it prints, mount them
# (systemctl daemon-reload; mount /var/lib/docker-staging; mount /srv/robotics-lab), run it again.
#
# Undo: systemctl disable --now docker-staging containerd-staging; remove the two units, /etc/containerd-staging,
#       /etc/docker-staging, /etc/sudoers.d/robotics-staging, /usr/local/libexec/robotics-staging-deploy;
#       systemctl daemon-reload. Staging's data stays on @robotics-staging and its images on @docker-staging
#       until the operator removes the fstab lines and the subvolumes by hand.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; PE="$HERE/staging-engine"
WB="$(cd "$HERE/../.." && pwd)/workstation/storage/wb-storage"
SVC=robotics
DGRP=robotics-data
STG=/srv/robotics-lab
ENG=/var/lib/docker-staging
SOCK=/run/docker-staging.sock
CSOCK=/run/containerd-staging/containerd.sock
UNITS=/etc/systemd/system

[ "$(id -u)" -eq 0 ] || { echo "!! must run as root: sudo bash $0"; exit 1; }
for b in /usr/bin/containerd /usr/bin/dockerd /usr/bin/ctr /usr/bin/btrfs /usr/bin/visudo; do
  [ -x "$b" ] || { echo "!! $b missing"; exit 1; }
done

echo "== 1. subvolumes @docker-staging and @robotics-staging (top-level siblings of @, outside Snapper's root) =="
src=$(findmnt -n -o SOURCE --mountpoint /) ; dev=${src%%\[*}
[ "$(findmnt -n -o FSTYPE --mountpoint /)" = btrfs ] || { echo "!! / is not btrfs"; exit 1; }
top=$(mktemp -d)
mount -o subvolid=5 "$dev" "$top" || { rmdir "$top"; echo "!! could not mount the top level of $dev"; exit 1; }
for sv in @docker-staging @robotics-staging; do
  if [ -d "$top/$sv" ]; then echo "   exists $sv"
  elif btrfs subvolume create "$top/$sv" >/dev/null; then echo "   created $sv"
  else umount "$top"; rmdir "$top"; echo "!! could not create $sv"; exit 1
  fi
done
umount "$top"; rmdir "$top"

echo "== 2. fstab and mounts =="
missing=0
while IFS= read -r line; do
  path=$(cut -f2 <<<"$line"); sv=$(cut -f4 <<<"$line" | sed 's/.*subvol=\///')
  if ! grep -qE "^[[:space:]]*[^#[:space:]].*[[:space:]]$path[[:space:]].*subvol=/?$sv([,[:space:]]|$)" /etc/fstab; then
    echo "   NOT IN /etc/fstab: $path"; missing=1
  elif ! findmnt -n -o SOURCE --mountpoint "$path" | grep -q "\[/$sv\]"; then
    echo "   in fstab, NOT MOUNTED from $sv: $path"; missing=1
  else
    echo "   mounted $path from $sv"
  fi
done < <("$WB" fstab --staging | grep -v '^#')
if [ "$missing" = 1 ]; then
  echo "   -> add these lines to /etc/fstab by hand (this script never edits it), then:"
  echo "      mkdir -p $ENG $STG; systemctl daemon-reload; mount $ENG; mount $STG; and run this script again"
  "$WB" fstab --staging | sed 's/^/      /'
  exit 3
fi

echo "== 3. service user $SVC (system, no login, not in docker or wheel) =="
if id "$SVC" >/dev/null 2>&1; then echo "   exists (uid $(id -u "$SVC"))"
else useradd --system --user-group --home-dir "$STG/home" --no-create-home --shell /usr/bin/nologin "$SVC" && echo "   created (uid $(id -u "$SVC"))"
fi
id -nG "$SVC" | tr ' ' '\n' | grep -qxE 'docker|wheel' && { echo "!! $SVC is in docker or wheel"; exit 1; }
# The host's recorders (runner, navigator, nxt-web) write runs as the operator: a shared group for the
# data folders only (operator, 2026-11-24). Never the operator in the group robotics (root-equivalent).
OP="${SUDO_USER:-marko}"
getent group "$DGRP" >/dev/null || { groupadd --system "$DGRP" && echo "   created group $DGRP"; }
for u in "$SVC" "$OP"; do
  id -nG "$u" | tr ' ' '\n' | grep -qx "$DGRP" || { usermod -aG "$DGRP" "$u" && echo "   added $u to $DGRP"; }
done
id -nG "$OP" | tr ' ' '\n' | grep -qx "$SVC" && { echo "!! $OP is in the group $SVC"; exit 1; }

echo "== 4. folders =="
install -d -o root -g root -m 711 "$ENG" "$ENG/containerd" "$ENG/docker" "$ENG/containerd-opt"
# No compression for new files in staging's content store: btrfs zstd with fs-verity is the suspect in the
# X3's containerd read faults (NEXT_STEPS). Undo: btrfs property set $ENG/containerd compression zstd
btrfs property set "$ENG/containerd" compression none || { echo "!! could not turn off compression on $ENG/containerd"; exit 1; }
install -d -o root -g root -m 755 "$STG"
install -d -o root -g "$SVC" -m 750 /etc/robotics-staging
# robotics owns these, so a symlink here could aim root's chown elsewhere: refuse one.
for d in home home/tmp data data-archive robots state state/observatory state/mission-control state/deploy; do
  [ -L "$STG/$d" ] && { echo "!! $STG/$d is a symlink; not following it"; exit 1; }
  install -d -o "$SVC" -g "$SVC" -m 750 "$STG/$d"
done
# data and data-archive: group $DGRP, setgid, and default ACLs so a file either writer makes stays
# group-writable whatever its umask. Only the folders themselves here; their contents are the cut-over's.
for d in data data-archive; do
  chown "$SVC:$DGRP" "$STG/$d" && chmod 2770 "$STG/$d"
  setfacl -m g::rwx,m::rwx -m d:u::rwx,d:g::rwx,d:m::rwx,d:o::--- "$STG/$d"
done
[ -e /etc/robotics-staging/installation.json ] || echo "   NOTE /etc/robotics-staging/installation.json absent: robotics-lab supplies it (root:$SVC 0640)"
echo "   $ENG (root 711); $STG/{home,robots,state} ($SVC 750); $STG/{data,data-archive} ($SVC:$DGRP 2770, default ACL g:rwx)"
echo "   $STG/checkout is made by the first deploy (root). $OP's new group counts from a new login."

echo "== 5. config, units, deploy script, sudoers =="
inst() { if [ -f "$3" ] && cmp -s "$2" "$3"; then echo "   unchanged $3"; else install -D -o root -g root -m "$1" "$2" "$3" && echo "   installed $3"; fi; }
inst 644 "$PE/containerd-staging.toml" /etc/containerd-staging/config.toml
inst 644 "$PE/daemon.json" /etc/docker-staging/daemon.json
inst 644 "$PE/containerd-staging.service" "$UNITS/containerd-staging.service"
inst 644 "$PE/docker-staging.service" "$UNITS/docker-staging.service"
inst 755 "$PE/robotics-staging-deploy" /usr/local/libexec/robotics-staging-deploy
tmp=$(mktemp); cp "$PE/robotics-staging.sudoers" "$tmp"
if visudo -cf "$tmp" >/dev/null; then inst 440 "$tmp" /etc/sudoers.d/robotics-staging
else echo "!! sudoers rule failed validation — NOT installed"; rm -f "$tmp"; exit 1; fi
rm -f "$tmp"
/usr/bin/dockerd --validate --config-file /etc/docker-staging/daemon.json >/dev/null || { echo "!! daemon.json invalid"; exit 1; }

echo "== 6. start (the system engine's iptables rules must not change) =="
before=$(iptables-save 2>/dev/null | grep -v '^#' | sed -E 's/\[[0-9]+:[0-9]+\]//')
systemctl daemon-reload
systemctl enable --now containerd-staging.service docker-staging.service
for _ in $(seq 30); do [ -S "$SOCK" ] && break; sleep 1; done
after=$(iptables-save 2>/dev/null | grep -v '^#' | sed -E 's/\[[0-9]+:[0-9]+\]//')

echo "== 7. docker context staging for $SVC =="
dk() { runuser -u "$SVC" -- env -i HOME="$STG/home" PATH=/usr/bin docker "$@"; }
if dk context inspect staging >/dev/null 2>&1; then echo "   exists"
else dk context create staging --docker "host=unix://$SOCK" >/dev/null && echo "   created (unix://$SOCK)"; fi

echo "== 8. checks =="
fail=0
# Without pipefail: `cmd | grep -q` would fail on the SIGPIPE cmd gets once grep has its match.
ck() { if (set +o pipefail; eval "$2") >/dev/null 2>&1; then echo "   ok   $1"; else echo "   FAIL $1"; fail=1; fi; }
ck "containerd-staging and docker-staging active" "systemctl is-active --quiet containerd-staging docker-staging"
ck "staging engine: data root $ENG/docker, containerd image store" \
   "[ \"\$(dk --context staging info --format '{{.DockerRootDir}}')\" = $ENG/docker ] && dk --context staging info --format '{{json .DriverStatus}}' | grep -q io.containerd.snapshotter"
# containerd makes a namespace only with its first object, so a fresh engine has none to list.
ck "staging containerd answers on its own socket" "ctr -a $CSOCK version | grep -q '^Server:'"
ck "socket $SOCK is root:$SVC 0660" "[ \"\$(stat -c '%U:%G %a' $SOCK)\" = 'root:$SVC 660' ]"
ck "the operator's uid is refused at the socket (permission denied)" \
   "{ runuser -u ${SUDO_USER:-marko} -- docker -H unix://$SOCK version --format '{{.Server.Version}}' 2>&1 || true; } | grep -qi 'permission denied'"
ck "staging's content store is not compressed" "btrfs property get $ENG/containerd compression | grep -qx 'compression=none'"
ck "no bridge network on staging (compose on host networking creates none)" \
   "[ \"\$(dk --context staging network ls --format '{{.Name}}' | sort | tr '\n' ' ')\" = 'host none ' ]"
# Rules only, without the packet counters. On a rerun the engine was already up, so this proves
# only the first start; the system engine adding a rule for a container in those seconds shows here too.
ck "iptables rules unchanged by the staging engine's start" "[ \"\$before\" = \"\$after\" ]"
[ "$before" = "$after" ] || diff <(echo "$before") <(echo "$after") | sed 's/^/      /'
ck "system engine untouched: its data root unchanged" \
   "[ \"\$(docker -H unix:///run/docker.sock info --format '{{.DockerRootDir}}')\" = /var/lib/docker ]"
ck "sudoers rule installed and valid" "visudo -cf /etc/sudoers.d/robotics-staging"
ck "data folders: $SVC:$DGRP 2770 with a group-writable default ACL" \
   "for d in data data-archive; do [ \"\$(stat -c '%U:%G %a' $STG/\$d)\" = '$SVC:$DGRP 2770' ] && getfacl -p $STG/\$d | grep -qx 'default:group::rwx' || exit 1; done"
ck "$OP is in $DGRP and not in $SVC" "id -nG $OP | tr ' ' '\n' | grep -qx $DGRP && ! id -nG $OP | tr ' ' '\n' | grep -qx $SVC"
[ "$fail" = 0 ] && echo "== done: PASS. Deploys: sudo robotics-staging-deploy up|rollback|smoke|status (docs/recipes/x3-staging-engine.md)" \
                || { echo "== done: FAIL (see above; nothing was rolled back)"; exit 1; }
