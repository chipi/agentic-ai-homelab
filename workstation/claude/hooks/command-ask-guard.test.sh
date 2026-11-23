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
# 2026-11-23, operator: a push of a feature branch needs no go; default branches, force and deletes still ask
t allow mcp__lean-ctx__ctx_shell  'cd /work/infra/wt-runsteps && git fetch -q origin && git rebase origin/main 2>&1 | tail -1 && git push --force-with-lease origin feat/corpus-migration-run-steps 2>&1 | tail -1'
t allow Bash                      'git push -u origin fix/guard-rm'
t allow Bash                      'git push -q origin HEAD:refs/heads/feat/x'
t allow Bash                      'git -C /work/x push origin chore/harness-v0.8.0'
t ask   Bash                      'git push origin'
t ask   Bash                      'git push -u origin HEAD'
t ask   Bash                      'git push origin master'
t ask   Bash                      'git push origin HEAD:refs/heads/main'
t ask   Bash                      'git push origin release/1.2'
t ask   Bash                      'git push -f origin feat/x'
t ask   Bash                      'git push --force origin feat/x'
t ask   Bash                      'git push origin +feat/x'
t ask   Bash                      'git push origin :feat/x'
t ask   Bash                      'git push origin --delete feat/x'
t ask   Bash                      'git push --all origin'
t ask   Bash                      'git push --tags origin'
t ask   Bash                      'git push origin feat/x main'
t ask   Bash                      'git push origin feat/x && git push origin main'
t ask   Bash                      'ssh host "cd r && git push origin feat/x"'
t ask   Bash                      $'printf \'git push origin feat/x\\n\' | sh'
# issues
t ask   Bash                      "gh issue create --title x --body y"
t allow Bash                      "gh issue view 87 --repo chipi/x"
t allow Bash                      "gh issue close 172 --reason 'not planned'"
# destructive
t ask   Bash                      "rm -rf src/"
t ask   mcp__lean-ctx__ctx_shell  "cd /tmp && rm -fr cache"
t ask   Bash                      "rm -r -f src"
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
# 2026-11-23: running a script file does not run the command's quoted text (this one asked)
t allow Bash                      'cd /tmp/s && sed -i '\''s|^t "#2" .*|t "#2" "$(printf "%s" "$C2" \| grep -v "git push -q -u")"|'\'' cases.sh && bash cases.sh'
t allow Bash                      'grep -n "rm -rf" README.md; bash scripts/check.sh'
t ask   Bash                      'bash -lc "git push origin main"'
t ask   Bash                      "sh -ec 'rm -rf /srv/data'"
t ask   Bash                      "printf 'git push origin main\\n' | bash"
# 2026-11-23 (operator): a script written by a heredoc and run in the same command is a script file like any
# other, not checked (a test script pushing to a throwaway local repo asked)
t allow Bash                      $'cat > t.sh <<\'EOF\'\nW="$(mktemp -d)"\ntrap \'rm -rf "$W"\' EXIT\ngit push -q origin HEAD:refs/heads/main\nEOF\nbash t.sh; echo EXIT=$?'
t allow Bash                      $'cat > x.sh <<\'EOF\'\nrm -rf build\nEOF\nbash x.sh'
# 2026-11-23: lean-ctx's rewrite `lean-ctx -c '...'` runs its argument: it is checked as the command itself
t ask   Bash                      $'/home/marko/.local/bin/lean-ctx -c \'S=/tmp/x\nrm -rf /work/t/run_steps4 && cp -a a b\''
t ask   Bash                      "lean-ctx -c 'git push origin main'"
t ask   Bash                      $'{ /home/marko/.local/bin/lean-ctx -c \'cd /w && git push\'\n} && pwd -P >| /home/marko/.cache/claude-tmp/claude-0b4f-cwd'
t ask   Bash                      "lean-ctx -c 'cd /w && sudo -u x sh -c '\\''docker volume rm y'\\'''"
t ask   Bash                      "lean-ctx -c 'git push origin main'; echo done"
t allow Bash                      "lean-ctx -c 'git status --short'"
t allow Bash                      $'lean-ctx -c \'git commit -q -F - <<\'\\\'\'EOF\'\\\'\'\nsee the git push docs\nEOF\''
t allow Bash                      "lean-ctx -c 'sed -i '\\''s|git push|x|'\\'' f && bash f'"
# ... and a real one next to or inside text that runs still asks
t ask   Bash                      'git commit -m "release" && git push origin main'
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
# 2026-11-23: generated-output folders (relative) and Claude temp areas on other hosts
t allow Bash                      'cd /work/eval-harness/worktrees/081/harness && rm -rf .build/f3-new; .venv/bin/python scripts/cli.py catalog --out .build/f3-new'
t allow Bash                      'rm -rf build dist node_modules .pytest_cache'
t allow Bash                      'rm -rf ./__pycache__ ./.mypy_cache'
t allow Bash                      $'timeout 60 ssh -i k host \'docker exec db psql -tAc "select 1"; rm -rf /tmp/claude-work/case3 && echo removed\''
t ask   Bash                      $'timeout 60 ssh -i k host \'rm -rf /tmp/case3\''
t ask   Bash                      'rm -rf .'
t ask   Bash                      'rm -rf ./'
t ask   Bash                      'rm -rf build/../src'
t ask   Bash                      'rm -rf build/*'
t ask   Bash                      'rm -rf src build'
t ask   Bash                      'rm -rf ~/build'
t ask   Bash                      'rm -rf /work/proj/build'
t ask   Bash                      'rm -rf .git'
t ask   Bash                      'rm -rf .venv'
t ask   Bash                      'rm -rf /tmp/claude-/x'
t allow Bash                      $'cd hooks && D=$(ssh -i ~/.ssh/k -o IdentitiesOnly=yes me@homelab \'mktemp -d\') && scp -q a b me@homelab:$D/ && timeout 120 ssh me@homelab "cd $D && bash t.sh; rm -rf \\"$D\\""'
t allow Bash                      $'D=$(timeout 30 ssh host mktemp -d); ssh host "rm -rf $D"'
t ask   Bash                      $'D=$(ssh host \'cat /etc/mktemp-list\'); ssh host "rm -rf $D"'
t ask   Bash                      $'D=$(ssh host \'echo /srv\'); ssh host "rm -rf $D"'
t ask   Bash                      'docker compose down -v # cleanup'
# other tools and the escape hatch
t allow Read                      "git push origin main"
out="$(jq -n '{tool_name:"Bash",tool_input:{command:"git push"}}' | COMMAND_ASK_GUARD=off bash "$H")"
[ -z "$out" ] && pass=$((pass+1)) || { fail=$((fail+1)); echo "FAIL escape hatch did not allow"; }
echo "command-ask-guard: $pass passed, $fail failed"
[ "$fail" -eq 0 ]
