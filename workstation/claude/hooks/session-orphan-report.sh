#!/usr/bin/env bash
# session-orphan-report.sh — SessionStart: REPORT (never kill) long-running processes in this
# project family that predate the current context. Wired into the SessionStart hook, which
# fires on `startup`, `resume`, AND `compact`.
#
# WHY THIS EXISTS — the gap session-reap.sh cannot cover.
# session-reap.sh runs on SessionEnd. A job started inside a session that simply keeps going is
# never reaped, and after a context compaction the agent holds NO record that it launched one.
# Incident 2026-09-19: an enrichment CLI ran 4d22h at 198% CPU on the operator's shared machine,
# burning 224.9 hours of CPU for ZERO bytes of output, across several compactions. Nothing
# surfaced it; the operator found it by hand and asked why it was still there.
#
# Detection fires exactly when the agent's context is empty — session start or post-compact —
# which is the one moment it would otherwise have no way to know.
#
# REPORT ONLY. It never signals anything. A long run is often legitimate (a real corpus pass, a
# model sweep), and SessionStart cannot tell a wanted 30h job from an abandoned one. Surfacing
# it is sufficient: the whole failure was that nobody was looking.
#
# THE TELL IS CPU-TIME, NOT LIVENESS. The runaway sat in STAT R at 198% and looked perfectly
# healthy. What gave it away was hours-of-CPU against zero bytes of output. So this reports
# elapsed AND cputime and lets the reader judge.
#
# SCOPE: same project FAMILY as session-reap.sh (family_prefix — ~/Projects/podcast_scraper-*
# is one family, orrery another), so an orrery session never reports podcast processes. Session
# infra (claude, lean-ctx, MCP servers, editors, shells) is excluded: those are meant to be
# long-lived and would otherwise fire on every single session start.
#
# TWO GATES, NOT ONE — age AND cpu-time. Age alone is useless: an idle MCP server sits at 20
# DAYS elapsed with 0m of CPU and is perfectly healthy infra. Reporting it every session is the
# noise that gets a check ignored, which is the same way the ingest-stalled alert became
# furniture. The runaway burned 224.9 HOURS of CPU. So the cpu floor is what actually separates
# "abandoned and eating the machine" from "long-lived and idle" — and an idle process costs
# nothing, so it is not what this hook is for.
#
# Env: ORPHAN_REPORT_MIN_AGE   age floor in seconds     (default 3600 = 1h)
#      ORPHAN_REPORT_MIN_CPU   cpu-time floor, seconds  (default 600 = 10m)
#      ORPHAN_REPORT_OFF=1     disable entirely
set -u

[ "${ORPHAN_REPORT_OFF:-0}" = "1" ] && exit 0

PROJECT_DIR="${1:-${CLAUDE_PROJECT_DIR:-$PWD}}"
PROJECT_DIR="${PROJECT_DIR%/}"
MIN_AGE="${ORPHAN_REPORT_MIN_AGE:-3600}"
MIN_CPU="${ORPHAN_REPORT_MIN_CPU:-600}"
SELF=$$

# Refuse to run against a non-specific dir — a bad CLAUDE_PROJECT_DIR must not widen scope.
case "$PROJECT_DIR" in "" | "/" | "$HOME") exit 0 ;; esac

