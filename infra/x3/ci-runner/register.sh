#!/bin/bash
# Registers one runner for one repo, on its own rootless engine, and starts it (ADR-0015). As root:
#   sudo bash register.sh <repo> <n> <token-file>
# <token-file> holds a registration token (one hour, one use): an agent writes it with
#   gh api -X POST repos/chipi/<repo>/actions/runners/registration-token -q .token
# The runner is named x3-<repo>-<n> and carries the labels self-hosted, linux, x64, x3. The token is
# read from the file, handed to the runner's state volume, used once and deleted there. Registering
# a name again replaces the old registration (config.sh --replace).
set -uo pipefail
U=gh-runner
repo=${1:?usage: register.sh <repo> <n> <token-file>}; n=${2:?}; tok=${3:?}
[ "$(id -u)" -eq 0 ] || { echo "!! must run as root"; exit 1; }
[ -s "$tok" ] || { echo "!! no token in $tok"; exit 1; }
UID_R=$(id -u "$U") || exit 1
H=$(getent passwd "$U" | cut -d: -f6)
inst="$repo-$n"
AS() { sudo -u "$U" env XDG_RUNTIME_DIR="/run/user/$UID_R" DOCKER_HOST="unix:///run/user/$UID_R/e-$inst/docker.sock" "$@"; }
UC() { systemctl --user -M "$U@" "$@"; }

install -m 600 -o "$U" -g "$U" /dev/stdin "$H/ci-runner/$inst.env" <<EOF
REPO_URL=https://github.com/chipi/$repo
RUNNER_NAME=x3-$inst
RUNNER_LABELS=x3
EOF
UC daemon-reload
UC stop "ci-runner@$inst.service" >/dev/null 2>&1
UC enable --now "docker@$inst.service" >/dev/null 2>&1
for i in $(seq 40); do [ -S "/run/user/$UID_R/e-$inst/docker.sock" ] && break; sleep 1; done
AS docker info >/dev/null 2>&1 || { echo "REGISTER FAIL — the engine docker@$inst is not up: journalctl _UID=$UID_R -n 30"; exit 1; }
AS docker volume rm -f "ci-runner-$inst" >/dev/null 2>&1
AS docker volume create "ci-runner-$inst" >/dev/null
AS docker run --rm -i -v "ci-runner-$inst:/s" alpine sh -c 'umask 077; cat > /s/token' < "$tok"
rm -f "$tok"
UC enable --now "ci-runner@$inst.service" >/dev/null 2>&1
for i in $(seq 180); do   # the first start pulls the runner image into the new engine
  AS docker logs "ci-runner-$inst" 2>&1 | grep -q 'Listening for Jobs' && break
  sleep 2
done
if AS docker logs "ci-runner-$inst" 2>&1 | grep -q 'Listening for Jobs'; then
  echo "REGISTER PASS — x3-$inst is listening for jobs on chipi/$repo"
else
  echo "REGISTER FAIL — the runner is not listening:"; AS docker logs --tail 15 "ci-runner-$inst" 2>&1
  exit 1
fi
