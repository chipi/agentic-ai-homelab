#!/bin/bash
# The X3 — robotics-lab's prod Docker engine (ADR-0013): its own containerd and dockerd as system
# units, data on two new Btrfs subvolumes, a socket only the service user `robotics` can open, and
# one sudoers-allowed deploy script. The system engine (docker.service, containerd.service,
# /var/lib/docker, /var/lib/containerd, /etc/docker) is never touched.
#
# Idempotent. Run as root from the deploy checkout:
#   sudo bash ~/deploy/agentic-ai-homelab/infra/x3/x3-prod-engine-setup.sh
# The first run creates the subvolumes and stops: add the two fstab lines it prints, mount them
# (systemctl daemon-reload; mount /var/lib/docker-prod; mount /srv/robotics-lab), run it again.
#
# Undo: systemctl disable --now docker-prod containerd-prod; remove the two units, /etc/containerd-prod,
#       /etc/docker-prod, /etc/sudoers.d/robotics-prod, /usr/local/libexec/robotics-prod-deploy;
#       systemctl daemon-reload. Prod's data stays on @robotics-prod and its images on @docker-prod
#       until the operator removes the fstab lines and the subvolumes by hand.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; PE="$HERE/prod-engine"
WB="$(cd "$HERE/../.." && pwd)/workstation/storage/wb-storage"
SVC=robotics
PROD=/srv/robotics-lab
ENG=/var/lib/docker-prod
SOCK=/run/docker-prod.sock
CSOCK=/run/containerd-prod/containerd.sock
UNITS=/etc/systemd/system

[ "$(id -u)" -eq 0 ] || { echo "!! must run as root: sudo bash $0"; exit 1; }
for b in /usr/bin/containerd /usr/bin/dockerd /usr/bin/ctr /usr/bin/btrfs /usr/bin/visudo; do
  [ -x "$b" ] || { echo "!! $b missing"; exit 1; }
done

