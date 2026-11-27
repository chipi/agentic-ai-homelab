#!/bin/bash
# As gh-runner, every 2 minutes (ci-runner-sync.timer): install the runner files the operator's account
# copies to /srv/ci-runner-src, and restart each runner that is behind them, one at a time, only while it
# has no job. A runner fix then needs no sudo: every fix through 2026-11-26 waited on the operator to run
# x3-ci-runner-setup.sh (operator: "make it work without me"). The setup itself is still for what
# gh-runner cannot do (packages, the slice cap, subordinate ids, linger).
#   Copy a fix in (as the operator's account, from the deploy checkout):
#     install -m 644 ~/deploy/agentic-ai-homelab/infra/x3/ci-runner/{docker@.service,ci-runner@.service,entrypoint.sh,Dockerfile,sync.sh} /srv/ci-runner-src/
#   Log: journalctl --user -M gh-runner@ -u ci-runner-sync (as root), or /srv/ci-runner-src/log/sync.log (readable without sudo).
set -uo pipefail
SRC=${CI_RUNNER_SRC:-/srv/ci-runner-src}
UD=$HOME/.config/systemd/user
CR=$HOME/ci-runner
log() { echo "$(date -u +%FT%TZ) $*" | tee -a "$SRC/log/sync.log" 2>/dev/null; }
[ -d "$SRC" ] || exit 0
mkdir -p "$CR/applied" "$CR/image"

put() {   # put <file in SRC> <destination> <mode>: 0 when the destination changed
  [ -s "$SRC/$1" ] || return 1
  cmp -s "$SRC/$1" "$2" && return 1
  install -m "$3" "$SRC/$1" "$2" && log "installed $1"
}
reload=""
put docker@.service "$UD/docker@.service" 644 && reload=1
put ci-runner@.service "$UD/ci-runner@.service" 644 && reload=1
put entrypoint.sh "$CR/entrypoint.sh" 755
put Dockerfile "$CR/image/Dockerfile" 644
put sync.sh "$CR/sync.sh" 755
[ -n "$reload" ] && systemctl --user daemon-reload

runner_v=$(cat "$UD/ci-runner@.service" "$CR/entrypoint.sh" "$CR/image/Dockerfile" | sha256sum | cut -c1-16)
engine_v=$(sha256sum < "$UD/docker@.service" | cut -c1-16)

# A runner is busy while a Runner.Worker (uid 201000 once jobs run as runner) has the runner's engine
# shim as an ancestor; the shim's -address names /run/user/<gh-runner>/e-<instance>/.
busy=" "
for w in $(pgrep -f 'bin/Runner.Worker'); do
  p=$w
  while [ "${p:-1}" -gt 1 ]; do
    a=$(ps -o args= -p "$p")
    if [[ $a == *containerd-shim* ]]; then
      i=$(grep -oE "/run/user/$(id -u)/e-[A-Za-z0-9_.-]+/" <<<"$a" | head -1 | sed -E 's#.*/e-##; s#/$##')
      [ -n "$i" ] && busy+="$i "
      break
    fi
    p=$(ps -o ppid= -p "$p" | tr -d ' ')
  done
done

for u in $(systemctl --user list-units --all --plain --no-legend 'ci-runner@*' | awk '{print $1}'); do
  i=${u#ci-runner@}; i=${i%.service}
  { read -r have_r have_e < "$CR/applied/$i"; } 2>/dev/null || { have_r=""; have_e=""; }
  [ "$have_r $have_e" = "$runner_v $engine_v" ] && continue
  if [[ $busy == *" $i "* ]]; then log "$i has a job: restart later"; continue; fi
  # entrypoint.sh's job-started hook: a job is running even when the process check above misses it.
  if [ -e "$CR/work/$i/.job-running" ]; then log "$i has a job (marker): restart later"; continue; fi
  # A job the runner takes in the moment between the check above and the restart is still lost.
  if [ "$have_e" != "$engine_v" ]; then systemctl --user restart "docker@$i.service" || { log "FAIL restart docker@$i"; continue; }; fi
  systemctl --user restart "$u" || { log "FAIL restart $u"; continue; }
  echo "$runner_v $engine_v" > "$CR/applied/$i"
  log "$i restarted (idle) at runner $runner_v engine $engine_v"
done

# Each runner's disk, as its last start measured it (entrypoint.sh ci_disk writes cache/<i>/.sizes), for
# x3-host.sh to push: the log folder is the one place both gh-runner and the operator's account reach.
{ for f in "$CR"/cache/*/.sizes; do
    [ -r "$f" ] || continue
    i=$(basename "$(dirname "$f")")
    awk -v i="$i" '{ printf "x3_ci_runner_%s{box=\"x3\",runner=\"%s\"} %s\n", $1, i, $2 }' "$f"
  done; } > "$SRC/log/ci-sizes.prom.tmp" 2>/dev/null && mv "$SRC/log/ci-sizes.prom.tmp" "$SRC/log/ci-sizes.prom"
exit 0
