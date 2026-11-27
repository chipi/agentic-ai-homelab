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
# shim as an ancestor; the shim's -address names /run/user/<gh-runner>/e-<instance>/. Asked for each runner
# just before its restart, not once for all: a snapshot taken before the loop was 6 and 11 s old when
# player-1 and player-3 were restarted, both had taken a job meanwhile, and GitHub ended the two jobs with
# "A task was canceled." (10:04:21Z, 2026-11-27).
busy() {
  local w p a i
  for w in $(pgrep -f 'bin/Runner.Worker'); do
    p=$w
    while [ "${p:-1}" -gt 1 ]; do
      a=$(ps -o args= -p "$p")
      if [[ $a == *containerd-shim* ]]; then
        i=$(grep -oE "/run/user/$(id -u)/e-[A-Za-z0-9_.-]+/" <<<"$a" | head -1 | sed -E 's#.*/e-##; s#/$##')
        [ "$i" = "$1" ] && return 0
        break
      fi
      p=$(ps -o ppid= -p "$p" | tr -d ' ')
    done
  done
  return 1
}

for u in $(systemctl --user list-units --all --plain --no-legend 'ci-runner@*' | awk '{print $1}'); do
  i=${u#ci-runner@}; i=${i%.service}
  { read -r have_r have_e < "$CR/applied/$i"; } 2>/dev/null || { have_r=""; have_e=""; }
  [ "$have_r $have_e" = "$runner_v $engine_v" ] && continue
  if busy "$i"; then log "$i has a job: restart later"; continue; fi
  # A container lives for one job and takes the new files at its next start anyway; a restart is only for a
  # runner that sits idle on old files. A container started under 10 minutes ago is skipped: player-1's
  # started at 19:17:45Z, GitHub gave it a job at 19:17:51Z, and this loop restarted it as idle at 19:18:44Z
  # (neither check above saw the job), so GitHub lost the job 10 minutes later (player #60, 2026-11-27).
  # A job holding or waiting for a job slot (entrypoint.sh) is a job, whatever the checks above saw.
  if [ -e "$CR/slots/wait/x3-$i" ] || grep -qs "^x3-$i " "$CR"/slots/[rs]-*/owner; then log "$i holds or waits for a job slot: restart later"; continue; fi
  st=$(awk '$1 == "measured_at" { print $2 }' "$CR/cache/$i/.sizes" 2>/dev/null)
  if [ -n "$st" ] && [ $(( $(date +%s) - st )) -lt 600 ]; then continue; fi
  # entrypoint.sh's job-started hook: a job is running even when the process check above misses it.
  if [ -e "$CR/work/$i/.job-running" ]; then log "$i has a job (marker): restart later"; continue; fi
  # A job the runner takes in the moment between these checks and the restart (well under a second) is still lost.
  if [ "$have_e" != "$engine_v" ]; then systemctl --user restart "docker@$i.service" || { log "FAIL restart docker@$i"; continue; }; fi
  systemctl --user restart "$u" || { log "FAIL restart $u"; continue; }
  echo "$runner_v $engine_v" > "$CR/applied/$i"
  log "$i restarted (idle) at runner $runner_v engine $engine_v"
done

# A runner GitHub shows offline while it runs here: on 2026-11-27 the home line dropped for a minute or two
# at 02:29Z (every runner's broker poll timed out; the mini's egress probe failed at 02:30Z), GitHub showed the
# runners offline 02:31-02:35Z, and then again for 20-25 minutes from about 03:01Z, while gh-runner's journal
# shows them polling without an error (operator's go for this fix the same day). A restart opens a new session. Read from VictoriaMetrics, where the mini's
# collector writes GitHub's view every 5 minutes (gh_runner_up): offline in every sample of the last 10
# minutes, with 2 or more samples (a stale collector is no evidence), the unit up for 15 minutes (a runner
# just started has not shown up yet), idle, and not healed in the last 30 minutes. No answer from
# VictoriaMetrics means no restart.
VMQ=${CI_RUNNER_VM_QUERY:-https://vm.tail6d0ed4.ts.net/api/v1/query}
offline=$(curl -s -m10 "$VMQ" --data-urlencode 'query=(max by (runner) (max_over_time(gh_runner_up{machine="x3"}[10m])) == 0) and on (runner) (count_over_time(gh_runner_up{machine="x3"}[10m]) >= 2)' 2>/dev/null \
  | jq -r '.data.result[]?.metric.runner' 2>/dev/null)
for r in $offline; do
  i=${r#x3-}; u="ci-runner@$i.service"
  systemctl --user is-active -q "$u" || continue
  up=$(date -d "$(systemctl --user show -p ActiveEnterTimestamp --value "$u")" +%s 2>/dev/null || echo "$(date +%s)")
  [ $(( $(date +%s) - up )) -ge 900 ] || continue
  h="$CR/applied/$i.heal"
  [ -f "$h" ] && [ $(( $(date +%s) - $(cat "$h") )) -lt 1800 ] && continue
  if busy "$i" || [ -e "$CR/work/$i/.job-running" ]; then log "$i offline on GitHub for 10 min but has a job: no restart"; continue; fi
  systemctl --user restart "$u" || { log "FAIL restart $u (offline on GitHub)"; continue; }
  date +%s > "$h"
  log "$i restarted: GitHub showed it offline for 10 min while it ran here"
done

# When each runner's engine last ran each image: Docker records no last use, and entrypoint.sh's pruning
# needs one for the agreed rule (an image no job ran for 7 days goes; operator, 2026-11-27). Every 2 minutes,
# the images of the engine's running containers get the time now in cache/<i>/.image-seen ("<image id>
# <unix s>" lines). A container that lives under 2 minutes can be missed; its image then counts from its
# pull, and at worst is pulled again.
now=$(date +%s)
for s in /run/user/"$(id -u)"/e-*/docker.sock; do
  [ -S "$s" ] || continue
  i=${s%/docker.sock}; i=${i##*/e-}
  f="$CR/cache/$i/.image-seen"
  [ -d "$CR/cache/$i" ] || continue
  ids=$(DOCKER_HOST="unix://$s" timeout 20 docker ps -q 2>/dev/null | xargs -r env DOCKER_HOST="unix://$s" timeout 20 docker inspect -f '{{.Image}}' 2>/dev/null | sort -u)
  [ -n "$ids" ] || continue
  { [ -f "$f" ] && awk -v ids="$ids" 'BEGIN { n = split(ids, a, "\n"); for (k = 1; k <= n; k++) run[a[k]] = 1 } !($1 in run)' "$f"
    for id in $ids; do echo "$id $now"; done; } > "$f.tmp" && mv "$f.tmp" "$f"
done

# Job slots (entrypoint.sh, RFC-0011 item 26). A runner frees its own slot at its next start; a slot whose
# runner unit is no longer active (a runner removed, or stopped for good) is freed here.
SL="$CR/slots"
if [ -d "$SL" ]; then
  for o in "$SL"/*/owner; do
    [ -f "$o" ] || continue
    r=$(cut -d' ' -f1 "$o"); i=${r#x3-}
    systemctl --user is-active -q "ci-runner@$i.service" && continue
    rm -rf "$(dirname "$o")" && log "freed job slot $(basename "$(dirname "$o")") of $r (ci-runner@$i is not active)"
  done
fi

# Each runner's disk, as its last start measured it (entrypoint.sh ci_disk writes cache/<i>/.sizes), for
# x3-host.sh to push: the log folder is the one place both gh-runner and the operator's account reach.
{ if [ -d "$SL" ]; then
    now=$(date +%s); held=0; waiting=0; oldest=0
    for d in "$SL"/[rs]-*; do
      [ -d "$d" ] || continue
      held=$((held + 1))
      printf 'x3_ci_slot_held{box="x3",slot="%s",runner="%s"} 1\n' "$(basename "$d")" "$(cut -d' ' -f1 "$d/owner" 2>/dev/null)"
    done
    for w in "$SL"/wait/*; do
      [ -f "$w" ] || continue
      waiting=$((waiting + 1)); a=$(( now - $(cat "$w") )); [ "$a" -gt "$oldest" ] && oldest=$a
    done
    repos=$(systemctl --user list-units --all --plain --no-legend 'ci-runner@*' | awk '{print $1}' | sed -E 's/^ci-runner@(.*)-[0-9]+\.service$/\1/' | sort -u | wc -l)
    shared=$(grep -oE 'CI_SLOTS_SHARED=[0-9]+' "$UD/ci-runner@.service" | head -1 | cut -d= -f2)
    printf 'x3_ci_slots_held{box="x3"} %d\nx3_ci_slots_total{box="x3"} %d\n' "$held" "$(( repos + ${shared:-0} ))"
    printf 'x3_ci_jobs_waiting_for_slot{box="x3"} %d\nx3_ci_slot_wait_oldest_seconds{box="x3"} %d\n' "$waiting" "$oldest"
  fi
  for f in "$CR"/cache/*/.sizes; do
    [ -r "$f" ] || continue
    i=$(basename "$(dirname "$f")")
    awk -v i="$i" '{ printf "x3_ci_runner_%s{box=\"x3\",runner=\"%s\"} %s\n", $1, i, $2 }' "$f"
    s="$(dirname "$f")/.image-seen"
    [ -r "$s" ] && printf 'x3_ci_runner_images_seen{box="x3",runner="%s"} %d\n' "$i" "$(wc -l < "$s")"
  done; } > "$SRC/log/ci-sizes.prom.tmp" 2>/dev/null && mv "$SRC/log/ci-sizes.prom.tmp" "$SRC/log/ci-sizes.prom"
exit 0