echo "== 1. subvolumes @docker-prod and @robotics-prod (top-level siblings of @, outside Snapper's root) =="
src=$(findmnt -n -o SOURCE --mountpoint /) ; dev=${src%%\[*}
[ "$(findmnt -n -o FSTYPE --mountpoint /)" = btrfs ] || { echo "!! / is not btrfs"; exit 1; }
top=$(mktemp -d)
mount -o subvolid=5 "$dev" "$top" || { rmdir "$top"; echo "!! could not mount the top level of $dev"; exit 1; }
for sv in @docker-prod @robotics-prod; do
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
done < <("$WB" fstab --prod | grep -v '^#')
if [ "$missing" = 1 ]; then
  echo "   -> add these lines to /etc/fstab by hand (this script never edits it), then:"
  echo "      mkdir -p $ENG $PROD; systemctl daemon-reload; mount $ENG; mount $PROD; and run this script again"
  "$WB" fstab --prod | sed 's/^/      /'
  exit 3
fi

echo "== 3. service user $SVC (system, no login, not in docker or wheel) =="
if id "$SVC" >/dev/null 2>&1; then echo "   exists (uid $(id -u "$SVC"))"
else useradd --system --user-group --home-dir "$PROD/home" --no-create-home --shell /usr/bin/nologin "$SVC" && echo "   created (uid $(id -u "$SVC"))"
fi
id -nG "$SVC" | tr ' ' '\n' | grep -qxE 'docker|wheel' && { echo "!! $SVC is in docker or wheel"; exit 1; }

echo "== 4. folders =="
install -d -o root -g root -m 711 "$ENG" "$ENG/containerd" "$ENG/docker" "$ENG/containerd-opt"
# No compression for new files in prod's content store: btrfs zstd with fs-verity is the suspect in the
# X3's containerd read faults (NEXT_STEPS). Undo: btrfs property set $ENG/containerd compression zstd
btrfs property set "$ENG/containerd" compression none || { echo "!! could not turn off compression on $ENG/containerd"; exit 1; }
install -d -o root -g root -m 755 "$PROD"
install -d -o root -g "$SVC" -m 750 /etc/robotics-prod
# robotics owns these, so a symlink here could aim root's chown elsewhere: refuse one.
for d in home home/tmp data data-archive state state/observatory state/mission-control state/deploy; do
  [ -L "$PROD/$d" ] && { echo "!! $PROD/$d is a symlink; not following it"; exit 1; }
  install -d -o "$SVC" -g "$SVC" -m 750 "$PROD/$d"
done
[ -e /etc/robotics-prod/installation.json ] || echo "   NOTE /etc/robotics-prod/installation.json absent: robotics-lab supplies it (root:$SVC 0640)"
echo "   $ENG (root 711), $PROD/{home,data,data-archive,state} ($SVC 750); $PROD/checkout is made by the first deploy (root)"

echo "== 5. config, units, deploy script, sudoers =="
inst() { if [ -f "$3" ] && cmp -s "$2" "$3"; then echo "   unchanged $3"; else install -D -o root -g root -m "$1" "$2" "$3" && echo "   installed $3"; fi; }
inst 644 "$PE/containerd-prod.toml" /etc/containerd-prod/config.toml
inst 644 "$PE/daemon.json" /etc/docker-prod/daemon.json
inst 644 "$PE/containerd-prod.service" "$UNITS/containerd-prod.service"
inst 644 "$PE/docker-prod.service" "$UNITS/docker-prod.service"
inst 755 "$PE/robotics-prod-deploy" /usr/local/libexec/robotics-prod-deploy
tmp=$(mktemp); cp "$PE/robotics-prod.sudoers" "$tmp"
if visudo -cf "$tmp" >/dev/null; then inst 440 "$tmp" /etc/sudoers.d/robotics-prod
else echo "!! sudoers rule failed validation — NOT installed"; rm -f "$tmp"; exit 1; fi
rm -f "$tmp"
/usr/bin/dockerd --validate --config-file /etc/docker-prod/daemon.json >/dev/null || { echo "!! daemon.json invalid"; exit 1; }

echo "== 6. start (the system engine's iptables rules must not change) =="
before=$(iptables-save 2>/dev/null | grep -v '^#' | sed -E 's/\[[0-9]+:[0-9]+\]//')
systemctl daemon-reload
systemctl enable --now containerd-prod.service docker-prod.service
for _ in $(seq 30); do [ -S "$SOCK" ] && break; sleep 1; done
after=$(iptables-save 2>/dev/null | grep -v '^#' | sed -E 's/\[[0-9]+:[0-9]+\]//')

echo "== 7. docker context prod for $SVC =="
dk() { runuser -u "$SVC" -- env -i HOME="$PROD/home" PATH=/usr/bin docker "$@"; }
if dk context inspect prod >/dev/null 2>&1; then echo "   exists"
else dk context create prod --docker "host=unix://$SOCK" >/dev/null && echo "   created (unix://$SOCK)"; fi

echo "== 8. checks =="
fail=0
ck() { if eval "$2" >/dev/null 2>&1; then echo "   ok   $1"; else echo "   FAIL $1"; fail=1; fi; }
ck "containerd-prod and docker-prod active" "systemctl is-active --quiet containerd-prod docker-prod"
ck "prod engine: data root $ENG/docker, containerd image store" \
   "[ \"\$(dk --context prod info --format '{{.DockerRootDir}}')\" = $ENG/docker ] && dk --context prod info --format '{{json .DriverStatus}}' | grep -q io.containerd.snapshotter"
# containerd makes a namespace only with its first object, so a fresh engine has none to list.
ck "prod containerd answers on its own socket" "ctr -a $CSOCK version | grep -q '^Server:'"
ck "socket $SOCK is root:$SVC 0660" "[ \"\$(stat -c '%U:%G %a' $SOCK)\" = 'root:$SVC 660' ]"
ck "the operator's uid is refused at the socket (permission denied)" \
   "{ runuser -u ${SUDO_USER:-marko} -- docker -H unix://$SOCK version --format '{{.Server.Version}}' 2>&1 || true; } | grep -qi 'permission denied'"
ck "prod's content store is not compressed" "btrfs property get $ENG/containerd compression | grep -qx 'compression=none'"
ck "no bridge network on prod (compose on host networking creates none)" \
   "[ \"\$(dk --context prod network ls --format '{{.Name}}' | sort | tr '\n' ' ')\" = 'host none ' ]"
# Rules only, without the packet counters. On a rerun the engine was already up, so this proves
# only the first start; the system engine adding a rule for a container in those seconds shows here too.
ck "iptables rules unchanged by the prod engine's start" "[ \"\$before\" = \"\$after\" ]"
[ "$before" = "$after" ] || diff <(echo "$before") <(echo "$after") | sed 's/^/      /'
ck "system engine untouched: its data root unchanged" \
   "[ \"\$(docker -H unix:///run/docker.sock info --format '{{.DockerRootDir}}')\" = /var/lib/docker ]"
ck "sudoers rule installed and valid" "visudo -cf /etc/sudoers.d/robotics-prod"
[ "$fail" = 0 ] && echo "== done: PASS. Deploys: sudo robotics-prod-deploy up|rollback|smoke|status (docs/recipes/x3-prod-engine.md)" \
                || { echo "== done: FAIL (see above; nothing was rolled back)"; exit 1; }
