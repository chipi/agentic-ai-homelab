#!/usr/bin/env bash
# Tests for tmp-sweep.sh, in a scratch /tmp (TMP_SWEEP_ROOT) and a scratch HOME (so a scratch log).
#   bash workstation/claude/hooks/tmp-sweep.test.sh
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; SWEEP="$HERE/tmp-sweep.sh"
[ -d /proc/self/fd ] || { echo "SKIP: needs Linux /proc"; exit 0; }
T="$(mktemp -d)"
cleanup() {   # stop only processes whose cwd is under this scratch dir
  local p
  for p in $(pgrep -u "$(id -u)" .); do
    case "$(readlink "/proc/$p/cwd" 2>/dev/null)" in "$T"/*) kill "$p" 2>/dev/null ;; esac
  done
  sleep 0.3; rm -rf "$T"
}
trap cleanup EXIT
pass=0; fail=0
chk() { if eval "$2"; then echo "  ok   $1"; pass=$((pass+1)); else echo "  FAIL $1"; fail=$((fail+1)); fi; }
export HOME="$T/home" TMP_SWEEP_ROOT="$T/tmp"; mkdir -p "$HOME"
U="$(id -u)"; ME="$(id -un)"; C="$T/tmp/claude-$U"
S1=11111111-2222-3333-4444-555555555555; S2=66666666-7777-8888-9999-000000000000
old() { touch -d '5 days ago' "$1"; find "$1" -exec touch -d '5 days ago' {} +; }
mk() { mkdir -p "$1"; echo x > "$1/f"; }
sweep() { bash "$SWEEP" "$@" >/dev/null 2>&1; }

echo "== --session"
mk "$C/-work-a/$S1/scratchpad"; mk "$C/-work-a/$S2"; mk "$C/-work-b/$S1"
TMP_SWEEP_DRY_RUN=1 sweep --session "$S1"
chk "dry run removes nothing" "[ -d '$C/-work-a/$S1' ] && [ -d '$C/-work-b/$S1' ]"
sweep --session not-a-uuid
chk "an id that is not a uuid removes nothing" "[ -d '$C/-work-a/$S1' ]"
sweep --session '*'
chk "a glob as the id removes nothing" "[ -d '$C/-work-a/$S2' ]"
sweep --session '../-work-b'
chk "a path as the id cannot reach a project folder" "[ -d '$C/-work-b' ]"
(cd "$C/-work-a/$S2" && setsid -f sleep 300 </dev/null >/dev/null 2>&1); sleep 0.3
sweep --session "$S2"
chk "a scratchpad another process works in is kept" "[ -d '$C/-work-a/$S2' ]"
(cd "$C/-work-a/$S1" && bash "$SWEEP" --session "$S1" >/dev/null 2>&1)
chk "the session's own scratchpad goes, even with the caller inside it (its ancestors don't count)" \
  "[ ! -e '$C/-work-a/$S1' ] && [ ! -e '$C/-work-b/$S1' ]"
chk "another session's scratchpad stays" "[ -d '$C/-work-a/$S2' ]"

echo "== --daily"
P="$T/tmp/pytest-of-$ME"
for n in 7 8 9 10 11 12; do mk "$P/pytest-$n"; old "$P/pytest-$n"; done
ln -s "$P/pytest-7" "$P/pytest-current"
mk "$T/tmp/player-tests-old"; old "$T/tmp/player-tests-old"
mk "$T/tmp/player-tests-young"
mk "$T/tmp/player-tests-busy"; old "$T/tmp/player-tests-busy"
(cd "$T/tmp/player-tests-busy" && setsid -f sleep 300 </dev/null >/dev/null 2>&1); sleep 0.3
mk "$C/-work-c/$S1"; old "$C/-work-c/$S1"
# a live "claude" (comm claude) in a project that holds no scratchpad open: its project's are kept
mkdir -p "$T/bin" "$T/work/live.proj"; ln -s "$(command -v sleep)" "$T/bin/claude"
LSLUG="$(printf '%s' "$T/work/live.proj" | sed 's/[^[:alnum:]]/-/g')"
mk "$C/$LSLUG/$S2"; old "$C/$LSLUG/$S2"
(cd "$T/work/live.proj" && setsid -f "$T/bin/claude" 300 </dev/null >/dev/null 2>&1); sleep 0.3
mk "$C/-work-c/notes"; old "$C/-work-c/notes"
mk "$C/bash-edit-diff"; old "$C/bash-edit-diff"
echo x > "$C/loose.txt"; old "$C/loose.txt"; echo y > "$C/new.txt"
mk "$T/tmp/unrelated"; old "$T/tmp/unrelated"
TMP_SWEEP_DRY_RUN=1 sweep --daily
chk "dry run removes nothing" "[ -d '$P/pytest-8' ] && [ -d '$T/tmp/player-tests-old' ] && [ -f '$C/loose.txt' ]"
sweep --daily
chk "old pytest dirs go" "[ ! -e '$P/pytest-8' ] && [ ! -e '$P/pytest-9' ]"
chk "the 3 newest pytest dirs stay, whatever their age" "[ -d '$P/pytest-10' ] && [ -d '$P/pytest-11' ] && [ -d '$P/pytest-12' ]"
chk "the one pytest-current points at stays" "[ -d '$P/pytest-7' ]"
chk "an old *-tests-* leftover goes" "[ ! -e '$T/tmp/player-tests-old' ]"
chk "a young one stays" "[ -d '$T/tmp/player-tests-young' ]"
chk "an old one a process works in stays" "[ -d '$T/tmp/player-tests-busy' ]"
chk "an old session scratchpad goes" "[ ! -e '$C/-work-c/$S1' ]"
chk "a non-uuid folder in a project dir stays" "[ -d '$C/-work-c/notes' ]"
chk "a project with a live Claude that holds no scratchpad keeps its old scratchpads" "[ -d '$C/$LSLUG/$S2' ]"
chk "Claude Code's own folders stay" "[ -d '$C/bash-edit-diff' ]"
chk "an old loose file goes, a new one stays" "[ ! -e '$C/loose.txt' ] && [ -f '$C/new.txt' ]"
chk "anything else in /tmp is never touched" "[ -d '$T/tmp/unrelated' ]"
chk "every removal is logged" "[ \$(grep -c 'REMOVE' '$HOME/.claude/hooks/tmp-sweep.log') -ge 7 ]"

echo "== session-reap.sh hands the session id over from its stdin"
mk "$C/-work-d/$S1"
R="$T/reap"; mkdir -p "$R"
printf '{"session_id":"%s","cwd":"%s","hook_event_name":"SessionEnd"}' "$S1" "$R" \
  | (cd "$R" && SESSION_REAP_NO_LOOP_SWEEP=1 SESSION_REAP_NO_WATCH_SWEEP=1 bash "$HERE/session-reap.sh" "$R" >/dev/null 2>&1)
chk "the ending session's scratchpad is removed by the hook" "[ ! -e '$C/-work-d/$S1' ]"
mk "$C/-work-d/$S1"
printf '{"session_id":"%s"}' "$S1" | (cd "$R" && SESSION_REAP_NO_TMP_SWEEP=1 SESSION_REAP_NO_LOOP_SWEEP=1 \
  SESSION_REAP_NO_WATCH_SWEEP=1 bash "$HERE/session-reap.sh" "$R" >/dev/null 2>&1)
chk "SESSION_REAP_NO_TMP_SWEEP=1 keeps it" "[ -d '$C/-work-d/$S1' ]"

echo; echo "RESULT: pass=$pass fail=$fail"
[ "$fail" = 0 ]
