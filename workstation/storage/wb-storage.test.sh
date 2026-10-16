#!/usr/bin/env bash
# Tests for wb-storage and the storage drop-ins. Every case runs against a scratch
# root (WB_STORAGE_ROOT) with a fake findmnt; the live /etc, mounts, subvolumes,
# Docker and /work are never touched.
#   bash workstation/storage/wb-storage.test.sh
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; CMD="$HERE/wb-storage"
WS="$(cd "$HERE/.." && pwd)"; REPO="$(cd "$WS/.." && pwd)"
T="$(mktemp -d)"
OWNED=()   # PIDs this test started (users cases); stopped by PID only
trap 'for p in "${OWNED[@]}"; do kill "$p" 2>/dev/null; done; rm -rf "$T"' EXIT
pass=0; fail=0
chk() { if eval "$2"; then echo "  ok   $1"; pass=$((pass+1)); else echo "  FAIL $1"; fail=$((fail+1)); fi; }

# The X3 root filesystem UUID, assembled so this file never contains it literally.
X3_UUID="3addef3c""-18a8-45e3-b929-""8f7f2f2cb736"
FAKE_UUID="0f0f0f0f-1111-4222-8333-444455556666"
OPTS="rw,relatime,compress=zstd:3,ssd,space_cache=v2"

# fake findmnt: answers `-n -o <cols> --mountpoint <p>` from $FAKE_MOUNTS
# ("<mountpoint> <fstype> <options> <uuid>" per line); no line, no output, exit 1.
mkdir -p "$T/bin"
cat > "$T/bin/findmnt" <<'EOF'
#!/bin/sh
cols=; mp=
while [ $# -gt 0 ]; do case $1 in -o) cols=$2; shift ;; --mountpoint) mp=$2; shift ;; esac; shift; done
awk -v mp="$mp" -v cols="$cols" '$1 == mp {
  n = split(cols, c, ","); out = ""
  for (i = 1; i <= n; i++) {
    v = (c[i] == "FSTYPE") ? $2 : (c[i] == "OPTIONS") ? $3 : (c[i] == "UUID") ? $4 : ""
    out = out (i > 1 ? " " : "") v
  }
  print out; found = 1
} END { exit found ? 0 : 1 }' "$FAKE_MOUNTS"
EOF
chmod +x "$T/bin/findmnt"

# box <name> [root-options]: a scratch root with an Omarchy-like fstab and the root mount.
box() {
  B="$T/$1"; mkdir -p "$B/etc/systemd/system/docker.service.d"
  local ro="${2:-$OPTS,subvol=/@}"
  printf '# Static information about the filesystems.\nUUID=%s\t/\tbtrfs\t%s\t0 0\nUUID=%s\t/home\tbtrfs\t%s,subvol=/@home\t0 0\n' \
    "$FAKE_UUID" "$ro" "$FAKE_UUID" "$OPTS" > "$B/etc/fstab"
  printf '/ btrfs %s %s\n' "$ro" "$FAKE_UUID" > "$B.mounts"
  # Omarchy's package-owned drop-in, which must never be rewritten.
  printf '[Unit]\nDefaultDependencies=no\n' > "$B/etc/systemd/system/docker.service.d/no-block-boot.conf"
}
ws() { WB_STORAGE_ROOT="$B" WB_STORAGE_FINDMNT="$T/bin/findmnt" FAKE_MOUNTS="$B.mounts" "$CMD" "$@"; }
st() { ws status "$@" > "$B.out" 2>&1; echo $?; }
mounted() { printf '%s btrfs %s,subvolid=300,subvol=/%s %s\n' "$1" "$OPTS" "$2" "$FAKE_UUID" >> "$B.mounts"; }
add_fstab() { ws fstab | grep -v '^#' >> "$B/etc/fstab"; }
populate() {
  mkdir -p "$B/work/orrery/main/.git" "$B/var/lib/docker" "$B/var/lib/containerd/io.containerd.content.v1.content"
  echo data > "$B/work/orrery/main/README.md"; echo id > "$B/var/lib/docker/engine-id"; echo blob > "$B/var/lib/containerd/io.containerd.content.v1.content/b"
}
sig() { (cd "$B" && find . -printf '%p|%y|%s|%m|%T@|%i\n' | sort; find . -type f -exec md5sum {} + | sort) | md5sum; }

