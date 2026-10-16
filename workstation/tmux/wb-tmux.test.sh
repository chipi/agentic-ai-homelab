#!/usr/bin/env bash
# Disposable kill-and-restore tests for the tmux persistence (wb-tmux on top of
# tmux-resurrect). Everything runs in its own tmux server: own TMUX_TMPDIR, own
# -L socket, own HOME and config, own snapshot directory. The real tmux server and
# the real snapshot directory are only READ, to prove they are untouched.
#   bash workstation/tmux/wb-tmux.test.sh
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; WS="$(cd "$HERE/.." && pwd)"; REPO="$(cd "$WS/.." && pwd)"
for c in tmux git awk pgrep; do command -v "$c" >/dev/null || { echo "SKIP: $c not installed"; exit 0; }; done
REAL_HOME="$HOME"
REAL_SOCK="${TMUX%%,*}"; [ -n "$REAL_SOCK" ] || REAL_SOCK="${TMUX_TMPDIR:-/tmp}/tmux-$(id -u)/default"
REAL_STATE="$REAL_HOME/.local/share/tmux/resurrect"
PIN=$(awk '$1 == "tmux-resurrect" { print $3 }' "$HERE/plugins.lock")

T="$(mktemp -d)"
cleanup() {
  local i
  tmux -L wbtest kill-server 2>/dev/null
  for i in $(seq 1 30); do pgrep -f "tmux -L wbtest" >/dev/null || break; sleep 0.1; done
  if [ -n "${WB_TMUX_TEST_KEEP:-}" ]; then echo "kept scratch: $T"; else rm -rf "$T"; fi
}
pass=0; fail=0
ok()  { echo "  ok   $1"; pass=$((pass+1)); }
bad() { echo "  FAIL $1"; fail=$((fail+1)); }
chk() { if eval "$2"; then ok "$1"; else bad "$1"; fi; }

# Read-only fingerprint of the REAL server: its pid, sessions and pane ids.
real_fp() {
  [ -S "$REAL_SOCK" ] || { echo none; return; }
  env -u TMUX tmux -S "$REAL_SOCK" display-message -p '#{pid}' 2>/dev/null
  env -u TMUX tmux -S "$REAL_SOCK" list-panes -a -F '#{session_id} #{session_name} #{window_id} #{pane_id}' 2>/dev/null | sort
}
real_state_fp() { find "$REAL_STATE" -maxdepth 1 -printf '%f|%s|%T@\n' 2>/dev/null | sort | md5sum; }
REAL_BEFORE=$(real_fp); REAL_STATE_BEFORE=$(real_state_fp)

# --- the isolated environment ---------------------------------------------------
unset TMUX
export TMUX_TMPDIR="$T/tmuxsock" HOME="$T/home" XDG_DATA_HOME="" WB_TMUX_SOCKET=wbtest
export WB_TMUX_EPHEMERAL_RE='^/wb-tmux-test-never(/|$)'   # scratch lives under /tmp itself
mkdir -p "$TMUX_TMPDIR" "$HOME/.local/bin" "$HOME/.config/tmux" "$HOME/.local/share/tmux/plugins"
trap cleanup EXIT
P="$HOME/.local/share/tmux/plugins/tmux-resurrect"
for src in "${WB_TMUX_TEST_RESURRECT_SRC:-}" "$REAL_HOME/.local/share/tmux/plugins/tmux-resurrect" https://github.com/tmux-plugins/tmux-resurrect.git; do
  [ -n "$src" ] || continue
  git clone -q --no-checkout "$src" "$P" 2>/dev/null && git -C "$P" -c advice.detachedHead=false checkout -q --detach "$PIN" 2>/dev/null && break
  rm -rf "$P"
done
if [ "$(git -C "$P" rev-parse HEAD 2>/dev/null)" != "$PIN" ]; then
  echo "FAIL cannot obtain tmux-resurrect at the pinned commit $PIN (offline? set WB_TMUX_TEST_RESURRECT_SRC)"; exit 1
