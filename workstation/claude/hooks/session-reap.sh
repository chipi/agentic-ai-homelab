#!/usr/bin/env bash
# session-reap.sh — SessionEnd cleanup: kill processes THIS session spawned in THIS
# worktree, so the machine returns to its pre-session state. Wired into the SessionEnd
# hook (see ~/.claude/settings.json).
#
# SAFETY — the scope is two ANDs, never one:
#   1. the process CWD is UNDER the session's project dir (never another worktree), AND
#   2. it is a session TOOL process (this worktree's .venv python, node/playwright,
#      ffmpeg, dev servers) — not an interactive shell, editor, MCP server, or Claude.
# A process in another podcast_scraper-* worktree can never match (gate #1), honoring
# the never-touch-other-worktrees rule. Every candidate is logged for audit.
#
# STALE-LOOP SWEEP — runaway agent poll loops (`while true; do gh run …; sleep; done`)
# leak when the session that spawned them dies without this hook firing: they are then
# orphaned in a SIBLING worktree no future SessionEnd targets, so the per-worktree gate
# above can never reach them (seen in the wild: 3 such loops surviving 8-14 days). They
# are swept here across sibling worktrees — but scoped to THIS session's PROJECT FAMILY
# (project-name prefix, see family_prefix), never other projects: an orrery session
# reaps only orrery-family loops, a podcast session only podcast-family loops. Safety
# is the stack: same-family CWD AND `gh run` AND an unbounded while/until loop AND
# age >= MAX_LOOP_AGE — a live watch (exits in minutes) can't match. Tune/disable below.
#
# ORPHAN-WATCHER SWEEP — leaked `tail -f <file> | grep …` watchers whose session (and
# file) are gone; same family scoping, gates documented at the sweep below.
#
# Env: SESSION_REAP_DRY_RUN=1     -> log + print targets, kill nothing.
#      SESSION_REAP_MAX_LOOP_AGE  -> stale-loop age floor in seconds (default 7200 = 2h).
#      SESSION_REAP_NO_LOOP_SWEEP=1 -> skip the stale-loop sweep entirely.
#      SESSION_REAP_MAX_WATCH_AGE -> orphan-watcher age floor in seconds (default 7200 = 2h).
#      SESSION_REAP_NO_WATCH_SWEEP=1 -> skip the orphan-watcher sweep entirely.
set -u

PROJECT_DIR="${1:-${CLAUDE_PROJECT_DIR:-$PWD}}"
PROJECT_DIR="${PROJECT_DIR%/}"
DRY="${SESSION_REAP_DRY_RUN:-0}"
LOG="$HOME/.claude/hooks/session-reap.log"
SELF=$$
ts="$(date '+%Y-%m-%d %H:%M:%S')"
echo "== $ts session-reap start project=$PROJECT_DIR dry=$DRY ==" >>"$LOG"

