#!/usr/bin/env bash
# long-job — run a long command detached from the agent's tool call, with a log
# that ends in an EXIT= line, a PID file, and a lock so a second job writing the
# same thing can't start. See ../SKILL.md.
#
#   long-job.sh start <name> [--lock <key>] [--cwd <dir>] -- <command …>
#   long-job.sh status <name>      # running | finished EXIT=<n> | unknown
#   long-job.sh tail <name> [n]    # last n log lines (default 20)
#   long-job.sh stop <name>        # stops ONLY this job's process group
#   long-job.sh list               # jobs in the state dir
#
# State: ${LONG_JOB_DIR:-${XDG_STATE_HOME:-$HOME/.local/state}/long-job}/<name>.{log,pid,cmd}
# Locks: <state>/locks/<key>.lock (default key = name). A lock is free when its
# owner PID is gone, so a crashed job never blocks the next one.
set -euo pipefail

STATE="${LONG_JOB_DIR:-${XDG_STATE_HOME:-$HOME/.local/state}/long-job}"
mkdir -p "$STATE/locks"

die() { echo "long-job: $*" >&2; exit 2; }
alive() { [ -n "${1:-}" ] && kill -0 "$1" 2>/dev/null; }
valid_name() { [[ "$1" =~ ^[A-Za-z0-9._-]+$ ]] || die "name must be [A-Za-z0-9._-]+ (got '$1')"; }

cmd="${1:-}"; shift || true
case "$cmd" in
  start)
    name="${1:-}"; shift || true
    [ -n "$name" ] || die "start needs a name"
    valid_name "$name"
    lock="$name"; cwd="$PWD"
    while [ "${1:-}" != "--" ] && [ $# -gt 0 ]; do
      case "$1" in
        --lock) lock="$2"; valid_name "$lock"; shift 2 ;;
        --cwd) cwd="$2"; shift 2 ;;
        *) die "unknown option $1 (put the command after --)" ;;
      esac
    done
    [ "${1:-}" = "--" ] || die "missing -- before the command"
    shift
    [ $# -gt 0 ] || die "no command given"
    lockf="$STATE/locks/$lock.lock"
    if [ -f "$lockf" ]; then
      owner="$(cut -d' ' -f1 "$lockf")"; holder="$(cut -d' ' -f2- "$lockf")"
      if alive "$owner"; then die "lock '$lock' is held by running job '$holder' (pid $owner) — refusing to start a second writer"; fi
    fi
    if [ -f "$STATE/$name.pid" ] && alive "$(cat "$STATE/$name.pid")"; then
      die "job '$name' is already running (pid $(cat "$STATE/$name.pid"))"
    fi
    log="$STATE/$name.log"
    printf '%q ' "$@" > "$STATE/$name.cmd"
    : > "$log"
    # Own process group (pgid == pid, so `stop` can signal the whole job), surviving the tool call;
    # the wrapper writes EXIT=. setsid is Linux-only: macOS has none ("setsid: command not found"
    # killed every job there while `start` still reported success), so use perl's setpgrp + exec.
    if command -v setsid >/dev/null 2>&1; then newpg=(setsid)
    elif command -v perl >/dev/null 2>&1; then newpg=(perl -e 'setpgrp(0, 0) or die "setpgrp: $!"; exec @ARGV or die "exec: $!"')
    else die "need setsid (Linux) or perl (macOS) to give the job its own process group"; fi
    (
      cd "$cwd"
      "${newpg[@]}" bash -c '
        echo "[long-job] start $(date -u +%FT%TZ) in $PWD: $*"
        "$@"
        rc=$?
        echo "[long-job] end $(date -u +%FT%TZ)"
        echo "EXIT=$rc"
      ' long-job "$@" >> "$log" 2>&1 < /dev/null &
      echo $! > "$STATE/$name.pid"
    )
    pid="$(cat "$STATE/$name.pid")"
    # A job that is gone a second later without an EXIT= line never started (a missing launcher,
    # a bad cwd): say so instead of "started".
    sleep 1
    if ! alive "$pid" && ! grep -q '^EXIT=' "$log"; then
      die "job '$name' died at once without an EXIT= line; log $log: $(tail -3 "$log" | tr '\n' ' ')"
    fi
    echo "$pid $name" > "$lockf"
    echo "started '$name' pid $pid (pgid $pid), lock '$lock'"
    echo "log: $log"
    echo "monitor (Monitor tool command; it ends when the job's process exits):"
    if tail --version 2>/dev/null | grep -q GNU; then
      echo "  tail -n +1 -F --pid=$pid '$log' | grep -E --line-buffered 'EXIT=|Error|error|FAIL|✗'"
    else
      # BSD tail (macOS) has no --pid: poll the log until the EXIT= line appears.
      echo "  n=0; until grep -q '^EXIT=' '$log'; do c=\$(wc -l < '$log'); [ \$c -gt \$n ] && sed -n \"\$((n+1)),\${c}p\" '$log' | grep -E 'Error|error|FAIL|✗'; n=\$c; sleep 5; done; grep '^EXIT=' '$log'"
    fi
    echo "wait (Bash run_in_background, one notification):"
    echo "  until grep -q '^EXIT=' '$log'; do sleep 10; done; tail -20 '$log'"
    ;;
  status)
    name="${1:-}"; valid_name "$name"
    log="$STATE/$name.log"; [ -f "$log" ] || { echo unknown; exit 1; }
    if grep -q '^EXIT=' "$log"; then echo "finished $(grep '^EXIT=' "$log" | tail -1)";
    elif alive "$(cat "$STATE/$name.pid" 2>/dev/null)"; then echo running;
    else echo "dead (no EXIT= line — killed or crashed)"; fi
    ;;
  tail)
    name="${1:-}"; valid_name "$name"; tail -n "${2:-20}" "$STATE/$name.log" ;;
  stop)
    name="${1:-}"; valid_name "$name"
    pid="$(cat "$STATE/$name.pid" 2>/dev/null || true)"
    alive "$pid" || { echo "job '$name' is not running"; exit 0; }
    # Only this job's process group (setsid made pgid == pid).
    ps -o pid=,pgid=,args= -g "$pid" | sed 's/^/  stopping: /'
    kill -TERM -- "-$pid" 2>/dev/null || true
    for _ in 1 2 3 4 5 6 7 8 9 10; do alive "$pid" || break; sleep 1; done
    alive "$pid" && kill -KILL -- "-$pid" 2>/dev/null || true
    echo "EXIT=stopped" >> "$STATE/$name.log"
    echo "stopped '$name'"
    ;;
  list)
    for p in "$STATE"/*.pid; do
      [ -e "$p" ] || continue
      n="$(basename "$p" .pid)"
      printf '%-30s %s\n' "$n" "$("$0" status "$n" 2>/dev/null || true)"
    done
    ;;
  *) sed -n '2,15p' "$0"; exit 2 ;;
esac