fi
# The installed layout: the same links and the same source line install.sh creates.
ln -s "$HERE/wb-tmux" "$HOME/.local/bin/wb-tmux"
ln -s "$HERE/persistence.conf" "$HOME/.config/tmux/workstation-persistence.conf"
CONF="$HOME/.config/tmux/tmux.conf"
{
  if [ -f /usr/share/omarchy/config/tmux/tmux.conf ]; then cat /usr/share/omarchy/config/tmux/tmux.conf
  else printf 'set -g base-index 1\nsetw -g pane-base-index 1\n'; fi
  printf '\n# >>> workstation tmux-persistence >>>\nsource-file -q ~/.config/tmux/workstation-persistence.conf\n# <<< workstation tmux-persistence <<<\n'
} > "$CONF"
export WB_TMUX_CONF="$CONF"
t()  { tmux -L wbtest -f "$CONF" "$@"; }
WB="$HOME/.local/bin/wb-tmux"
STATE="$HOME/.local/share/tmux/resurrect"

# Independent topology extraction (not wb-tmux's own code): names, indices,
# active/zoom flags, layout geometry without checksum and pane ids, and cwds.
topo() {
  local d=$'\t'
  t list-windows -a -F "W${d}#{session_name}${d}#{window_index}${d}#{window_name}${d}#{window_active}${d}#{window_zoomed_flag}${d}#{window_panes}${d}#{window_layout}" |
    sed -E 's/\t[0-9a-f]{4},/\t/; s/([0-9]+x[0-9]+,[0-9]+,[0-9]+),[0-9]+/\1/g'
  t list-panes -a -F "P${d}#{session_name}${d}#{window_index}${d}#{pane_index}${d}#{pane_active}${d}#{pane_current_path}"
}
ready() {  # ready <target>...: until each pane's shell has printed its prompt
  local p i
  for p in "$@"; do
    for i in $(seq 1 100); do [ -n "$(t capture-pane -p -t "$p" | tr -d '[:space:]')" ] && break; sleep 0.1; done
  done
}
wait_cmd() {  # wait_cmd <target> <command>: until the pane's foreground command is <command>
  local i; for i in $(seq 1 50); do [ "$(t display -p -t "$1" '#{pane_current_command}')" = "$2" ] && return 0; sleep 0.1; done; return 1
}

# --- fake cockpit ------------------------------------------------------------------
A="$T/projects/project-a"; B="$T/projects/project-b"; W="$T/work/orrery/main"
mkdir -p "$A/subdir/deep" "$B" "$W" "$T/bin"
for m in claude codex node vim; do cp "$(command -v sleep)" "$T/bin/$m"; done
echo "marker" > "$T/marker.log"
t new-session -d -s alpha -n editor -c "$A" -x 200 -y 50
t split-window -h -t alpha:editor -c "$A/subdir"
t split-window -v -t alpha:editor.2 -c "$A/subdir/deep"
t select-layout -t alpha:editor main-vertical
t new-window -d -t alpha -n terminal -c "$A"
t new-window -d -t alpha -n agents -c "$A"
t split-window -h -t alpha:agents -c "$A/subdir"
ready alpha:terminal alpha:agents.1 alpha:agents.2
t send-keys -t alpha:terminal "exec tail -f $T/marker.log $T/SECRET-NOT-TO-BE-SAVED" C-m   # tail is on Resurrect's default list; an argument shaped like a secret
t send-keys -t alpha:agents.1 "$T/bin/claude 7771" C-m                  # agent-shaped marker
t send-keys -t alpha:agents.2 "$T/bin/vim 7772" C-m                     # editor on the default list
t resize-pane -Z -t alpha:agents.2
t new-session -d -s beta -n main -c "$B" -x 200 -y 50
t split-window -v -t beta:main -c "$B"
ready beta:main.2
t send-keys -t beta:main.2 "$T/bin/node 7773" C-m
t new-session -d -s gamma -n repo -c "$W" -x 200 -y 50
ready gamma:repo
t send-keys -t gamma:repo "$T/bin/codex 7774" C-m
t select-window -t alpha:agents; t select-pane -t alpha:editor.3; t select-pane -t beta:main.1
wait_cmd alpha:terminal tail; wait_cmd alpha:agents.1 claude; wait_cmd alpha:agents.2 vim; wait_cmd beta:main.2 node; wait_cmd gamma:repo codex
BEFORE=$(topo)
MARKERS=$(pgrep -f "$T/bin/|tail -f $T/marker.log| 777[1-4]$" | sort)
FG=$(t list-panes -a -F "#{session_name}:#{window_index}.#{pane_index}=#{pane_current_command}" | grep -v "=bash$" | sort | tr "\n" " ")
SERVER_PID=$(t display -p '#{pid}')
PANE_PIDS=$(t list-panes -a -F '#{pane_pid}')
OLD_INO=$(stat -c %i "$W")

