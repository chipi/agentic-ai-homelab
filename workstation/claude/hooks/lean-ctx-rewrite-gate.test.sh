#!/usr/bin/env bash
# Regression tests for lean-ctx-rewrite-gate.sh. Run: bash lean-ctx-rewrite-gate.test.sh (exit 0 = all pass)
# Needs jq and lean-ctx on PATH: "rewritten" means lean-ctx's own hook answered with an updatedInput.
set -uo pipefail
HOOK="$(cd "$(dirname "$0")" && pwd)/lean-ctx-rewrite-gate.sh"
command -v jq >/dev/null || { echo "jq required"; exit 2; }
command -v lean-ctx >/dev/null || { echo "lean-ctx required"; exit 2; }

WT=/work/x/.claude/worktrees/agent-a1
pass=0; fail=0
run() {  # run <expect: passthrough|rewritten> <cwd> <command> <label>
  local expect="$1" cwd="$2" cmd="$3" label="$4" out got
  out="$(jq -cn --arg c "$cmd" --arg d "$cwd" '{tool_name:"Bash",hook_event_name:"PreToolUse",cwd:$d,tool_input:{command:$c}}' \
    | bash "$HOOK" 2>/dev/null)"
  got=passthrough; printf '%s' "$out" | grep -q '"updatedInput"' && got=rewritten
  if [ "$got" = "$expect" ]; then pass=$((pass+1)); printf '  ok   [%s] %s\n' "$got" "$label"
  else fail=$((fail+1)); printf '  FAIL exp=%s got=%s : %s\n' "$expect" "$got" "$label"; fi
}

run passthrough "$WT"           'git status --short'                          "bare git in an agent worktree"
run passthrough "$WT"           'git status --short; echo b'                  "git chained with another command"
run passthrough "$WT"           'echo c $(git rev-parse --short HEAD)'        "git inside a substitution"
run passthrough "$WT/src"       'cd .. && git commit -q -F /tmp/m'            "a subfolder of the worktree"
run passthrough "$WT"           '/usr/bin/git add -u'                         "git by its path"
run rewritten   "$WT"           'npm test'                                    "no git in an agent worktree: lean-ctx as before"
run rewritten   "$WT"           'cat .gitignore'                              "a .git* file name is not git"
run rewritten   "$WT"           'grep -r digit src'                           "a word ending in git is not git"
run rewritten   /work/orrery/main 'git status --short'                        "git outside an agent worktree: lean-ctx as before"
run rewritten   /work/x/worktrees/081 'git log -1'                            "a hand-made worktree: lean-ctx as before"
run passthrough /work/orrery/main 'echo hi'                                   "lean-ctx's own pass-through (echo) is kept"

printf '\n%d passed, %d failed\n' "$pass" "$fail"
[ "$fail" -eq 0 ]
