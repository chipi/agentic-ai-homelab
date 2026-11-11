#!/usr/bin/env bash
# tmp-sweep.sh — remove what agents and test runs leave in /tmp (the workstation's /tmp is a tmpfs
# with a fixed inode count; it filled to 97% on 2026-11-11 and new files failed).
#
#   tmp-sweep.sh --session <session-id>   that session's scratchpad: /tmp/claude-<uid>/<project>/<id>
#                                         (session-reap.sh calls it at SessionEnd)
#   tmp-sweep.sh --daily                  older than TMP_SWEEP_MAX_AGE_H (default 48 h), per path:
#                                         - /tmp/pytest-of-<user>/pytest-N, except the 3 newest and
#                                           the one pytest-current points at
#                                         - /tmp/*-tests-* folders (TemporaryDirectory leftovers of
#                                           killed test runs)
#                                         - session scratchpads /tmp/claude-<uid>/<project>/<uuid>
#                                           (a session that ended without the hook), except in a
#                                           project where a live Claude holds no scratchpad open
#                                         - loose files directly in /tmp/claude-<uid>
#
# SAFETY — every removal needs all of: owned by this user; the newest file in it older than the
# age floor (--daily); no process has its cwd or an open file inside it, except the processes
# that called this script (at SessionEnd the ending session's own Claude still holds its files);
# for --session, a session id of uuid shape and a path exactly /tmp/claude-<uid>/<one dir>/<id>.
# Claude Code's own folders directly under /tmp/claude-<uid> (bash-edit-diff, bundled-skills, ...)
# are never touched. Each removal is logged.
#
# Env: TMP_SWEEP_DRY_RUN=1 -> print and log, remove nothing.
#      TMP_SWEEP_MAX_AGE_H -> the age floor in hours for --daily (default 48).
#      TMP_SWEEP_ROOT      -> the /tmp to sweep (tests).
set -u
cd / || exit 0   # its own subshells must not sit in a folder it judges (they inherit the cwd)
ROOT="${TMP_SWEEP_ROOT:-/tmp}"
ROOT="${ROOT%/}"
UIDN="$(id -u)"; ME="$(id -un)"
CROOT="$ROOT/claude-$UIDN"
DRY="${TMP_SWEEP_DRY_RUN:-0}"
MAXH="${TMP_SWEEP_MAX_AGE_H:-48}"
LOG="$HOME/.claude/hooks/tmp-sweep.log"
mkdir -p "$(dirname "$LOG")"
ts="$(date '+%Y-%m-%d %H:%M:%S')"
UUID_RE='^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
[ -d /proc/self/fd ] || { echo "$ts SKIP no /proc (Linux only)" >>"$LOG"; exit 0; }

# this script's ancestors: at SessionEnd the ending session's Claude holds files in its own
# scratchpad, which must not count as "in use"
SKIP=" "
p=$$
while [[ "$p" =~ ^[0-9]+$ ]] && [ "$p" -gt 1 ]; do
  SKIP="$SKIP$p "
  st="$(cat "/proc/$p/stat" 2>/dev/null)"   # pid (comm) state ppid …; comm may hold spaces
  st="${st##*) }"
  p="$(printf '%s' "$st" | awk '{print $2}')"
done