echo "== cockpit built (3 sessions, 5 windows, 9 panes; markers running)"
chk "the five marker programs are the panes' foreground commands before the save" "[ \"\$FG\" = 'alpha:2.1=tail alpha:3.1=claude alpha:3.2=vim beta:1.2=node gamma:1.1=codex ' ]"
chk "the disposable server is a different process from the real one" "[ \"$SERVER_PID\" != \"\$(head -1 <<<\"\$REAL_BEFORE\")\" ]"

echo "== save with the configured mechanism (wb-tmux save → Resurrect save.sh → scrub hook)"
"$WB" save > "$T/save.out" 2>&1; rc=$?
chk "wb-tmux save: exit 0 and 'verified' against the live server" "[ $rc = 0 ] && grep -q '^verified: 5 windows, 9 panes in 3 sessions' '$T/save.out'"
F=$(readlink -f "$STATE/last")
chk "snapshot written under \$HOME/.local/share/tmux/resurrect, never /tmp of the real user" "[ -f '$F' ] && [[ '$F' == '$HOME/.local/share/tmux/resurrect/'* ]]"
chk "snapshot mode 0600, directory 0700 (scrub hook)" "[ \$(stat -c %a '$F') = 600 ] && [ \$(stat -c %a '$STATE') = 700 ]"
chk "no saved command lines: every pane's field 11 is ':' (no SECRET, no marker arguments)" \
  "[ -z \"\$(awk -F'\t' '\$1 == \"pane\" && \$11 != \":\"' '$F')\" ] && ! grep -q -e SECRET -e 7771 -e 7773 '$F'"
chk "the saved cwd is the pathname string, e.g. :$W" "grep -qF \":$W\" '$F'"
chk "foreground command names are recorded (for the audit), e.g. claude and node" \
  "awk -F'\t' '\$1 == \"pane\" { print \$10 }' '$F' | grep -qx claude && awk -F'\t' '\$1 == \"pane\" { print \$10 }' '$F' | grep -qx node"
"$WB" show > "$T/show.out" 2>&1
chk "wb-tmux show lists the five foreground programs that will NOT be restarted" "[ \$(grep -c '(not restarted' '$T/show.out') = 5 ]"

echo "== kill ONLY the disposable server, prove its processes are dead"
t kill-server
for i in $(seq 1 50); do alive=0; for p in $SERVER_PID $PANE_PIDS $MARKERS; do kill -0 "$p" 2>/dev/null && alive=1; done; [ $alive = 0 ] && break; sleep 0.1; done
chk "server, every pane shell and every marker process are gone" "[ $alive = 0 ] && [ -z \"\$(pgrep -f \"$T/bin/|tail -f $T/marker.log| 777[1-4]$\")\" ]"
chk "the real tmux server is still the same server with the same panes" "[ \"\$(real_fp)\" = \"\$REAL_BEFORE\" ]"

echo "== same pathname, new backing store (models /work moving onto @work)"
mv "$T/work" "$T/work.pre-subvol"; mkdir -p "$T/work/orrery"; cp -a "$T/work.pre-subvol/orrery/main" "$T/work/orrery/main"
NEW_INO=$(stat -c %i "$W")
chk "the visible path now has a different backing directory (inode $OLD_INO -> $NEW_INO)" "[ '$OLD_INO' != '$NEW_INO' ]"

