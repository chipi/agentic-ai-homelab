#!/usr/bin/env bash
# subagent-model-guard.sh — Claude Code PreToolUse hook (Agent|Task matcher). Blocks a
# subagent launch that names no `model`, enforcing AGENTS.md "Subagent delegation":
# every Agent call names its model (sonnet for implementers, reviewers, planners and
# searches; haiku for mechanical work). Without it the subagent inherits the main
# conversation's model (Opus): one session of 2026-11-14 spent 41% of its subagent
# tokens that way (83 general-purpose calls, 14 Explore).
#
# PreToolUse contract: reads {tool_name, tool_input} as JSON on stdin. A launch with no
# non-empty `tool_input.model` gets a `deny` decision (exit 0) whose reason names the fix;
# the caller re-issues the call with a model. EVERY other path allows (exit 0, no output):
#   - `subagent_type: "fork"` (a fork always runs on the main model; `model` is ignored,
#     so demanding one would only add noise — the rule "no forks for heavy work" is
#     judgment, not something a hook can see);
#   - a call that names any model (tier choice stays the caller's judgment);
#   - SUBAGENT_MODEL_GUARD=off in the environment (escape hatch);
#   - no jq, unreadable payload, or any internal error. Fail-open by design: a broken
#     guard must never stop all delegation.

set -uo pipefail   # deliberately NOT -e: internal errors must fail-open, not block

allow() { exit 0; }

deny() {
    jq -n --arg r "$1" \
      '{hookSpecificOutput:{hookEventName:"PreToolUse",permissionDecision:"deny",permissionDecisionReason:$r}}' \
      2>/dev/null \
      || printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"subagent-model-guard: name a model (sonnet or haiku) on this Agent call"}}\n'
    exit 0
}

[ "${SUBAGENT_MODEL_GUARD:-on}" = "off" ] && allow
command -v jq >/dev/null 2>&1 || allow
payload="$(cat 2>/dev/null)" || allow

tool="$(jq -r '.tool_name // empty' <<<"$payload" 2>/dev/null)" || allow
case "$tool" in Agent|Task) ;; *) allow ;; esac

stype="$(jq -r '.tool_input.subagent_type // empty' <<<"$payload" 2>/dev/null)" || allow
[ "$stype" = "fork" ] && allow

model="$(jq -r '.tool_input.model // empty | tostring | gsub("^\\s+|\\s+$"; "")' <<<"$payload" 2>/dev/null)" || allow
[ -n "$model" ] && allow

deny "subagent-model-guard: this ${tool} call (subagent_type: ${stype:-default}) names no model, so the subagent would inherit the main conversation's model. Re-issue it with model: \"sonnet\" (implementers, reviewers, planners, searches) or \"haiku\" (mechanical work: tests, docs, small edits). Rule: ~/.config/AGENTS.md, Subagent delegation."
