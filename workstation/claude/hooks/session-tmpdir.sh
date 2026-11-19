#!/usr/bin/env bash
# session-tmpdir.sh — SessionStart: give each Claude session its own TMPDIR off /tmp.
#
# The workstation's /tmp is a tmpfs with a fixed 1,048,576 inodes shared by every session; on
# 2026-11-19 ~17:50 CET test runs filled it and every session's commands failed ("No space left
# on device"). This hook makes ~/.cache/agent-tmp/<session id> (mode 700, on the home disk, outside
# any git worktree) and exports TMPDIR to it for every command the session runs, through
# CLAUDE_ENV_FILE. Python's tempfile, mktemp and pytest's default basetemp follow TMPDIR.
# tmp-sweep.sh removes the folder at SessionEnd (--session) and any left over after 48 h (--daily).
#
# Not moved by this: Claude Code's own scratchpad (/tmp/claude-<uid>/...), which the harness
# places itself, and tools that hardcode /tmp.
# Env: AGENT_TMP_ROOT -> the parent folder (default ~/.cache/agent-tmp; tests).
# Never blocks a session: any failure exits 0 and leaves TMPDIR as it was.
set -u
in="$(cat)"
id="$(printf '%s' "$in" | sed -n 's/.*"session_id"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -1)"
[[ "$id" =~ ^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$ ]] || exit 0
[ -n "${CLAUDE_ENV_FILE:-}" ] || exit 0
d="${AGENT_TMP_ROOT:-$HOME/.cache/agent-tmp}/$id"
mkdir -p -m 700 "$d" 2>/dev/null && [ -d "$d" ] && [ ! -L "$d" ] || exit 0
printf 'export TMPDIR=%q\n' "$d" >>"$CLAUDE_ENV_FILE"
exit 0