echo "== restore into a fresh server (wb-tmux restore → Resurrect restore.sh + selection)"
"$WB" restore > "$T/restore.out" 2>&1; rc=$?
AFTER=$(topo)
chk "wb-tmux restore: exit 0 and verified" "[ $rc = 0 ] && grep -q '^verified: 5 windows, 9 panes in 3 sessions' '$T/restore.out'"
chk "topology identical: sessions, window names and indices, pane counts, layouts, active window/pane, zoom, cwds" \
  "[ \"\$AFTER\" = \"\$BEFORE\" ]"
[ "$AFTER" = "$BEFORE" ] || diff <(echo "$BEFORE") <(echo "$AFTER") | sed 's/^/      /'
chk "sessions exactly alpha beta gamma (bootstrap session removed)" "[ \"\$(t list-sessions -F '#{session_name}' | tr '\n' ' ')\" = 'alpha beta gamma ' ]"
chk "layouts restored: alpha:editor is still main-vertical with 3 panes" \
  "[ \"\$(grep -P '^W\talpha\t1\t' <<<\"\$AFTER\")\" = \"\$(grep -P '^W\talpha\t1\t' <<<\"\$BEFORE\")\" ] && grep -qP '^W\talpha\t1\teditor\t0\t0\t3\t200x50,0,0\{' <<<\"\$AFTER\""
chk "active selection: alpha's active window is agents, editor's active pane is 3, beta's is 1" \
  "[ \"\$(t display -p -t alpha '#{window_name}')\" = agents ] && [ \"\$(t display -p -t alpha:editor '#{pane_index}')\" = 3 ] && [ \"\$(t display -p -t beta:main '#{pane_index}')\" = 1 ]"
chk "zoom restored on alpha:agents" "[ \"\$(t display -p -t alpha:agents '#{window_zoomed_flag}')\" = 1 ]"
sleep 0.5
chk "no marker process restarted (claude, codex, node, vim, tail -f)" "[ -z \"\$(pgrep -f \"$T/bin/|tail -f $T/marker.log| 777[1-4]$\")\" ]"
chk "every restored pane runs a plain shell" "[ \"\$(t list-panes -a -F '#{pane_current_command}' | sort -u)\" = bash ]"
GPID=$(t display -p -t gamma:repo '#{pane_pid}')
chk "the gamma pane is at the same pathname, on the NEW backing directory" \
  "[ \"\$(t display -p -t gamma:repo '#{pane_current_path}')\" = '$W' ] && [ \"\$(stat -L -c %i /proc/$GPID/cwd)\" = '$NEW_INO' ]"

echo "== autosave guard (the timer's --auto mode)"
t kill-server; sleep 0.2
t new-session -d -s scratch -c "$HOME"; LAST=$(readlink "$STATE/last")
"$WB" save --auto > "$T/auto.out" 2>&1; rc=$?
chk "fresh server, not restored yet: --auto saves nothing ('paused'), 'last' unchanged" \
  "[ $rc = 0 ] && grep -q 'autosave paused' '$T/auto.out' && [ \"\$(readlink '$STATE/last')\" = '$LAST' ]"
"$WB" restore > "$T/r2.out" 2>&1
chk "restore into a server holding only an unrelated session: saved sessions added, 'scratch' kept" \
  "[ \"\$(t list-sessions -F '#{session_name}' | sort | tr '\n' ' ')\" = 'alpha beta gamma scratch ' ]"
t new-window -d -t alpha -n added -c "$A"
"$WB" save --auto > "$T/auto2.out" 2>&1
chk "after a restore the server is armed: --auto saves the new window" \
  "[ \"\$(readlink '$STATE/last')\" != '$LAST' ] && grep -qP '^window\talpha\t[0-9]+\t:added\t' \"\$(readlink -f '$STATE/last')\""

