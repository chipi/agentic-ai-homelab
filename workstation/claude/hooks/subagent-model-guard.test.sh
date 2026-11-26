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
run allow '{"tool_name":"Agent","tool_input":{"subagent_type":"advisor","model":"fable","prompt":"p"}}'           "advisor on fable"
run allow '{"tool_name":"Agent","tool_input":{"subagent_type":"advisor","prompt":"p"}}'                           "advisor without model (its frontmatter sets fable)"
run allow '{"tool_name":"Agent","tool_input":{"subagent_type":"advisor","model":"opus","prompt":"p"}}'            "advisor is the one exception, whatever model"
run deny  '{"tool_name":"Agent","tool_input":{"subagent_type":"fork","prompt":"p"}}'                              "fork (always the main model, Opus)"
run deny  '{"tool_name":"Agent","tool_input":{"subagent_type":"fork","model":"haiku","prompt":"p"}}'              "fork with a model named (ignored for forks)"
run deny  '{"tool_name":"Agent","tool_input":{"subagent_type":"general-purpose","model":"opus","prompt":"p"}}'    "opus"
run deny  '{"tool_name":"Agent","tool_input":{"subagent_type":"general-purpose","model":"Opus","prompt":"p"}}'    "Opus (any case)"
run deny  '{"tool_name":"Agent","tool_input":{"subagent_type":"implementer","model":"claude-opus-5-5","prompt":"p"}}' "full opus model id"
run deny  '{"tool_name":"Agent","tool_input":{"subagent_type":"general-purpose","model":"opusplan","prompt":"p"}}' "opusplan"
run deny  '{"tool_name":"Agent","tool_input":{"subagent_type":"general-purpose","model":"fable","prompt":"p"}}'   "fable outside the advisor"
run deny  '{"tool_name":"Task","tool_input":{"subagent_type":"Explore","model":"claude-fable-5-1","prompt":"p"}}' "full fable model id, legacy Task tool"
run allow '{"tool_name":"Agent","tool_input":{"subagent_type":"Explore","model":"claude-sonnet-5-5","prompt":"p"}}' "full sonnet model id"
run allow '{"tool_name":"Agent","tool_input":{"subagent_type":"tester","model":"claude-haiku-4-5-20251001","prompt":"p"}}' "full haiku model id"
run deny  '{"tool_name":"Workflow","tool_input":{"script":"export const meta={name:\"x\"}\nawait agent(\"p\", {label:\"a\", model: \"opus\"})"}}' "workflow: an agent on opus"
run deny  '{"tool_name":"Workflow","tool_input":{"script":"await agent(`p`, {model:`claude-fable-5-1`})"}}'     "workflow: an agent on a fable id (backticks)"
run deny  '{"tool_name":"Workflow","tool_input":{"script":"await agent(\"p\", {subagent_type: \"fork\"})"}}'      "workflow: a fork"
run allow '{"tool_name":"Workflow","tool_input":{"script":"await agent(\"p\", {model: \"sonnet\"}); await agent(\"q\", {model: \"haiku\"})"}}' "workflow: sonnet and haiku agents"
run allow '{"tool_name":"Workflow","tool_input":{"script":"// opus is mentioned in a comment only\nawait agent(\"p\", {model: \"sonnet\"})"}}' "workflow: opus in a comment, not a model"
WF="$(mktemp -d)"; printf 'await agent("p", {model: "opus"})\n' > "$WF/bad.js"; printf 'await agent("p", {model: "haiku"})\n' > "$WF/ok.js"
mkdir -p "$WF/home/.claude/workflows"; cp "$WF/bad.js" "$WF/home/.claude/workflows/saved-bad.js"
run deny  "{\"tool_name\":\"Workflow\",\"tool_input\":{\"scriptPath\":\"$WF/bad.js\"}}"                            "workflow by scriptPath, an opus agent"
run allow "{\"tool_name\":\"Workflow\",\"tool_input\":{\"scriptPath\":\"$WF/ok.js\"}}"                             "workflow by scriptPath, a haiku agent"
run deny  '{"tool_name":"Workflow","tool_input":{"name":"saved-bad"}}'                                            "saved workflow by name (~/.claude/workflows), an opus agent" HOME="$WF/home"
run allow '{"tool_name":"Workflow","tool_input":{"name":"no-such-workflow"}}'                                     "saved workflow not found: allowed (fail open)" HOME="$WF/home"
rm -rf "$WF"
run allow '{"tool_name":"Bash","tool_input":{"command":"ls"}}'                                                    "other tool"
run allow 'not json at all'                                                                                       "garbage payload fails open"
run allow ''                                                                                                      "empty payload fails open"
run allow '{"tool_name":"Agent","tool_input":{"subagent_type":"general-purpose","prompt":"p"}}'                   "escape hatch SUBAGENT_MODEL_GUARD=off" SUBAGENT_MODEL_GUARD=off

