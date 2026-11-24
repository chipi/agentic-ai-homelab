#!/usr/bin/env bash
# PreToolUse on Bash: lean-ctx's rewrite, except for git inside an agent worktree (`*/.claude/worktrees/*`).
#
# Why: `lean-ctx hook rewrite` turns every Bash command into `lean-ctx -c '<command>'`. Claude Code's
# worktree isolation must show that an isolated agent's git stays in its own worktree, and it cannot see into
# that wrapper, so it refused every git command there, even a bare `git status --short` (orrery's subagents,
# 2026-11-23; reproduced 2026-11-24). lean-ctx has no per-command rewrite exclusion (`excluded_commands` does
# not stop the rewrite, checked on 3.10.5), so this gate sits in front of it: such a command gets no output
# and runs as written; every other call is lean-ctx's hook, unchanged.
#
# Not covered: a worktree that is not under `.claude/worktrees/` (a hand-made one needs no isolation check).
payload="$(cat)"
if command -v jq >/dev/null 2>&1; then
  cwd="$(jq -r '.cwd // empty' <<<"$payload" 2>/dev/null)"
  cmd="$(jq -r '.tool_input.command // empty' <<<"$payload" 2>/dev/null)"
  case "$cwd" in
    */.claude/worktrees/*)
      if printf '%s' "$cmd" | grep -Eq '(^|[^[:alnum:]_.-])git([[:space:]]|$)'; then exit 0; fi ;;
  esac
fi
LC="${LEAN_CTX_BIN:-$(command -v lean-ctx || echo "$HOME/.local/bin/lean-ctx")}"
printf '%s' "$payload" | exec "$LC" hook rewrite