OPEN=""
open_paths() {   # every cwd and open file of every process of ours, except our ancestors
  local d pid
  for d in /proc/[0-9]*; do
    pid="${d#/proc/}"
    case "$SKIP" in *" $pid "*) continue ;; esac
    [ -O "$d" ] || continue
    readlink "$d/cwd" 2>/dev/null
    for f in "$d"/fd/*; do readlink "$f" 2>/dev/null; done
  done
}
in_use() { printf '%s\n' "$OPEN" | grep -q -F -- "$1/" || printf '%s\n' "$OPEN" | grep -q -x -F -- "$1"; }
# A live Claude normally holds its own scratchpad open (its tasks/ folder). One that holds none
# (seen on 2026-11-11 for 4 of 18) gives no way to tell which scratchpad is its, so every
# scratchpad of its project folder is kept: the folder is the cwd with each non-alphanumeric as '-'.
held_projects() {
  local d pid cwd
  for d in /proc/[0-9]*; do
    pid="${d#/proc/}"
    [ -O "$d" ] && [ "$(cat "$d/comm" 2>/dev/null)" = claude ] || continue
    holds=0
    for f in "$d"/fd/*; do case "$(readlink "$f" 2>/dev/null)" in "$CROOT"/*) holds=1; break ;; esac; done
    [ "$holds" = 1 ] && continue
    cwd="$(readlink "$d/cwd" 2>/dev/null)" || continue
    printf '%s\n' "${cwd//[^[:alnum:]]/-}"
  done
}
age_h() {   # hours since the newest change inside $1 (a file: its own)
  local newest
  newest="$(find "$1" -xdev -printf '%T@\n' 2>/dev/null | sort -n | tail -1)"
  echo $(( ( $(date +%s) - ${newest%.*} ) / 3600 ))
}
removed=0; kept=0
remove() {   # path reason
  local p="$1"
  [ -O "$p" ] || { echo "$ts KEEP not ours: $p" >>"$LOG"; kept=$((kept+1)); return; }
  if in_use "$p"; then echo "$ts KEEP in use: $p" >>"$LOG"; kept=$((kept+1)); return; fi
  echo "$ts REMOVE ($2): $p" >>"$LOG"
  if [ "$DRY" = 1 ]; then echo "[dry-run] would remove ($2): $p"; else rm -rf -- "$p"; fi
  removed=$((removed+1))
}

case "${1:-}" in
  --session)
    id="${2:-}"
    [[ "$id" =~ $UUID_RE ]] || { echo "$ts SKIP session id not a uuid: '$id'" >>"$LOG"; exit 0; }
    OPEN="$(open_paths)"
    for d in "$CROOT"/*/"$id"; do
      [ -d "$d" ] && [ ! -L "$d" ] && remove "$d" "session ended"
    done
    ;;
  --daily)
    OPEN="$(open_paths)"
    if [ -d "$ROOT/pytest-of-$ME" ]; then
      cur="$(readlink "$ROOT/pytest-of-$ME/pytest-current" 2>/dev/null)"
      newest3="$(for d in "$ROOT/pytest-of-$ME"/pytest-[0-9]*; do [ -d "$d" ] && printf '%s\t%s\n' "${d##*/pytest-}" "$d"; done \
        | sort -n | tail -3 | cut -f2)"
      for d in "$ROOT/pytest-of-$ME"/pytest-[0-9]*; do
        [ -d "$d" ] || continue
        [ "$d" = "$cur" ] && continue
        printf '%s\n' "$newest3" | grep -q -x -F -- "$d" && continue
        [ "$(age_h "$d")" -ge "$MAXH" ] && remove "$d" "pytest, $(age_h "$d") h"
      done
    fi
    for d in "$ROOT"/*-tests-*; do
      [ -d "$d" ] && [ ! -L "$d" ] || continue
      [ "$(age_h "$d")" -ge "$MAXH" ] && remove "$d" "test leftover, $(age_h "$d") h"
    done
    HELD="$(held_projects)"
    for d in "$CROOT"/*/*; do
      [ -d "$d" ] && [ ! -L "$d" ] || continue
      [[ "$(basename "$d")" =~ $UUID_RE ]] || continue
      proj="$(basename "$(dirname "$d")")"
      if printf '%s\n' "$HELD" | grep -q -x -F -- "$proj"; then
        echo "$ts KEEP a live Claude in $proj holds no scratchpad: $d" >>"$LOG"; kept=$((kept+1)); continue
      fi
      [ "$(age_h "$d")" -ge "$MAXH" ] && remove "$d" "session scratchpad, $(age_h "$d") h"
    done
    for f in "$CROOT"/*; do
      [ -f "$f" ] && [ ! -L "$f" ] || continue
      [ "$(age_h "$f")" -ge "$MAXH" ] && remove "$f" "loose file, $(age_h "$f") h"
    done
    ;;
  *) echo "usage: tmp-sweep.sh --session <id> | --daily" >&2; exit 2 ;;
esac
echo "$ts tmp-sweep ${1}: removed $removed, kept $kept (dry=$DRY)" >>"$LOG"
echo "tmp-sweep ${1}: removed $removed, kept $kept$([ "$DRY" = 1 ] && echo ' (dry run)')"
