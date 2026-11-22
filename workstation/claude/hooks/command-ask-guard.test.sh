#!/usr/bin/env bash
# Tests for command-ask-guard.sh: each case feeds a PreToolUse payload and checks ask vs allow.
# Run: bash workstation/claude/hooks/command-ask-guard.test.sh   (exit 1 on any failure)
set -uo pipefail
H="$(cd "$(dirname "$0")" && pwd)/command-ask-guard.sh"
pass=0; fail=0
t() {   # $1 expected (ask|allow), $2 tool, $3 command
    local out got
    out="$(jq -n --arg t "$2" --arg c "$3" '{tool_name:$t, tool_input:{command:$c}}' | bash "$H")"
    got=allow; printf '%s' "$out" | grep -q '"permissionDecision": *"ask"' && got=ask
    if [ "$got" = "$1" ]; then pass=$((pass+1)); else fail=$((fail+1)); echo "FAIL want $1 got $got: [$2] $3"; fi
}
# pushes, through both tools, plain and compound
t ask   Bash                      "git push origin main"
t ask   mcp__lean-ctx__ctx_shell  "git push origin main"
t ask   mcp__lean-ctx__ctx_shell  "cd /work/x && git push --force-with-lease"
t ask   Bash                      "git -C /work/x push"
t ask   Bash                      "git fetch -q origin main && git rebase origin/main && git push origin HEAD:main"
t allow Bash                      "git status --short"
t allow Bash                      "git log --oneline origin/main..HEAD"
t allow Bash                      "echo 'remember to git-push later'"
t allow Bash                      "grep -n push README.md"
# issues
t ask   Bash                      "gh issue create --title x --body y"
t allow Bash                      "gh issue view 87 --repo chipi/x"
t allow Bash                      "gh issue close 172 --reason 'not planned'"
# destructive
t ask   Bash                      "rm -rf build/"
t ask   mcp__lean-ctx__ctx_shell  "cd /tmp && rm -fr cache"
t ask   Bash                      "rm -r -f dist"
t allow Bash                      "rm build/out.o"
t allow Bash                      "rm -f /tmp/x.json"
t ask   Bash                      "docker system prune -af"
t ask   Bash                      "docker volume prune"
t ask   Bash                      "docker volume rm data"
t ask   Bash                      "docker compose down -v"
t ask   Bash                      "docker compose -p x down --volumes"
t allow Bash                      "docker compose down"
t allow Bash                      "docker system df"
t ask   Bash                      "terraform apply -auto-approve"
t allow Bash                      "terraform plan"
# installs
t ask   Bash                      "pip install humanize"
t ask   mcp__lean-ctx__ctx_shell  "python3 -m pip install requests"
t ask   Bash                      "uv pip install -q --python .venv/bin/python pkg"
t ask   Bash                      "uv add httpx"
t ask   Bash                      "uv tool install harbor"
t ask   Bash                      "npm install -g typescript"
t ask   Bash                      "npm i -g pnpm"
t ask   Bash                      "brew install jq"
t allow Bash                      "npm install"
t allow Bash                      "npm ci"
t allow Bash                      "pip show evaluation-harness"
t allow Bash                      "uv venv .venv"
# 2026-11-22: text that only mentions a guarded command is not a command (the operator saw constant prompts;
# the fleet session's message draft below, which quoted "git push" lines, asked)
t allow Bash                      $'F=/tmp/claude-1000/p/s/scratchpad/msg.txt; cat > $F <<\'EOF\'\n- 6 asks, shape `cd <repo> && git push origin HEAD:main`.\nEOF\npython3 ~/.claude/skills/session-handoff-msg/scripts/lint_msg.py $F'
t allow Bash                      'git commit -m "docs: how to git push safely"'
t allow Bash                      'echo "never run docker volume rm here"'
t allow Bash                      'python3 x.py  # needs: pip install foo'
t allow Bash                      $'cat > x.sh <<\'EOF\'\nrm -rf "$HOME/x"\nEOF'
t allow Bash                      'd=$(mktemp -d); do_work "$d"; rm -rf "$d"'
t allow Bash                      'T="$(mktemp -d)" && trap '\''rm -rf "$T"'\'' EXIT; make -C "$T"'
t allow Bash                      "rm -rf /tmp/claude-$(id -u)/proj/session/scratchpad/egress-test"
t allow Bash                      "rm -rf /private/tmp/claude-$(id -u)/proj/session/scratchpad/x"
# ... and a real one next to or inside text that runs still asks
t ask   Bash                      'git commit -m "release" && git push origin main'
t ask   Bash                      $'cat > x.sh <<\'EOF\'\nrm -rf build\nEOF\nbash x.sh'
t ask   Bash                      $'bash <<\'EOF\'\ngit push origin main\nEOF'
t ask   Bash                      $'ssh host \'bash -s\' <<\'EOF\'\nrm -rf ~/data\nEOF'
t ask   Bash                      'bash -c "rm -rf /srv/data"'
t ask   Bash                      'ssh homelab "cd repo && git push origin main"'
t ask   Bash                      "sudo -u claude sh -c 'docker volume rm x'"
t ask   Bash                      'eval "git push origin main"'
t ask   Bash                      'echo "git push origin main" | sh'
t ask   Bash                      'd=$(mktemp -d); rm -rf "$d" "$HOME/data"'
t ask   Bash                      'rm -rf "$d"'
t ask   Bash                      "rm -rf /tmp/claude-$(id -u)/../../home/x"
t ask   Bash                      "rm -rf /tmp/other"
t ask   Bash                      'docker compose down -v # cleanup'
# other tools and the escape hatch
t allow Read                      "git push origin main"
out="$(jq -n '{tool_name:"Bash",tool_input:{command:"git push"}}' | COMMAND_ASK_GUARD=off bash "$H")"
[ -z "$out" ] && pass=$((pass+1)) || { fail=$((fail+1)); echo "FAIL escape hatch did not allow"; }
echo "command-ask-guard: $pass passed, $fail failed"
[ "$fail" -eq 0 ]