# [[dd-]hh:]mm:ss -> seconds. `10#` on every field: ps zero-pads (08, 09), which bash
# arithmetic would otherwise read as octal and fail on. `%%.*` strips ps TIME's decimals.
hms_secs() {
  local e="$1" d=0 hms
  [ -z "$e" ] && { echo 0; return; }
  case "$e" in *-*) d="${e%%-*}"; hms="${e#*-}" ;; *) hms="$e" ;; esac
  local IFS=:
  # SC2086 is deliberate: IFS=':' plus word-splitting is HOW the hh:mm:ss fields become
  # $1/$2/$3. Quoting would pass the whole string as one arg and break the parse.
  # shellcheck disable=SC2086
  set -- $hms
  case $# in
    3) echo $(( 10#$d*86400 + 10#$1*3600 + 10#$2*60 + 10#${3%%.*} )) ;;
    2) echo $(( 10#$d*86400 + 10#$1*60 + 10#${2%%.*} )) ;;
    *) echo $(( 10#$d*86400 + 10#${1:-0} )) ;;
  esac
}

human() {  # seconds -> 4d22h / 03h07m / 12m
  local s="$1"
  if   [ "$s" -ge 86400 ]; then echo "$((s/86400))d$(( (s%86400)/3600 ))h"
  elif [ "$s" -ge 3600 ];  then printf '%dh%02dm\n' $((s/3600)) $(( (s%3600)/60 ))
  else echo "$((s/60))m"; fi
}

# Same family rule as session-reap.sh: $HOME/<container>/<instance>, instance truncated at its
# first '-'. ~/Projects/podcast_scraper-infra and -FUTURE share a family; orrery does not.
family_prefix() {
  local p="${1%/}" rel container instance
  case "$p" in "$HOME"/*/*) : ;; *) echo ""; return ;; esac
  rel="${p#"$HOME"/}"; container="${rel%%/*}"; rel="${rel#*/}"; instance="${rel%%/*}"
  echo "$HOME/$container/${instance%%-*}"
}

FAMILY="$(family_prefix "$PROJECT_DIR")"
[ -z "$FAMILY" ] && exit 0   # too shallow to name a family — fail safe, report nothing

# Narrow by command shape first: lsof-per-pid is the expensive part and this runs at EVERY
# session start, so only survivors of the age gate get their CWD resolved.
cands="$(pgrep -f 'python|playwright|ffmpeg|uvicorn|vite|node |mkdocs|pytest' 2>/dev/null || true)"

found=0
out=""
for pid in $cands; do
  [ "$pid" = "$SELF" ] && continue

  read -r etime cputime <<<"$(ps -p "$pid" -o etime=,time= 2>/dev/null | tr -s ' ')"
  [ -z "${etime:-}" ] && continue
  age="$(hms_secs "$etime")"
  [ "${age:-0}" -ge "$MIN_AGE" ] || continue          # young: not an orphan, skip before lsof

  # GATE 2 — cpu burn. This is the one that matters; see the header. An idle long-lived
  # server (MCP, dev server) has ~0 cputime and is filtered here by behaviour rather than by
  # name, so a server this list has never heard of is still correctly ignored.
  cpu_s="$(hms_secs "$cputime")"
  [ "${cpu_s:-0}" -ge "$MIN_CPU" ] || continue

  cmd="$(ps -p "$pid" -o command= 2>/dev/null)"
  [ -z "$cmd" ] && continue
  # Session infra and editors are SUPPOSED to be long-lived. Belt-and-braces with the cpu gate
  # above: a BUSY editor or language server would clear the cpu floor legitimately.
  # `--transport stdio` is the generic MCP-server shape, matched so new servers need no entry.
  case "$cmd" in
    *claude* | *lean-ctx* | *mcp* | *"--transport stdio"* | *Code\ Helper* | *cmux* | \
    *.vscode/extensions/* | *lsp_server.py* | *language-server* | *copilot* | \
    *" vim"* | *" nvim"* | *" emacs"* | */zsh | */bash | -zsh | -bash) continue ;;
  esac

  cwd="$(lsof -p "$pid" -a -d cwd -Fn 2>/dev/null | sed -n 's/^n//p' | head -1)"
  [ -z "$cwd" ] && continue
  case "$cwd" in "$FAMILY" | "$FAMILY"*) : ;; *) continue ;; esac   # this project family only

  # Cores-worth of CPU sustained over its whole life. ~2.0 means it has pegged two cores the
  # entire time, which is what the 2026-09-19 runaway looked like (198%).
  cores="$(awk -v c="$cpu_s" -v a="$age" 'BEGIN{ printf "%.2f", (a>0? c/a : 0) }')"
  found=$((found + 1))
  out="${out}    pid=${pid}  elapsed=$(human "$age")  cputime=$(human "$cpu_s")  sustained=${cores} core(s)
      ${cmd:0:150}
      cwd=${cwd}
"
done

[ "$found" -eq 0 ] && exit 0   # silent when clean: no noise on a normal session start

printf '%s\n' "[orphan-check] ${found} long-running process(es) in this project family predate this context:"
printf '%s' "$out"
cat <<'EOT'
    Nothing was killed. Verify each is still wanted before starting new work.
    A high cputime with no recent output is the tell — check what it has WRITTEN, not whether
    it is alive (a runaway sits in STAT R at 200% and looks perfectly healthy).
    Kill only processes under YOUR worktree; sibling worktrees belong to other agents.
EOT
exit 0
