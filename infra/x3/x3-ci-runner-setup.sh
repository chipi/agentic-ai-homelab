#!/bin/bash
# The X3 — self-hosted GitHub Actions runners for the private repos (ADR-0015): a service user
# `gh-runner` outside the docker group, and per runner a container on its own rootless Docker engine.
# Everything gh-runner runs is capped together in its user slice (8 cores, 32 GB), so CI cannot
# starve the operator's sessions or robotics-lab. The system engine is never touched.
#
# Idempotent. Run as root from the deploy checkout:
#   sudo bash ~/deploy/agentic-ai-homelab/infra/x3/x3-ci-runner-setup.sh
# Then register a runner per repo with ci-runner/register.sh (it prints the next step).
#
# Undo: for each instance, systemctl --user -M gh-runner@ disable --now ci-runner@<instance>
#       docker@<instance>, and delete the runner in the repo's Settings → Actions → Runners; then
#       loginctl disable-linger gh-runner;
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
UD="$HOMEDIR/.config/systemd/user"
install -d -m 755 -o "$U" -g "$U" "$HOMEDIR/.config" "$HOMEDIR/.config/systemd" "$UD" "$HOMEDIR/ci-runner"
runner_changed=""
for f in docker@.service ci-runner@.service; do cmp -s "$CR/$f" "$UD/$f" || runner_changed=1; done
cmp -s "$CR/entrypoint.sh" "$HOMEDIR/ci-runner/entrypoint.sh" || runner_changed=1
install -m 644 -o "$U" -g "$U" "$CR/docker@.service" "$CR/ci-runner@.service" "$UD/"
install -m 755 -o "$U" -g "$U" "$CR/entrypoint.sh" "$HOMEDIR/ci-runner/entrypoint.sh"
ok "docker@.service, ci-runner@.service, entrypoint.sh"

UC() { systemctl --user -M "$U@" "$@"; }
# AS <instance> <command…>: a command as gh-runner against that instance's engine.
AS() { local i=$1; shift; sudo -u "$U" env XDG_RUNTIME_DIR="/run/user/$UID_R" DOCKER_HOST="unix:///run/user/$UID_R/e-$i/docker.sock" "$@"; }
UC daemon-reload

# Until 2026-11-25 all runners shared one engine (docker.service); each now has its own.
if [ -f "$UD/docker.service" ]; then
  step "retire the shared engine of the first version"
  UC disable --now docker.service >/dev/null 2>&1
  rm -f "$UD/docker.service"; UC daemon-reload
  rm -rf "$HOMEDIR/.local/share/docker"
  ok "docker.service stopped and removed, with its images and volumes"
  echo "NOTE  runners registered on it lost their registration: register each again with register.sh"
fi

step "smoke: two engines side by side, each publishing port 15432, neither on the X3"
smoke_ok=1
for i in smoke-a smoke-b; do
  UC start "docker@$i.service" >/dev/null 2>&1
  for t in $(seq 40); do [ -S "/run/user/$UID_R/e-$i/docker.sock" ] && break; sleep 1; done
  if AS "$i" docker info --format '{{json .SecurityOptions}}' 2>/dev/null | grep -q rootless \
     && AS "$i" docker run -d --name ci-smoke -p 15432:80 nginx:alpine >/dev/null 2>&1; then
    ok "engine $i up, a container publishing 15432"
  else
    bad "engine $i: no rootless engine or no container (journalctl _UID=$UID_R -n 30)"; smoke_ok=""
  fi
done
if [ -n "$smoke_ok" ]; then
  sleep 2
  for i in smoke-a smoke-b; do
    inside=$(AS "$i" docker run --rm --network host curlimages/curl -s -o /dev/null -w '%{http_code}' -m 8 http://127.0.0.1:15432/ 2>/dev/null)
    [ "$inside" = 200 ] && ok "engine $i: port reachable inside its own network (200)" || bad "engine $i: port not reachable inside ($inside)"
  done
  host=$(curl -s -o /dev/null -w '%{http_code}' -m 3 http://127.0.0.1:15432/ 2>/dev/null)
  [ "$host" != 200 ] && ok "port not on the X3 itself (${host:-000})" || bad "port is published on the X3"
fi
for i in smoke-a smoke-b; do
  AS "$i" docker rm -f ci-smoke >/dev/null 2>&1
  UC stop "docker@$i.service" >/dev/null 2>&1
  rm -rf "$HOMEDIR/.local/share/docker-$i"
done

if [ -n "$runner_changed" ]; then
  step "runners: restart the registered ones for their changed files (a running job is stopped)"
  for u in $(UC list-units --all --plain --no-legend 'ci-runner@*' 2>/dev/null | awk '{print $1}'); do
    UC restart "$u" && ok "restarted $u" || bad "could not restart $u"
  done
fi

echo
[ "$fail" = 0 ] && echo "SETUP PASS — next: register a runner (infra/x3/ci-runner/register.sh)" || echo "SETUP FAIL — fix the FAIL lines and run again"
exit $fail