echo "== verify detects drift and flags unrestorable panes"
"$WB" save >/dev/null 2>&1; t new-window -d -t beta -n drift -c "$B"
"$WB" verify > "$T/v.out" 2>&1; rc=$?
chk "a window added after the save: verify exit 1 and names it" "[ $rc = 1 ] && grep -q 'drift' '$T/v.out'"
t kill-window -t beta:drift
mkdir -p "$T/eph/x" "$T/with space"
t new-window -d -t beta -n eph -c "$T/eph/x"; t new-window -d -t beta -n spaced -c "$T/with space"
mkdir -p "$T/gone"; t new-window -d -t beta -n gone -c "$T/gone"; sleep 0.2; rmdir "$T/gone"
WB_TMUX_EPHEMERAL_RE="^$T/eph(/|\$)" "$WB" save > "$T/f.out" 2>&1; rc=$?
chk "save flags ephemeral, whitespace and deleted cwds (exit 3, one FLAG each)" \
  "[ $rc = 3 ] && grep -q 'FLAG beta:.*ephemeral' '$T/f.out' && grep -q 'FLAG beta:.*whitespace' '$T/f.out' && grep -q 'FLAG beta:.*was deleted' '$T/f.out'"
for w in eph spaced gone; do t kill-window -t "beta:$w"; done

echo "== two saves in the same second (Resurrect names snapshots by the second)"
"$WB" save >/dev/null 2>&1; "$WB" save > "$T/twice.out" 2>&1; rc=$?
chk "back-to-back saves: exit 0 and 'last' still resolves to an existing snapshot" "[ $rc = 0 ] && [ -f \"\$(readlink -f '$STATE/last')\" ]"

echo "== restore refusals (nothing changed)"
"$WB" save >/dev/null 2>&1; GOOD=$(readlink -f "$STATE/last"); GOODTOPO=$(topo)
"$WB" restore > "$T/r3.out" 2>&1; rc=$?
chk "saved sessions already exist in the server: refused, exit 2" "[ $rc = 2 ] && grep -q \"refused: session '\" '$T/r3.out'"
t kill-server; sleep 0.2
mv "$T/projects" "$T/projects.away"
"$WB" restore > "$T/r4.out" 2>&1; rc=$?
chk "saved cwds missing (filesystem not mounted): refused, exit 2, and no server was started" \
  "[ $rc = 2 ] && grep -q 'saved working directories are missing' '$T/r4.out' && ! t list-sessions >/dev/null 2>&1"
mv "$T/projects.away" "$T/projects"
BAD="$STATE/tmux_resurrect_20000101T000000.txt"; head -c 200 "$GOOD" > "$BAD"
"$WB" restore "$BAD" > "$T/r5.out" 2>&1; rc=$?
chk "truncated snapshot: refused, exit 2, no server started" "[ $rc = 2 ] && grep -q 'incomplete or malformed' '$T/r5.out' && ! t list-sessions >/dev/null 2>&1"
rm -f "$BAD"

echo "== manual fallback: wb-tmux plan rebuilds the shells with plain tmux"
"$WB" plan "$GOOD" > "$T/plan.sh" 2>&1
mkdir -p "$T/shim"; printf '#!/bin/sh\nexec "%s" -L wbtest -f "%s" "$@"\n' "$(command -v tmux)" "$CONF" > "$T/shim/tmux"; chmod +x "$T/shim/tmux"
PATH="$T/shim:$PATH" bash "$T/plan.sh" > "$T/plan.out" 2>&1
PLANNED=$(topo)
chk "plan alone recreates every session, window name and index, pane count and cwd" \
  "[ \"\$(grep '^W' <<<\"\$PLANNED\" | cut -f2,3,4,7 | sort)\" = \"\$(grep '^W' <<<\"\$GOODTOPO\" | cut -f2,3,4,7 | sort)\" ] && [ \"\$(grep '^P' <<<\"\$PLANNED\" | cut -f2,3,4,6 | sort)\" = \"\$(grep '^P' <<<\"\$GOODTOPO\" | cut -f2,3,4,6 | sort)\" ]"
chk "plan also restores layouts and the active selection" "[ \"\$PLANNED\" = \"\$GOODTOPO\" ]"
[ "$PLANNED" = "$GOODTOPO" ] || diff <(echo "$GOODTOPO") <(echo "$PLANNED") | sed 's/^/      /'
chk "plan output contains no program to start (only tmux commands and comments)" "! grep -vE '^(tmux |#)' '$T/plan.sh' | grep -q ."