echo "== drop-ins (repository-owned, separate from Omarchy's no-block-boot.conf)"
DD="$HERE/systemd/docker.service.d/50-x3-storage-mounts.conf"
CD="$HERE/systemd/containerd.service.d/50-x3-storage-mounts.conf"
chk "docker drop-in: [Unit] RequiresMountsFor= both /var/lib/docker and /var/lib/containerd" \
  "grep -qx '\[Unit\]' '$DD' && [ \"\$(grep -v '^#' '$DD' | grep '^RequiresMountsFor=')\" = 'RequiresMountsFor=/var/lib/docker /var/lib/containerd' ]"
chk "containerd drop-in: [Unit] RequiresMountsFor=/var/lib/containerd" \
  "grep -qx '\[Unit\]' '$CD' && [ \"\$(grep -v '^#' '$CD' | grep '^RequiresMountsFor=')\" = 'RequiresMountsFor=/var/lib/containerd' ]"
chk "drop-ins set nothing else (no DefaultDependencies, no Exec*/Service section)" \
  "[ \"\$(grep -hv -e '^#' -e '^[[:space:]]*\$' '$DD' '$CD' | sort -u | tr '\n' '|')\" = 'RequiresMountsFor=/var/lib/containerd|RequiresMountsFor=/var/lib/docker /var/lib/containerd|[Unit]|' ]"
chk "no repository file is named no-block-boot.conf" "[ -z \"\$(find '$WS' -name no-block-boot.conf)\" ]"

echo "== fstab rendering (derived from the mounted root, never hard-coded)"
box render
chk "renders the three entries in order with the root's UUID and options + subvol=/@<name>" \
  "[ \"\$(ws fstab | grep -v '^#')\" = \"\$(printf 'UUID=%s\t/work\tbtrfs\t%s,subvol=/@work\t0 0\nUUID=%s\t/var/lib/containerd\tbtrfs\t%s,subvol=/@containerd\t0 0\nUUID=%s\t/var/lib/docker\tbtrfs\t%s,subvol=/@docker\t0 0' \"$FAKE_UUID\" \"$OPTS\" \"$FAKE_UUID\" \"$OPTS\" \"$FAKE_UUID\" \"$OPTS\")\" ]"
chk "never nofail in an entry; never the X3 UUID when run elsewhere" "! ws fstab | grep -v '^#' | grep -q -e nofail -e '$X3_UUID'"
box render-opts "rw,noatime,compress=zstd:1,subvolid=256,subvol=/@,nofail"
chk "other root options are carried over; subvolid= and nofail are dropped" \
  "[ \"\$(ws fstab | grep -v '^#' | head -1 | cut -f4)\" = 'rw,noatime,compress=zstd:1,subvol=/@work' ]"
box render-ext4; printf '/ ext4 rw %s\n' "$FAKE_UUID" > "$B.mounts"
chk "root not btrfs: refuses (exit 2), prints no entries" "ws fstab > '$B.out' 2>&1; [ \$? = 2 ] && ! grep -q '^UUID=' '$B.out'"
box render-nosub "$OPTS"
chk "root entry without subvol=/@: refuses (exit 2)" "ws fstab >/dev/null 2>&1; [ \$? = 2 ]"
box render-mismatch; sed -i "s/^UUID=$FAKE_UUID\t\/\t/UUID=99999999-0000-4000-8000-000000000000\t\/\t/" "$B/etc/fstab"
chk "fstab root UUID differs from the mounted root: refuses (exit 2)" "ws fstab >/dev/null 2>&1; [ \$? = 2 ]"