# The deny reason names the fix.
out="$(printf '%s' '{"tool_name":"Agent","tool_input":{"subagent_type":"Explore","prompt":"p"}}' | bash "$HOOK")"
if jq -e '.hookSpecificOutput.permissionDecisionReason | test("model: \"sonnet\"") and test("Explore")' <<<"$out" >/dev/null; then
  pass=$((pass+1)); echo "  ok   deny reason names the type and the fix"
else fail=$((fail+1)); echo "  FAIL deny reason: $out"; fi

# Launch ledger: a fake clock and a throwaway ledger dir.
L="$(mktemp -d)"
adv() { printf '{"session_id":"%s","tool_name":"Agent","tool_input":{"subagent_type":"advisor","prompt":"p"}}' "$1"; }
wk()  { printf '{"session_id":"%s","tool_name":"Agent","tool_input":{"subagent_type":"general-purpose","model":"sonnet","prompt":"p"}}' "$1"; }
LD="SUBAGENT_GUARD_LEDGER_DIR=$L"
run allow "$(adv A)" "advisor 1st in the session" "$LD" SUBAGENT_GUARD_NOW=1000
run allow "$(adv A)" "advisor 2nd"                "$LD" SUBAGENT_GUARD_NOW=1100
run deny  "$(adv A)" "advisor 3rd denied"         "$LD" SUBAGENT_GUARD_NOW=1200
run deny  "$(adv A)" "advisor 3rd still denied just inside the window" "$LD" SUBAGENT_GUARD_NOW=4500
run allow "$(adv A)" "advisor allowed again after the window" "$LD" SUBAGENT_GUARD_NOW=4700
run allow "$(adv B)" "another session's advisor is independent" "$LD" SUBAGENT_GUARD_NOW=1200
for i in 1 2 3 4 5; do run allow "$(adv '')" "no session_id: allowed ($i)" "$LD" SUBAGENT_GUARD_NOW=1200; done
for i in 1 2 3 4; do run allow "$(wk C)" "fan-out: agent $i of 4 allowed" "$LD" SUBAGENT_GUARD_NOW=$((5000+i)); done
run deny  "$(wk C)" "fan-out: 5th within 10 minutes denied" "$LD" SUBAGENT_GUARD_NOW=5100
run deny  "$(adv C)" "fan-out counts the advisor too" "$LD" SUBAGENT_GUARD_NOW=5100
run allow "$(wk D)" "fan-out: another session unaffected" "$LD" SUBAGENT_GUARD_NOW=5100
run allow "$(wk C)" "fan-out: allowed after the 10 minute window" "$LD" SUBAGENT_GUARD_NOW=5700
run deny  '{"session_id":"E","tool_name":"Agent","tool_input":{"subagent_type":"general-purpose","prompt":"p"}}' "a model-less call is still denied with a ledger" "$LD" SUBAGENT_GUARD_NOW=100
run allow "$(adv A)" "limits off with SUBAGENT_MODEL_GUARD=off" "$LD" SUBAGENT_GUARD_NOW=4800 SUBAGENT_MODEL_GUARD=off
for i in 1 2 3 4 5 6; do run allow '{"session_id":"F","tool_name":"Workflow","tool_input":{"script":"x"}}' "workflow calls are not counted ($i)" "$LD" SUBAGENT_GUARD_NOW=100; done
run allow "$(wk G)" "unwritable ledger dir fails open" SUBAGENT_GUARD_LEDGER_DIR=/proc/nope/x SUBAGENT_GUARD_NOW=100
rm -rf "$L"

echo "subagent-model-guard: $pass passed, $fail failed"
[ "$fail" -eq 0 ]
