#!/usr/bin/env bash
# command-ask-guard.sh — Claude Code PreToolUse hook. Makes the AGENTS.md "ask first" rules deterministic:
# a command that pushes, opens a GitHub issue, deletes or prunes destructively, or installs into a shared
# environment gets `permissionDecision: "ask"`, so Claude Code asks the operator (in a headless run, where
# nobody can answer, it is refused).
#
# Why a hook and not only permissions.ask: Bash(...) permission rules match the native Bash tool only, and the
# lean-ctx policy routes agents' shell commands through mcp__lean-ctx__ctx_shell, which those rules never see
# (2026-11-21: `claude -p "... git push origin main"` pushed through ctx_shell with Bash(git push:*) in ask).
# This hook reads the command from either: matcher `Bash|bash|mcp__lean-ctx__ctx_shell|mcp__lean-ctx__shell|
# mcp__lean-ctx__ctx_execute`.
#
# Asked about (anywhere in the command, so `cd x && git push` is caught too):
#   git push (incl. `git -C dir push`, --force) · gh issue create · rm -rf / -fr / -r -f ·
#   docker system|volume|image|container|builder|network prune · docker volume rm · compose down -v/--volumes ·
#   terraform apply|destroy · pip/pip3/python -m pip/uv pip install · uv add · uv tool install ·
#   npm install -g / npm i -g · brew install
# Not covered: a command assembled at runtime (eval, a script file that pushes), and other shells' wrappers.
#
# PreToolUse contract: reads {tool_name, tool_input} as JSON on stdin; "ask" is printed as JSON, exit 0. Every
# other path allows (no output, exit 0), including COMMAND_ASK_GUARD=off (the operator's escape hatch; agents
# never set it) and no jq / an unreadable payload: fail-open, a broken guard must never block every command.

set -uo pipefail

allow() { exit 0; }
ask() {
    jq -n --arg r "$1" \
      '{hookSpecificOutput:{hookEventName:"PreToolUse",permissionDecision:"ask",permissionDecisionReason:$r}}' \
      2>/dev/null || allow
    exit 0
}

[ "${COMMAND_ASK_GUARD:-on}" = "off" ] && allow
command -v jq >/dev/null 2>&1 || allow
payload="$(cat 2>/dev/null)" || allow
tool="$(jq -r '.tool_name // empty' <<<"$payload" 2>/dev/null)" || allow
case "$tool" in Bash|bash|mcp__lean-ctx__ctx_shell|mcp__lean-ctx__shell|mcp__lean-ctx__ctx_execute) ;; *) allow ;; esac
cmd="$(jq -r '.tool_input.command // .tool_input.code // empty' <<<"$payload" 2>/dev/null)" || allow
[ -n "$cmd" ] || allow

S='(^|[;&|(`[:space:]])'   # start of a command word: line start or a separator / whitespace before it
check() {   # $1 = ERE, $2 = what, $3 = the AGENTS.md rule
    if printf '%s' "$cmd" | grep -Eq -- "$1"; then
        ask "command-ask-guard: ${2}. The operator approves this per instance (~/.config/AGENTS.md, ${3}). Ask in the conversation before running it; in a headless run it is refused."
    fi
}
check "${S}git([[:space:]]+-[^;&|]*)?([[:space:]]+[^;&|[:space:]]+)*[[:space:]]+push([[:space:]]|\$)" "git push" "1: never push without the operator's go"
check "${S}gh[[:space:]]+issue[[:space:]]+create" "opening a GitHub issue" "1: never open a GitHub issue without the operator's explicit ask"
check "${S}rm[[:space:]]+(-[A-Za-z]*r[A-Za-z]*f|-[A-Za-z]*f[A-Za-z]*r|-r[[:space:]]+-f|-f[[:space:]]+-r|--recursive[[:space:]]+--force|--force[[:space:]]+--recursive)" "a recursive forced delete" "1: destructive changes need a per-instance go; deletes cover the exact paths named"
check "${S}docker[[:space:]]+(system|volume|image|container|builder|network)[[:space:]]+prune" "a docker prune" "1: destructive changes need a per-instance go"
check "${S}docker[[:space:]]+volume[[:space:]]+rm" "deleting a docker volume" "1: destructive changes need a per-instance go"
check "compose([[:space:]]+[^;&|]*)?[[:space:]]+down([[:space:]]+[^;&|]*)?[[:space:]]+(-v|--volumes)([[:space:]]|\$)" "compose down with volumes" "1: destructive changes need a per-instance go"
check "${S}terraform[[:space:]]+(apply|destroy)" "terraform apply/destroy" "1: destructive changes need a per-instance go"
check "${S}(pip3?|python3?[[:space:]]+-m[[:space:]]+pip|uv[[:space:]]+pip)[[:space:]]+install([[:space:]]|\$)" "a pip install" "1: no new dependencies and no installs into a shared environment without approval"
check "${S}uv[[:space:]]+(add|tool[[:space:]]+install)([[:space:]]|\$)" "a uv add / tool install" "1: no new dependencies without approval"
check "${S}npm[[:space:]]+(install|i)([[:space:]]+[^;&|]*)?[[:space:]]+(-g|--global)([[:space:]]|\$)" "a global npm install" "1: no installs into a shared environment without approval"
check "${S}brew[[:space:]]+install" "a brew install" "1: no installs into a shared environment without approval"
allow