echo "== status: classification, and it never changes anything"
box fresh-absent; before=$(sig)
chk "fresh (paths absent, no entries): exit 3 'fresh'" "[ \$(st) = 3 ] && grep -q '^fresh:' '$B.out'"
chk "status changed nothing in the scratch root" "[ \"\$(sig)\" = '$before' ]"
box fresh-empty; mkdir -p "$B/work" "$B/var/lib/docker" "$B/var/lib/containerd"
chk "fresh (empty directories): exit 3" "[ \$(st) = 3 ]"
box populated; populate; before=$(sig)
chk "populated /work + Docker trees: exit 4 'needs-migration', points at the runbook" \
  "[ \$(st) = 4 ] && grep -q '^needs-migration:.*docs/recipes/x3-storage-separation.md' '$B.out'"
chk "populated: nothing moved, copied or deleted" "[ \"\$(sig)\" = '$before' ]"
box docker-only; mkdir -p "$B/var/lib/docker"; echo id > "$B/var/lib/docker/engine-id"
chk "only /var/lib/docker populated (Docker started before the layout): exit 4" "[ \$(st) = 4 ]"
box separated; mkdir -p "$B/work" "$B/var/lib/docker" "$B/var/lib/containerd"; add_fstab
mounted /work @work; mounted /var/lib/containerd @containerd; mounted /var/lib/docker @docker
ws install-dropins >/dev/null
chk "separated (mounted from the right subvolumes, entries, drop-ins): exit 0" "[ \$(st) = 0 ] && grep -q '^separated:' '$B.out'"
rm "$B/etc/systemd/system/containerd.service.d/50-x3-storage-mounts.conf"
chk "mounted but a drop-in missing: exit 5 'incomplete'" "[ \$(st) = 5 ] && grep -q '^incomplete:' '$B.out'"
box entries-only; mkdir -p "$B/work" "$B/var/lib/docker" "$B/var/lib/containerd"; add_fstab
chk "fstab entries but nothing mounted: exit 5" "[ \$(st) = 5 ]"
box wrong-subvol; mkdir -p "$B/work" "$B/var/lib/docker" "$B/var/lib/containerd"; add_fstab
mounted /work @home; mounted /var/lib/containerd @containerd; mounted /var/lib/docker @docker; ws install-dropins >/dev/null
chk "/work mounted from the wrong subvolume: exit 5, reported" "[ \$(st) = 5 ] && grep -q '/work .*not from the expected subvolume' '$B.out'"
box nofail-entry; mkdir -p "$B/work" "$B/var/lib/docker" "$B/var/lib/containerd"
ws fstab | grep -v '^#' | sed 's/,subvol=/,nofail,subvol=/' >> "$B/etc/fstab"
mounted /work @work; mounted /var/lib/containerd @containerd; mounted /var/lib/docker @docker; ws install-dropins >/dev/null
chk "an entry with nofail is 'wrong': exit 5" "[ \$(st) = 5 ] && grep -q 'fstab entry: wrong' '$B.out'"
box brief; populate
chk "--brief prints only the verdict line" "ws status --brief > '$B.out' 2>&1; [ \$? = 4 ] && [ \$(wc -l < '$B.out') = 1 ]"

echo "== install-dropins: idempotent, coexists with no-block-boot.conf"
box inst; NB="$B/etc/systemd/system/docker.service.d/no-block-boot.conf"; nb_before=$(stat -c '%s|%Y|%i' "$NB"; md5sum < "$NB")
before=$(sig)
ws install-dropins --dry-run > "$B.out" 2>&1
chk "dry-run: INST announced for both, nothing written" "[ \$(grep -c '^INST' '$B.out') = 2 ] && [ \"\$(sig)\" = '$before' ]"
ws install-dropins > "$B.out" 2>&1; rc=$?
chk "first run: both installed, byte-identical to the repo, mode 0644" \
  "[ $rc = 0 ] && cmp -s '$DD' '$B/etc/systemd/system/docker.service.d/50-x3-storage-mounts.conf' && cmp -s '$CD' '$B/etc/systemd/system/containerd.service.d/50-x3-storage-mounts.conf' && [ \$(stat -c %a '$B/etc/systemd/system/docker.service.d/50-x3-storage-mounts.conf') = 644 ]"