# ps etime ([[dd-]hh:]mm:ss) -> elapsed seconds (macOS BSD ps has no `etimes`).
# `10#` on every field: ps zero-pads (08, 09) which bash arithmetic reads as octal.
etime_secs() {
  local e="$1" d=0 hms
  [ -z "$e" ] && { echo 0; return; }
  case "$e" in *-*) d="${e%%-*}"; hms="${e#*-}" ;; *) hms="$e" ;; esac
  local IFS=:; set -- $hms
  case $# in
    3) echo $(( 10#$d*86400 + 10#$1*3600 + 10#$2*60 + 10#$3 )) ;;
    2) echo $(( 10#$d*86400 + 10#$1*60 + 10#$2 )) ;;
    *) echo $(( 10#$d*86400 + 10#${1:-0} )) ;;
  esac
}

# Family prefix for a project path: $HOME/<container>/<base>, where <base> is the
# instance dir name up to its first '-'.  ~/.treehouse/orrery-311982/1/orrery and
# ~/.treehouse/orrery-fixes-311982/... both -> ~/.treehouse/orrery (one family);
# ~/Projects/podcast_scraper-ai-ml -> ~/Projects/podcast_scraper. Generic (not
# treehouse-specific): any $HOME/<container>/<instance>/... layout. Empty if the
# path is too shallow to name a family (then the sweep is skipped — fail safe).
#
# Model-B (the Linux workstation): /work/<project>/{main,worktrees/<stream>} -> "/work/<project>/".
# The trailing slash is the boundary: /work/orrery/ never matches /work/orrery2.
# WB_WORK_ROOT overrides /work (tests), as in the wb-* tools.
family_prefix() {
  local p="${1%/}" rel container instance root="${WB_WORK_ROOT:-/work}"
  root="${root%/}"
  case "$p" in "$root"/?*) rel="${p#"$root"/}"; echo "$root/${rel%%/*}/"; return ;; esac
  case "$p" in "$HOME"/*/*) : ;; *) echo ""; return ;; esac
  rel="${p#"$HOME"/}"; container="${rel%%/*}"; rel="${rel#*/}"; instance="${rel%%/*}"
  echo "$HOME/$container/${instance%%-*}"
}

# ── Stale agent poll-loops (family-scoped, shape + age gated) ────────────────
# Runs BEFORE the per-worktree gates below: these orphans live in sibling worktrees
# no future SessionEnd targets. Scoped to the SAME project family as this session
# (project-name prefix — see family_prefix), so an orrery session never reaps a
# podcast loop and vice-versa. Safety is the stack: same-family CWD AND a `gh run …`
# call AND an unbounded while/until loop AND age >= floor. A live watch (exits in
# minutes), the lean-ctx MCP server, and any other project can't match; a runaway
# loop's lean-ctx wrapper does (its cmdline carries the loop body), so both die.
MAX_LOOP_AGE="${SESSION_REAP_MAX_LOOP_AGE:-7200}"   # 2h
FAMILY="$(family_prefix "$PROJECT_DIR")"
loops=0
if [ "${SESSION_REAP_NO_LOOP_SWEEP:-0}" != "1" ] && [ -n "$FAMILY" ]; then
  for pid in $(pgrep -f 'gh run ' 2>/dev/null); do
    [ "$pid" = "$SELF" ] && continue
    cmd="$(ps -p "$pid" -o command= 2>/dev/null)"
    [ -z "$cmd" ] && continue
    case "$cmd" in *"while true"* | *"until "*) : ;; *) continue ;; esac   # unbounded loop only
    age="$(etime_secs "$(ps -p "$pid" -o etime= 2>/dev/null | tr -d ' ')")"
    [ "${age:-0}" -ge "$MAX_LOOP_AGE" ] || continue                        # young = maybe a live watch
    cwd="$(lsof -p "$pid" -a -d cwd -Fn 2>/dev/null | sed -n 's/^n//p' | head -1)"
    case "$cwd" in "$FAMILY" | "$FAMILY"*) : ;; *) continue ;; esac        # same project family only
    echo "$ts REAP-LOOP pid=$pid age=${age}s cwd=$cwd cmd=${cmd:0:180}" >>"$LOG"
    loops=$((loops + 1))
    if [ "$DRY" = "1" ]; then
      printf '[dry-run] would reap loop pid=%-7s age=%ss %s\n' "$pid" "$age" "${cmd:0:80}"
    else
      kill -TERM "$pid" 2>/dev/null || true
      ( sleep 3; kill -KILL "$pid" 2>/dev/null ) >/dev/null 2>&1 &
    fi
  done
fi
echo "$ts stale-loop sweep (family=${FAMILY:-none}): $loops loop(s)" >>"$LOG"
[ "$loops" -gt 0 ] && { [ "$DRY" = "1" ] && echo "[dry-run] $loops stale-loop(s); killed nothing" || echo "swept $loops stale-loop(s)"; }

# ── Orphaned follow-watchers (family-scoped, Linux /proc) ─────────────────────
# A backgrounded watch such as `tail -f <task-output> | grep 'FAIL|error'` outlives the
# session that started it: the session's scratch file is deleted, the pipeline is
# reparented to init, and it waits forever (seen on the X3: 14 days). Safety is the stack:
# `tail` following with -f/-F/--follow AND orphaned (parent is pid 1 or a systemd manager)
# AND EVERY file it follows is deleted AND age >= MAX_WATCH_AGE AND same-family CWD. A live
# watch has a live parent and a live file. Its pipeline partners (same process group, also
# orphaned, not a shell/agent/editor) go with it; nothing outside that group is touched.
MAX_WATCH_AGE="${SESSION_REAP_MAX_WATCH_AGE:-7200}"   # 2h
watchers=0
orphaned() { local pp; pp="$(ps -o ppid= -p "$1" 2>/dev/null | tr -d ' ')"; [ "$pp" = 1 ] || [ "$(ps -o comm= -p "${pp:-0}" 2>/dev/null)" = systemd ]; }
follows_only_deleted() {   # every regular file the tail has open is gone
  local f t n=0 gone=0
  for f in /proc/"$1"/fd/*; do
    t="$(readlink "$f" 2>/dev/null)" || continue
    case "$t" in /dev/* | pipe:* | socket:* | anon_inode:* | /proc/*) continue ;; esac
    n=$((n + 1)); case "$t" in *" (deleted)") gone=$((gone + 1)) ;; esac
  done
  [ "$n" -gt 0 ] && [ "$gone" = "$n" ]
}
if [ "${SESSION_REAP_NO_WATCH_SWEEP:-0}" != "1" ] && [ -n "$FAMILY" ] && [ -d /proc/self/fd ]; then
  for pid in $(pgrep -x tail 2>/dev/null); do
    [ "$pid" = "$SELF" ] && continue
    cmd="$(ps -p "$pid" -o command= 2>/dev/null)"
    # follow flag: -f / -F, inside a short-flag cluster (-nf, -fq), or --follow[=…]
    [[ " $cmd " =~ \ -[a-zA-Z]*[fF][a-zA-Z]*\  ]] || [[ " $cmd " == *" --follow"* ]] || continue
    orphaned "$pid" || continue
    follows_only_deleted "$pid" || continue
    age="$(etime_secs "$(ps -p "$pid" -o etime= 2>/dev/null | tr -d ' ')")"
    [ "${age:-0}" -ge "$MAX_WATCH_AGE" ] || continue
    cwd="$(readlink "/proc/$pid/cwd" 2>/dev/null)"
    case "$cwd" in "$FAMILY" | "$FAMILY"*) : ;; *) continue ;; esac
    pgid="$(ps -o pgid= -p "$pid" 2>/dev/null | tr -d ' ')"
    group="$pid"
    for q in $(pgrep -g "$pgid" 2>/dev/null); do
      [ "$q" = "$pid" ] || [ "$q" = "$SELF" ] && continue
      orphaned "$q" || continue
      qc="$(ps -p "$q" -o command= 2>/dev/null)"
      case "$qc" in "" | *claude\ * | claude | *lean-ctx* | *mcp* | */bash | -bash | */zsh | -zsh | bash* | zsh* | *vim* | *emacs*) continue ;; esac
      group="$group $q"
    done
    for q in $group; do
      echo "$ts REAP-WATCH pid=$q group=$pgid age=${age}s cwd=$cwd cmd=$(ps -p "$q" -o command= 2>/dev/null | cut -c1-160)" >>"$LOG"
      watchers=$((watchers + 1))
      if [ "$DRY" = "1" ]; then
        printf '[dry-run] would reap watcher pid=%-7s age=%ss %s\n' "$q" "$age" "$(ps -p "$q" -o command= 2>/dev/null | cut -c1-80)"
      else
        kill -TERM "$q" 2>/dev/null || true
        ( sleep 3; kill -KILL "$q" 2>/dev/null ) >/dev/null 2>&1 &
      fi
    done
  done
fi
echo "$ts orphan-watcher sweep (family=${FAMILY:-none}): $watchers process(es)" >>"$LOG"
[ "$watchers" -gt 0 ] && { [ "$DRY" = "1" ] && echo "[dry-run] $watchers orphaned watcher process(es); killed nothing" || echo "swept $watchers orphaned watcher process(es)"; }

# Safety floor: refuse to run against a non-specific dir, so a bad CLAUDE_PROJECT_DIR
# can never widen the scope to everything under $HOME or /.
case "$PROJECT_DIR" in
  "" | "/" | "$HOME") echo "$ts ABORT unsafe PROJECT_DIR='$PROJECT_DIR'" >>"$LOG"; exit 0 ;;
esac
if [ ! -d "$PROJECT_DIR/.git" ] && [ ! -d "$PROJECT_DIR/.venv" ]; then
  # KNOWN LIMITATION: a git WORKTREE's .git is a FILE (gitdir pointer), so `-d`
  # aborts here and the per-worktree main reap below is a NO-OP for every worktree
  # session. Left as-is deliberately: flipping to `-e` would enable this hook to
  # kill dev servers (vite/preview) in worktrees on session end — including the
  # operator's persistent one — which violates the never-kill-the-dev-server rule.
  # The stale-loop sweep ABOVE runs before this gate, so orphaned loops are still
  # reaped regardless. Enabling worktree reap needs a dev-server exclusion first.
  echo "$ts ABORT '$PROJECT_DIR' is not a project worktree (no .git/.venv)" >>"$LOG"; exit 0
fi

# Candidate session-tool processes. The CWD gate below is the real safety scope; this
# pgrep only narrows the set. `pgrep -f` matches the whole command line.
cands="$(pgrep -f 'python|playwright|ffmpeg|uvicorn|vite|mkdocs serve|node .*stack-test|tail -[Ff]' 2>/dev/null || true)"

reaped=0
for pid in $cands; do
  [ "$pid" = "$SELF" ] && continue
  # Resolve the process CWD (macOS lsof). No CWD -> skip (can't scope safely).
  cwd="$(lsof -p "$pid" -a -d cwd -Fn 2>/dev/null | sed -n 's/^n//p' | head -1)"
  [ -z "$cwd" ] && continue
  # GATE 1: CWD must be inside THIS worktree, else never touch it.
  case "$cwd" in
    "$PROJECT_DIR" | "$PROJECT_DIR"/*) : ;;
    *) continue ;;
  esac
  cmd="$(ps -p "$pid" -o command= 2>/dev/null)"
  [ -z "$cmd" ] && continue
  # GATE 2 exclusions: never reap session infra, editors, or interactive shells.
  case "$cmd" in
    *claude* | *lean-ctx* | *mcp* | *Code\ Helper* | \
    *.vscode/extensions/* | *lsp_server.py* | *language-server* | \
    *" vim"* | *" nvim"* | *" emacs"* | */zsh | */bash | -zsh | -bash) continue ;;
  esac
  echo "$ts REAP pid=$pid cwd=$cwd cmd=${cmd:0:160}" >>"$LOG"
  reaped=$((reaped + 1))
  if [ "$DRY" = "1" ]; then
    printf '[dry-run] would reap  pid=%-7s %s\n' "$pid" "${cmd:0:90}"
  else
    kill -TERM "$pid" 2>/dev/null || true
    ( sleep 3; kill -KILL "$pid" 2>/dev/null ) >/dev/null 2>&1 &
  fi
done

echo "== $ts session-reap done: ${reaped} target(s), ${loops} stale-loop(s) ==" >>"$LOG"
if [ "$DRY" = "1" ]; then
  echo "[dry-run] $reaped tool target(s) + $loops stale-loop(s); killed nothing"
else
  echo "reaped $reaped process(es) + $loops stale-loop(s)"
fi
