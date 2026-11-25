#!/bin/bash
# The X3 — self-hosted GitHub Actions runners for the private repos (ADR-0015): a service user
# `gh-runner` outside the docker group, its own rootless Docker engine, and one container per runner.
# Everything gh-runner runs is capped together in its user slice (8 cores, 32 GB), so CI cannot
# starve the operator's sessions or robotics-lab. The system engine is never touched.
#
# Idempotent. Run as root from the deploy checkout:
#   sudo bash ~/deploy/agentic-ai-homelab/infra/x3/x3-ci-runner-setup.sh
# Then register a runner per repo with ci-runner/register.sh (it prints the next step).
#
# Undo: for each instance, systemctl --user -M gh-runner@ disable --now ci-runner@<instance>, and
#       delete the runner in the repo's Settings → Actions → Runners; then
#       systemctl --user -M gh-runner@ disable --now docker; loginctl disable-linger gh-runner;
#       userdel -r gh-runner; remove /etc/systemd/system/user-<uid>.slice.d/50-ci-cap.conf,
#       /usr/local/bin/dockerd-rootless.sh and the gh-runner lines in /etc/subuid and /etc/subgid;
#       pacman -Rs rootlesskit slirp4netns.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; CR="$HERE/ci-runner"
U=gh-runner
HOMEDIR=/var/lib/gh-runner
SUBID_START=200000   # marko holds 100000-165535
ROOTLESS_SHA=904c9b9e35f6927c0a5e65afb4d35b6bc9eb1278c878044501281fc728c9be46   # moby docker-v29.7.2 contrib/dockerd-rootless.sh
CPU_QUOTA=800%
MEM_MAX=32G

[ "$(id -u)" -eq 0 ] || { echo "!! must run as root: sudo bash $0"; exit 1; }
fail=0
ok()   { echo "OK    $*"; }
bad()  { echo "FAIL  $*"; fail=1; }
step() { echo "==    $*"; }

step "packages (Arch extra): rootlesskit slirp4netns"
pacman -S --needed --noconfirm rootlesskit slirp4netns >/dev/null && ok "rootlesskit $(pacman -Q rootlesskit | cut -d' ' -f2), slirp4netns $(pacman -Q slirp4netns | cut -d' ' -f2)" || bad "pacman"

step "dockerd-rootless.sh (Docker's own, at the installed engine's version, checksum-pinned)"
if [ "$(sha256sum "$CR/dockerd-rootless.sh" | cut -d' ' -f1)" = "$ROOTLESS_SHA" ]; then
  install -m 755 -o root -g root "$CR/dockerd-rootless.sh" /usr/local/bin/dockerd-rootless.sh && ok "/usr/local/bin/dockerd-rootless.sh"
else
  bad "dockerd-rootless.sh does not match its pinned checksum"
fi

step "user $U (no login shell, not in the docker group)"
id "$U" >/dev/null 2>&1 || useradd --system --create-home --home-dir "$HOMEDIR" --shell /usr/bin/nologin "$U"
UID_R=$(id -u "$U")
if id -nG "$U" | tr ' ' '\n' | grep -qx docker; then bad "$U is in the docker group"; else ok "$U uid $UID_R, groups: $(id -nG "$U")"; fi
for f in /etc/subuid /etc/subgid; do
  grep -q "^$U:" "$f" || echo "$U:$SUBID_START:65536" >> "$f"
done
ok "subordinate ids: $(grep "^$U:" /etc/subuid)"

step "the cap: everything $U runs shares $CPU_QUOTA CPU and $MEM_MAX memory"
d=/etc/systemd/system/user-$UID_R.slice.d
mkdir -p "$d"
printf '[Slice]\nCPUQuota=%s\nMemoryMax=%s\nMemoryHigh=%s\n' "$CPU_QUOTA" "$MEM_MAX" "$(( ${MEM_MAX%G} * 7 / 8 ))G" > "$d/50-ci-cap.conf"
systemctl daemon-reload
ok "$(systemctl show "user-$UID_R.slice" -p CPUQuotaPerSecUSec -p MemoryMax | tr '\n' ' ')"

step "linger: $U's user manager runs without a login"
loginctl enable-linger "$U"
for i in $(seq 20); do [ -S "/run/user/$UID_R/bus" ] && break; sleep 0.5; done
[ -S "/run/user/$UID_R/bus" ] && ok "user manager up" || bad "no user manager for $U"

step "units and runner files in $HOMEDIR"
install -d -m 755 -o "$U" -g "$U" "$HOMEDIR/.config" "$HOMEDIR/.config/systemd" "$HOMEDIR/.config/systemd/user" "$HOMEDIR/ci-runner"
install -m 644 -o "$U" -g "$U" "$CR/docker.service" "$CR/ci-runner@.service" "$HOMEDIR/.config/systemd/user/"
install -m 755 -o "$U" -g "$U" "$CR/entrypoint.sh" "$HOMEDIR/ci-runner/entrypoint.sh"
ok "docker.service, ci-runner@.service, entrypoint.sh"

UC() { systemctl --user -M "$U@" "$@"; }
step "the rootless engine"
UC daemon-reload
UC enable --now docker.service >/dev/null 2>&1
for i in $(seq 30); do [ -S "/run/user/$UID_R/docker.sock" ] && break; sleep 1; done
AS() { sudo -u "$U" env XDG_RUNTIME_DIR="/run/user/$UID_R" DOCKER_HOST="unix:///run/user/$UID_R/docker.sock" "$@"; }
if AS docker info --format '{{.SecurityOptions}} {{.Driver}}' 2>/dev/null | grep -q rootless; then
  ok "rootless engine: $(AS docker info --format '{{.ServerVersion}}, {{.Driver}}, {{.DockerRootDir}}')"
else
  bad "the rootless engine is not up: journalctl _UID=$UID_R -n 30"
fi

step "smoke: a container runs, a published port stays inside the engine"
if AS docker run --rm -d --name ci-smoke -p 15432:80 nginx:alpine >/dev/null 2>&1; then
  sleep 2
  inside=$(AS docker run --rm --network host curlimages/curl -s -o /dev/null -w '%{http_code}' -m 5 http://127.0.0.1:15432/ 2>/dev/null)
  host=$(curl -s -o /dev/null -w '%{http_code}' -m 3 http://127.0.0.1:15432/ 2>/dev/null)
  AS docker rm -f ci-smoke >/dev/null 2>&1
  [ "$inside" = 200 ] && ok "port reachable inside the engine (200)" || bad "port not reachable inside the engine ($inside)"
  [ "$host" != 200 ] && ok "port not on the X3 itself (${host:-000})" || bad "port is published on the X3"
else
  bad "could not run a container"
fi

echo
[ "$fail" = 0 ] && echo "SETUP PASS — next: register a runner (infra/x3/ci-runner/register.sh)" || echo "SETUP FAIL — fix the FAIL lines and run again"
exit $fail
