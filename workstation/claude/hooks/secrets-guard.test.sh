#!/usr/bin/env bash
# Regression tests for secrets-guard.sh (the PreToolUse hook). Exercises the
# secret patterns, placeholder filter, commit/push detection, the -a/-am path,
# the push commit-range fallback, and the fail-open branches. No real secrets.
#
# NOTE: fake-secret fixtures are kept SPLIT into components (AK+H16, etc.) and
# assembled only at runtime, so this test file itself does not trip the live
# secrets-guard hook when committed. The full literals never appear in source.
#
# Run:  bash secrets-guard.test.sh   (exit 0 = all pass)
set -uo pipefail
HOOK="$(cd "$(dirname "$0")" && pwd)/secrets-guard.sh"
[ -x "$HOOK" ] || { echo "hook not found/executable: $HOOK"; exit 2; }
command -v jq >/dev/null || { echo "jq required for tests"; exit 2; }

# split fixture components — harmless on their own, assembled at runtime below
AK="AKIA"; H16="1234567890ABCDEF"; GH="ghp_"; GL="glpat-"
GV="abcdef1234567890ghij0"; PK="PRIVATE KEY-----"

R=/tmp/secrets_guard_test.$$
rm -rf "$R"; mkdir -p "$R"; cd "$R"
git init -q; git config user.email t@t; git config user.name t
git commit -q --allow-empty -m init
trap 'rm -rf "$R" "$R.remote.git"' EXIT

pass=0; fail=0
run() {  # run <expect: allow|deny> <command> <label>
  local expect="$1" cmd="$2" label="$3" payload out got
  payload="$(jq -n --arg c "$cmd" --arg d "$R" '{tool_name:"Bash",tool_input:{command:$c},cwd:$d}')"
  out="$(printf '%s' "$payload" | bash "$HOOK" 2>/dev/null)"
  got="allow"; printf '%s' "$out" | grep -Eq '"permissionDecision":[[:space:]]*"deny"' && got="deny"
  if [ "$got" = "$expect" ]; then pass=$((pass+1)); printf '  ok   [%s] %s\n' "$got" "$label"
  else fail=$((fail+1)); printf '  FAIL exp=%s got=%s : %s\n' "$expect" "$got" "$label"; fi
}

run allow "ls -la"                    "plain ls"
run allow "git status"                "git status (not commit/push)"
run allow "git log --oneline"         "git log"

printf 'hello\n' > a.txt; git add a.txt
run allow "git commit -m 'add a'"     "clean staged commit"

printf 'aws_key = %s\n' "${AK}${H16}" > sec.txt; git add sec.txt
run deny  "git commit -m x"           "staged AWS AKIA key"; git reset -q sec.txt; rm -f sec.txt
printf 'api_key = "%s"\n' "$GV" > s2.txt; git add s2.txt
run deny  "git commit -m x"           "staged generic api_key assignment"; git reset -q s2.txt; rm -f s2.txt
printf -- '-----BEGIN OPENSSH %s\n' "$PK" > k.txt; git add k.txt
run deny  "git commit -m x"           "staged private key block"; git reset -q k.txt; rm -f k.txt

printf 'api_key = ${MY_KEY}\n' > p.txt; git add p.txt
run allow "git commit -m x"           "placeholder \${MY_KEY}"; git reset -q p.txt; rm -f p.txt
printf 'token = "example_placeholder_value_here"\n' > p2.txt; git add p2.txt
run allow "git commit -m x"           "placeholder example/placeholder value"; git reset -q p2.txt; rm -f p2.txt

printf 'FOO=bar\n' > .env; git add .env
run deny  "git commit -m x"           "real .env staged"; git reset -q .env; rm -f .env
printf 'FOO=changeme\n' > .env.example; git add .env.example
run allow "git commit -m x"           ".env.example staged"; git reset -q .env.example; rm -f .env.example

printf 'clean\n' > tracked.txt; git add tracked.txt; git commit -q -m 'add tracked'
printf '%s\n' "${GH}ABCDEFGHIJKLMNOPQRST1234567890" >> tracked.txt   # modify, do NOT stage
run allow "git commit -m x"           "-a absent, nothing staged → allow"
run deny  "git commit -am x"          "-am secret in unstaged tracked file"
git checkout -q -- tracked.txt

rm -rf "$R.remote.git"; BR="$(git branch --show-current)"
git clone -q --bare "$R" "$R.remote.git"
git remote add origin "$R.remote.git"; git push -q -u origin "$BR"
run allow "git push origin $BR"       "push, nothing new outgoing"
printf '%s\n' "${GL}ABCDEFGHIJKLMNOP12345" > leak.txt; git add leak.txt; git commit -q -m 'leak'
run deny  "git push origin $BR"       "push with secret in unpushed commit"; git reset -q --hard HEAD~1

cp "$HOOK" ./hook-copy.sh; git add hook-copy.sh
run allow "git commit -m 'add hook'"  "hook's own regex source not self-flagged"; git reset -q hook-copy.sh; rm -f hook-copy.sh

echo; echo "RESULT: pass=$pass fail=$fail"
[ "$fail" = 0 ] || exit 1