echo "== guards"
t kill-server 2>/dev/null; sleep 0.2
printf 'set -g base-index 1\n' > "$T/bare.conf"
WB_TMUX_CONF="$T/bare.conf" tmux -L wbtest -f "$T/bare.conf" new-session -d -s bare -c "$HOME"
snapfp=$(ls -l --time-style=+%s.%N "$STATE")
WB_TMUX_CONF="$T/bare.conf" "$WB" save > "$T/g.out" 2>&1; rc=$?
chk "server without the persistence config: save refuses (exit 2), writes nothing" \
  "[ $rc = 2 ] && grep -q 'lacks the persistence config' '$T/g.out' && [ \"\$(ls -l --time-style=+%s.%N '$STATE')\" = \"\$snapfp\" ]"
WB_TMUX_CONF="$T/bare.conf" "$WB" save --auto > "$T/g2.out" 2>&1; rc=$?
chk "... and the timer's --auto mode logs it, exits 0 (no failed unit), writes nothing" \
  "[ $rc = 0 ] && grep -q 'lacks the persistence config' '$T/g2.out' && [ \"\$(ls -l --time-style=+%s.%N '$STATE')\" = \"\$snapfp\" ]"
t kill-server 2>/dev/null
cp "$GOOD" "$T/scrubme"; awk -F'\t' -v OFS='\t' '$1 == "pane" { $11 = ":ssh -i key --password=hunter2" } { print }' "$GOOD" > "$T/scrubme"
"$WB" scrub "$T/scrubme"
chk "scrub blanks saved command lines and makes the file 0600" "! grep -q hunter2 '$T/scrubme' && [ \$(stat -c %a '$T/scrubme') = 600 ]"
chk "wb-tmux has no kill-server, kill-session of saved sessions, or process restore" \
  "! grep -v '^[[:space:]]*#' '$HERE/wb-tmux' | grep -qE 'kill-server|@resurrect-processes .*(:all:|true)|send-keys'"
chk "the only kill-session in wb-tmux targets its own bootstrap session 0" \
  "[ \"\$(grep -v '^[[:space:]]*#' '$HERE/wb-tmux' | grep -o 'kill-session -t [^ ;]*' | sort -u)\" = 'kill-session -t 0' ]"

echo "== maintenance runbook ordering"
RB="$REPO/docs/recipes/x3-storage-separation.md"
line() { grep -n -m1 -F -- "$1" "$RB" | cut -d: -f1; }
chk "runbook: final wb-tmux save + verify come before the /work live-process check and the tmux stop" \
  "[ -n \"\$(line 'wb-tmux save')\" ] && [ \$(line 'wb-tmux save') -lt \$(line '\"\$WBS\" users /work') ] && [ \$(line 'wb-tmux verify') -lt \$(line 'tmux kill-server') ]"
chk "runbook: wb-tmux restore only after the post-reboot mount acceptance" \
  "[ \$(line 'wb-tmux restore') -gt \$(line '## Q. Reboot and acceptance') ] && [ \$(line 'wb-tmux restore') -gt \$(line 'Storage accepted. Only now restore the tmux cockpit') ] && [ \$(line 'Storage accepted. Only now restore the tmux cockpit') -gt \$(line '# systemctl reboot') ]"
chk "runbook: the pre-maintenance gate lists the tmux persistence conditions" \
  "grep -q 'tmux persistence installed' '$RB' && grep -q 'disposable restore test green' '$RB' && grep -q 'saved topology validated' '$RB'"

echo "== the real environment was only read"
chk "real tmux server: same pid, sessions, windows and panes as before the tests" "[ \"\$(real_fp)\" = \"\$REAL_BEFORE\" ]"
chk "real snapshot directory unchanged" "[ \"\$(real_state_fp)\" = '$REAL_STATE_BEFORE' ]"

echo; echo "RESULT: pass=$pass fail=$fail"
[ "$fail" = 0 ]
