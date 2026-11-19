#!/usr/bin/env bash
# subagent-model-guard.sh — Claude Code PreToolUse hook (Agent|Task|Workflow matcher). Enforces
# AGENTS.md "Subagent delegation": subagents run on sonnet or haiku; fable is the advisor's only;
# no subagent runs on Opus (operator, 2026-11-19: sessions launched Opus subagents the rules forbid).
#
# Agent / Task calls, in order:
#   - subagent_type "advisor": allowed, with any model or none (its frontmatter sets fable);
#   - subagent_type "fork": denied. A fork always runs on the main conversation's model (Opus
#     here) and ignores `model`, so it is an Opus subagent by construction;
#   - no non-empty `model`: denied. The subagent would run on the fallback (CLAUDE_CODE_SUBAGENT_MODEL
#     where set, else the main model, Opus): one session of 2026-11-14 spent 41% of its subagent
#     tokens that way. This also covers agent types whose frontmatter says opus;
#   - a model naming opus or fable (`opus`, `claude-opus-…`, `fable`, `claude-fable-…`, any case):
#     denied;
#   - anything else (sonnet, haiku, …): allowed.
# Workflow calls: the script (inline `script`, the file at `scriptPath`, or a saved workflow
# named `name` under ./.claude/workflows or ~/.claude/workflows) is read as text; a model literal
# naming opus or fable is denied, and so is a fork. Not covered: a model name assembled at runtime.
#
# PreToolUse contract: reads {tool_name, tool_input} as JSON on stdin; a deny is a
# `permissionDecision: "deny"` with a reason that names the fix (exit 0). Every other path allows
# (exit 0, no output), including SUBAGENT_MODEL_GUARD=off (escape hatch) and no jq / an unreadable
# payload / any internal error: fail-open by design, a broken guard must never stop all delegation.

set -uo pipefail   # deliberately NOT -e: internal errors must fail-open, not block

allow() { exit 0; }

deny() {
    jq -n --arg r "$1" \
      '{hookSpecificOutput:{hookEventName:"PreToolUse",permissionDecision:"deny",permissionDecisionReason:$r}}' \
      2>/dev/null \
      || printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"subagent-model-guard: use model sonnet or haiku on this subagent"}}\n'
    exit 0
}

RULE="Rule: ~/.config/AGENTS.md, Subagent delegation (sonnet for implementers, reviewers, planners and searches; haiku for mechanical work; fable is the advisor's only; no Opus subagents)."
BANNED_RE='(opus|fable)'   # any model id containing them: opus, opusplan, claude-opus-5-5, fable, claude-fable-5-1

[ "${SUBAGENT_MODEL_GUARD:-on}" = "off" ] && allow
command -v jq >/dev/null 2>&1 || allow
payload="$(cat 2>/dev/null)" || allow

tool="$(jq -r '.tool_name // empty' <<<"$payload" 2>/dev/null)" || allow

case "$tool" in
  Agent|Task)
    stype="$(jq -r '.tool_input.subagent_type // empty' <<<"$payload" 2>/dev/null)" || allow
    [ "$stype" = "advisor" ] && allow
    [ "$stype" = "fork" ] && deny "subagent-model-guard: forks are not allowed. A fork always runs on the main conversation's model (Opus) and ignores \`model\`. Launch a named subagent instead (subagent_type general-purpose, Explore, implementer, tester, ...) with model: \"sonnet\" or \"haiku\", or the advisor for a hard decision. ${RULE}"
    model="$(jq -r '.tool_input.model // empty | tostring | gsub("^\\s+|\\s+$"; "")' <<<"$payload" 2>/dev/null)" || allow
    [ -n "$model" ] || deny "subagent-model-guard: this ${tool} call (subagent_type: ${stype:-default}) names no model, so the subagent would run on the fallback (CLAUDE_CODE_SUBAGENT_MODEL, else the main conversation's model, Opus) instead of a chosen tier. Re-issue it with model: \"sonnet\" (implementers, reviewers, planners, searches) or \"haiku\" (mechanical work: tests, docs, small edits). ${RULE}"
    lc="$(printf '%s' "$model" | tr '[:upper:]' '[:lower:]')"
    if printf '%s' "$lc" | grep -Eq "$BANNED_RE"; then
      deny "subagent-model-guard: model \"${model}\" is not allowed for a subagent (subagent_type: ${stype:-default}). Use model: \"sonnet\" or \"haiku\"; fable only through the advisor (subagent_type: \"advisor\"). ${RULE}"
    fi
    allow
    ;;
  Workflow)
    script="$(jq -r '.tool_input.script // empty' <<<"$payload" 2>/dev/null)" || allow
    if [ -z "$script" ]; then
      path="$(jq -r '.tool_input.scriptPath // empty' <<<"$payload" 2>/dev/null)" || allow
      if [ -z "$path" ]; then
        name="$(jq -r '.tool_input.name // empty' <<<"$payload" 2>/dev/null)" || allow
        [ -n "$name" ] || allow
        for c in "./.claude/workflows/$name" "./.claude/workflows/$name.js" "$HOME/.claude/workflows/$name" "$HOME/.claude/workflows/$name.js"; do
          [ -f "$c" ] && { path="$c"; break; }
        done
      fi
      [ -n "$path" ] && [ -f "$path" ] || allow
      script="$(cat "$path" 2>/dev/null)" || allow
    fi
    lc="$(printf '%s' "$script" | tr '[:upper:]' '[:lower:]')"
    hit="$(printf '%s' "$lc" | grep -Eo "model[\"']?[[:space:]]*:[[:space:]]*[\"'\`][^\"'\`]*[\"'\`]" | grep -E "$BANNED_RE" | head -1)"
    [ -n "$hit" ] && deny "subagent-model-guard: this workflow gives an agent an Opus or Fable model (${hit}). Workflow agents run on sonnet or haiku; fable only through the advisor (outside the workflow). ${RULE}"
    fork="$(printf '%s' "$lc" | grep -Eo "subagent_?type[\"']?[[:space:]]*:[[:space:]]*[\"'\`]fork[\"'\`]" | head -1)"
    [ -n "$fork" ] && deny "subagent-model-guard: this workflow launches a fork (${fork}), which runs on the main model (Opus). Use a named agent type with model sonnet or haiku. ${RULE}"
    allow
    ;;
  *) allow ;;
esac