chk "no-block-boot.conf untouched (size, mtime, inode, content)" "[ \"\$(stat -c '%s|%Y|%i' '$NB'; md5sum < '$NB')\" = '$nb_before' ]"
chk "never reloads units itself: prints the daemon-reload step" "grep -q '^NEXT  systemctl daemon-reload' '$B.out'"
after=$(sig); ws install-dropins > "$B.out" 2>&1
chk "rerun: OK for both, nothing changed, no backups" \
  "[ \$(grep -c '^OK    already installed' '$B.out') = 2 ] && [ \"\$(sig)\" = '$after' ] && [ -z \"\$(find '$B/etc' -name '*.bak.*')\" ]"
echo '# local edit' >> "$B/etc/systemd/system/containerd.service.d/50-x3-storage-mounts.conf"
ws install-dropins > "$B.out" 2>&1
chk "drifted copy: backed up, then replaced; the other one left alone" \
  "[ \$(grep -c '^BACK' '$B.out') = 1 ] && [ -n \"\$(find '$B/etc/systemd/system/containerd.service.d' -name '*.bak.*')\" ] && cmp -s '$CD' '$B/etc/systemd/system/containerd.service.d/50-x3-storage-mounts.conf'"
chk "no-block-boot.conf still untouched" "[ \"\$(stat -c '%s|%Y|%i' '$NB'; md5sum < '$NB')\" = '$nb_before' ]"
if [ "$(id -u)" != 0 ]; then
  chk "without a scratch root and not root: refuses before writing (exit 2)" \
    "env -u WB_STORAGE_ROOT '$CMD' install-dropins >/dev/null 2>&1; [ \$? = 2 ]"
fi

echo "== users: read-only live-process check (cwd, open fds, mapped files)"
U="$T/users"; mkdir -p "$U/cwd" "$U/fd" "$U/map" "$T/elsewhere"
echo x > "$U/fd/held"; cp "$(command -v sleep)" "$U/map/sleep"
(cd "$U/cwd" && exec sleep 300) & OWNED+=($!)
(cd "$T/elsewhere" && exec bash -c 'exec 3<"$1"; exec sleep 300' _ "$U/fd/held") & OWNED+=($!)
(cd "$T/elsewhere" && exec "$U/map/sleep" 300) & OWNED+=($!)
sleep 0.5
(cd "$T/elsewhere" && "$CMD" users "$U" > "$U.out" 2>&1); urc=$?
chk "finds the process by cwd, by open fd and by mapped executable (exit 1)" \
  "[ $urc = 1 ] && grep -q '^pid ${OWNED[0]} ' '$U.out' && grep -q '^pid ${OWNED[1]} ' '$U.out' && grep -q '^pid ${OWNED[2]} ' '$U.out'"
chk "reports what it found and how to stop it (by PID), stops nothing itself" \
  "grep -q 'stop each one yourself, by PID' '$U.out' && kill -0 ${OWNED[0]} && kill -0 ${OWNED[1]} && kill -0 ${OWNED[2]}"
for p in "${OWNED[@]}"; do kill "$p" 2>/dev/null; wait "$p" 2>/dev/null; done
(cd "$T/elsewhere" && "$CMD" users "$U" > "$U.out" 2>&1); urc=$?
if [ "$(id -u)" = 0 ]; then
  chk "nothing left: exit 0" "[ $urc = 0 ]"
else
  chk "nothing visible as non-root: exit 2 (inconclusive), says to run as root" "[ $urc = 2 ] && grep -q 'run as root' '$U.out'"
fi
(cd "$U/cwd" && "$CMD" users "$U" > "$U.out" 2>&1); urc=$?
chk "run from inside a checked path: refuses (exit 2)" "[ $urc = 2 ] && grep -q 'run this from outside' '$U.out'"
chk "a sibling path with the same prefix is not a match (/x/cwd vs /x/cwd2)" \
  "mkdir -p '$U/cwd2'; (cd '$U/cwd2' && '$CMD' users '$U/cwd' >/dev/null 2>&1); [ \$? != 1 ]"

