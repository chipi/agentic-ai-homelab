#!/usr/bin/env bash
# Tests for session-tmpdir.sh, in a scratch root.
#   bash workstation/claude/hooks/session-tmpdir.test.sh
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; HOOK="$HERE/session-tmpdir.sh"
T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
pass=0; fail=0
chk() { if eval "$2"; then echo "  ok   $1"; pass=$((pass+1)); else echo "  FAIL $1"; fail=$((fail+1)); fi; }
export AGENT_TMP_ROOT="$T/agent-tmp"
S1=11111111-2222-3333-4444-555555555555
run() { printf '%s' "$1" | CLAUDE_ENV_FILE="$2" bash "$HOOK"; echo $?; }

E="$T/env1"; : >"$E"
rc="$(run "{\"session_id\":\"$S1\",\"hook_event_name\":\"SessionStart\",\"source\":\"startup\"}" "$E")"
chk "exits 0" "[ '$rc' = 0 ]"
chk "makes the session's folder" "[ -d '$T/agent-tmp/$S1' ]"
chk "the folder is mode 700" "[ \"\$(stat -c %a '$T/agent-tmp/$S1')\" = 700 ]"
chk "exports TMPDIR to it in the env file" "grep -qx 'export TMPDIR=$T/agent-tmp/$S1' '$E'"
chk "the env file sets TMPDIR when sourced" "[ \"\$(bash -c '. $E; echo \$TMPDIR')\" = '$T/agent-tmp/$S1' ]"

E="$T/env2"; : >"$E"
run '{"session_id":"../../etc","source":"startup"}' "$E" >/dev/null
chk "an id that is not a uuid writes nothing" "[ ! -s '$E' ] && [ ! -e '$T/etc' ]"
run '{"source":"startup"}' "$E" >/dev/null
chk "no session id writes nothing" "[ ! -s '$E' ]"
rc="$(run "{\"session_id\":\"$S1\"}" "")"
chk "no CLAUDE_ENV_FILE: exits 0, writes nothing" "[ '$rc' = 0 ]"

E="$T/env3"; : >"$E"
run "{\"session_id\":\"$S1\",\"source\":\"resume\"}" "$E" >/dev/null
chk "a resumed session (folder exists) gets the same TMPDIR" "grep -qx 'export TMPDIR=$T/agent-tmp/$S1' '$E'"

rm -rf "$T/agent-tmp/$S1"; mkdir -p "$T/elsewhere"; ln -s "$T/elsewhere" "$T/agent-tmp/$S1"
E="$T/env4"; : >"$E"
run "{\"session_id\":\"$S1\"}" "$E" >/dev/null
chk "a symlink in place of the folder is refused" "[ ! -s '$E' ]"

echo "session-tmpdir tests: $pass passed, $fail failed"
[ "$fail" = 0 ] && echo "RESULT: PASS" || { echo "RESULT: FAIL"; exit 1; }
