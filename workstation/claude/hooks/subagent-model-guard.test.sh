#!/usr/bin/env bash
# Regression tests for subagent-model-guard.sh (the PreToolUse hook on Agent|Task).
# Run:  bash subagent-model-guard.test.sh   (exit 0 = all pass)
set -uo pipefail
HOOK="$(cd "$(dirname "$0")" && pwd)/subagent-model-guard.sh"
[ -x "$HOOK" ] || { echo "hook not found/executable: $HOOK"; exit 2; }
command -v jq >/dev/null || { echo "jq required for tests"; exit 2; }

pass=0; fail=0
run() {  # run <expect: allow|deny> <payload-json> <label> [env...]
  local expect="$1" payload="$2" label="$3" out got
  shift 3
  out="$(printf '%s' "$payload" | env "$@" bash "$HOOK" 2>/dev/null)"
  got="allow"; printf '%s' "$out" | grep -Eq '"permissionDecision":[[:space:]]*"deny"' && got="deny"
  if [ "$got" = "$expect" ]; then pass=$((pass+1)); printf '  ok   [%s] %s\n' "$got" "$label"
  else fail=$((fail+1)); printf '  FAIL exp=%s got=%s : %s\n' "$expect" "$got" "$label"; fi
}

run deny  '{"tool_name":"Agent","tool_input":{"description":"x","prompt":"p"}}'                                   "Agent, no subagent_type, no model"
run deny  '{"tool_name":"Agent","tool_input":{"subagent_type":"general-purpose","prompt":"p"}}'                   "general-purpose without model"
run deny  '{"tool_name":"Agent","tool_input":{"subagent_type":"Explore","prompt":"p"}}'                           "Explore without model"
run deny  '{"tool_name":"Agent","tool_input":{"subagent_type":"implementer","prompt":"p"}}'                       "pinned type without model (every call names one)"
run deny  '{"tool_name":"Task","tool_input":{"subagent_type":"general-purpose","prompt":"p"}}'                    "legacy Task tool name"
run deny  '{"tool_name":"Agent","tool_input":{"subagent_type":"general-purpose","model":"","prompt":"p"}}'        "empty model string"
run deny  '{"tool_name":"Agent","tool_input":{"subagent_type":"general-purpose","model":"   ","prompt":"p"}}'     "blank model string"
run deny  '{"tool_name":"Agent","tool_input":{"subagent_type":"general-purpose","model":null,"prompt":"p"}}'      "null model"
run allow '{"tool_name":"Agent","tool_input":{"subagent_type":"general-purpose","model":"sonnet","prompt":"p"}}'  "sonnet named"
run allow '{"tool_name":"Agent","tool_input":{"subagent_type":"tester","model":"haiku","prompt":"p"}}'            "haiku named"
run allow '{"tool_name":"Agent","tool_input":{"subagent_type":"advisor","model":"fable","prompt":"p"}}'           "fable named (tier is caller judgment)"
run allow '{"tool_name":"Agent","tool_input":{"subagent_type":"fork","prompt":"p"}}'                              "fork (model is ignored for forks)"
run allow '{"tool_name":"Bash","tool_input":{"command":"ls"}}'                                                    "other tool"
run allow 'not json at all'                                                                                       "garbage payload fails open"
run allow ''                                                                                                      "empty payload fails open"
run allow '{"tool_name":"Agent","tool_input":{"subagent_type":"general-purpose","prompt":"p"}}'                   "escape hatch SUBAGENT_MODEL_GUARD=off" SUBAGENT_MODEL_GUARD=off

# The deny reason names the fix.
out="$(printf '%s' '{"tool_name":"Agent","tool_input":{"subagent_type":"Explore","prompt":"p"}}' | bash "$HOOK")"
if jq -e '.hookSpecificOutput.permissionDecisionReason | test("model: \"sonnet\"") and test("Explore")' <<<"$out" >/dev/null; then
  pass=$((pass+1)); echo "  ok   deny reason names the type and the fix"
else fail=$((fail+1)); echo "  FAIL deny reason: $out"; fi

echo "subagent-model-guard: $pass passed, $fail failed"
[ "$fail" -eq 0 ]