echo "== static guards: no automatic migration, no destructive commands"
# danger <file>: print executable (non-comment) lines that would mutate storage,
# Docker or system units. Command patterns are matched with quoted strings blanked
# (so a printed hint like "NEXT  systemctl daemon-reload" is not a command); a
# write redirect to fstab is matched on the raw line.
danger() {
  local n=0 line s
  while IFS= read -r line; do
    n=$((n+1))
    [[ $line =~ ^[[:space:]]*# ]] && continue
    s=$(sed -E "s/\"[^\"]*\"/\"\"/g; s/'[^']*'//g" <<<"$line")
    if grep -qE \
         -e 'btrfs[[:space:]]+(subvolume|property|balance|filesystem[[:space:]]+(resize|defrag))' \
         -e '(^|[;&|(`[:space:]])u?mount([[:space:]]|$)' \
         -e '(^|[;&|(`[:space:]])(rm|rmdir|rsync|chattr|mkfs[.a-z0-9]*|cryptsetup|snapper|fstrim|kill|pkill|killall)([[:space:]]|$)' \
         -e '(^|[;&|(`[:space:]])(mv|cp)[[:space:]].*(/work|/var/lib/(docker|containerd)|fstab)' \
         -e '(^|[;&|(`[:space:]])systemctl[[:space:]]+(-[a-z-]+[[:space:]]+)*(stop|start|restart|reload|daemon-reload|kill|mask|disable|enable)' \
         -e '(^|[;&|(`[:space:]])docker([[:space:]]|$)' -e 'prune' <<<"$s" \
       || grep -qE '>>?[[:space:]]*"?[$A-Za-z_{}]*/?etc/fstab' <<<"$line"; then
      echo "$n:$line"
    fi
  done < "$1"
}
chk "wb-storage has no mutating storage/Docker/unit command" "[ -z \"\$(danger '$CMD')\" ]"
# install.sh: its own home-dir backups (mv to *.bak) and the user ssh-agent enable are expected.
chk "install.sh has no storage/Docker/system-unit mutation" \
  "[ -z \"\$(danger '$WS/install.sh' | grep -v 'systemctl --user ')\" ]"
# Prove the guard bites: each mutation of a copy must be caught.
caught=1
for m in 'btrfs subvolume create /x/@work' 'mount /work' 'umount /var/lib/docker' 'rm -rf "$R/work"' \
         'mv /work /work.pre-subvol' 'cp -a /work/. /x/' 'rsync -aHAX /work/ /x/' 'systemctl stop docker.socket' \
         'systemctl daemon-reload' 'docker image ls' 'docker system prune -f' 'echo x >> "$R/etc/fstab"' \
         'snapper -c root create' 'chattr +C /var/lib/docker' 'kill "$pid"' 'pkill -f node'; do
  cp "$CMD" "$T/mut"; printf '%s\n' "$m" >> "$T/mut"
  [ -n "$(danger "$T/mut")" ] || { caught=0; echo "    guard missed: $m"; }
done
chk "guard catches each injected mutation (16 mutants)" "[ $caught = 1 ]"
chk "no prune / rm -rf / compose down -v in the storage code, drop-ins or installer" \
  "! grep -rnE 'prune|rm -rf|down -v' '$CMD' '$HERE/systemd' '$WS/install.sh'"
chk "portable code and docs never contain the X3 root UUID (only the X3 runbook may)" \
  "! grep -rlF '$X3_UUID' '$WS' '$REPO/docs/adr' '$REPO/docs/recipes/x3-storage-safety-copy-retirement.md' 2>/dev/null | grep -q ."
chk "X3 runbook marks the UUID it shows as X3-specific evidence" \
  "grep -qF '$X3_UUID' '$REPO/docs/recipes/x3-storage-separation.md' && grep -qi 'X3-specific' '$REPO/docs/recipes/x3-storage-separation.md'"
chk "runbook and retirement procedure exist and never prune Docker" \
  "[ -f '$REPO/docs/recipes/x3-storage-separation.md' ] && [ -f '$REPO/docs/recipes/x3-storage-safety-copy-retirement.md' ] && ! grep -nE 'docker[a-z ]* prune' '$REPO/docs/recipes/x3-storage-separation.md' '$REPO/docs/recipes/x3-storage-safety-copy-retirement.md'"

echo; echo "RESULT: pass=$pass fail=$fail"
[ "$fail" = 0 ]
