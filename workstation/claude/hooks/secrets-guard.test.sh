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

# A provider shape only gitleaks knows (no regex above matches sk_live_…). Skipped without gitleaks.
if command -v gitleaks >/dev/null 2>&1; then
  ST="sk_""live_"; SV="51HxY2bKfP4qR8sT6uV9wZ0aB3cD5eF7gH"
  printf 'stripe = %s%s\n' "$ST" "$SV" > st.txt; git add st.txt
  run deny  "git commit -m x"         "staged Stripe live key (gitleaks rule)"; git reset -q st.txt; rm -f st.txt
  printf 'clean line, nothing secret\n' > gl.txt; git add gl.txt
  run allow "git commit -m x"         "clean change with gitleaks present"; git reset -q gl.txt; rm -f gl.txt
  # The repo's own .gitleaks.toml applies, and an allowlist anchored at the line's start matches the line as the
  # file holds it: gitleaks reads the added lines without the diff's leading `+` (2026-11-13: an allowance had to
  # be written `^\+?` to match). Allowed is that one line only; the same key on another line is still found.
  printf '[extend]\nuseDefault = true\n[[allowlists]]\nregexTarget = "line"\nregexes = ['"'(?m)^stripe = %s%s$'"']\n' \
    "$ST" "$SV" > .gitleaks.toml
  printf 'stripe = %s%s\n' "$ST" "$SV" > st.txt; git add st.txt
  run allow "git commit -m x"         "repo allowlist anchored at ^ matches the added line"; git reset -q st.txt; rm -f st.txt
  printf 'other = %s%s\n' "$ST" "$SV" > st.txt; git add st.txt
  run deny  "git commit -m x"         "repo allowlist: the key on another line is still found"; git reset -q st.txt; rm -f st.txt
  rm -f .gitleaks.toml
fi

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

# The repo the command targets, not the session cwd (2026-11-04: `cd worktree && git push`
# from a session sitting in another checkout was scanned against that other checkout).
run_in() {  # run_in <cwd> <expect> <command> <label>
  local d="$1" expect="$2" cmd="$3" label="$4" payload out got
  payload="$(jq -n --arg c "$cmd" --arg d "$d" '{tool_name:"Bash",tool_input:{command:$c},cwd:$d}')"
  out="$(printf '%s' "$payload" | bash "$HOOK" 2>/dev/null)"
  got="allow"; printf '%s' "$out" | grep -Eq '"permissionDecision":[[:space:]]*"deny"' && got="deny"
  if [ "$got" = "$expect" ]; then pass=$((pass+1)); printf '  ok   [%s] %s\n' "$got" "$label"
  else fail=$((fail+1)); printf '  FAIL exp=%s got=%s : %s\n' "$expect" "$got" "$label"; fi
}
C="$R.clean"; rm -rf "$C" "$C.remote.git"; git init -q "$C"
( cd "$C" && git config user.email t@t && git config user.name t && git commit -q --allow-empty -m init \
  && git clone -q --bare . "$C.remote.git" && git remote add origin "$C.remote.git" \
  && git push -q -u origin "$(git branch --show-current)" \
  && printf 'clean\n' > c.txt && git add c.txt && git commit -q -m clean )
printf '%s\n' "${GL}ABCDEFGHIJKLMNOP12345" > leak.txt; git add leak.txt; git commit -q -m 'leak'
run_in "$R" allow "cd $C && git push origin HEAD"      "cd into a clean repo: not the cwd repo's leak"
run_in "$C" deny  "cd $R && git push origin $BR"       "cd into the repo holding the leak"
run_in "$R" allow "git -C $C push origin HEAD"         "git -C a clean repo"
run_in "$C" deny  "git -C '$R' push origin $BR"        "git -C (quoted) the repo holding the leak"
git reset -q --hard HEAD~1

# A rebased branch brings main's commits, which are already on the remote: only the branch's own
# commits are new, so a secret-shaped line in main's (published) history must not block the push.
git checkout -q -b feature; printf 'f1\n' > f.txt; git add f.txt; git commit -q -m f1
git push -q -u origin feature
git checkout -q "$BR"; printf '%s\n' "${GL}ABCDEFGHIJKLMNOP12345" > pub.txt; git add pub.txt
git commit -q -m 'already published'; git push -q origin "$BR"
git checkout -q feature; git rebase -q "$BR"
run allow "git push --force-with-lease origin feature" "rebased branch: main's published commits are not re-scanned"
printf '%s\n' "${GH}ABCDEFGHIJKLMNOPQRST1234567890" > own.txt; git add own.txt; git commit -q -m own
run deny  "git push --force-with-lease origin feature" "rebased branch: its own new commit is still scanned"
git checkout -q "$BR"; rm -rf "$C" "$C.remote.git"

# Where the git command runs, followed through the command (2026-11-05 review of the first fix,
# which scanned only the first cd / -C and failed open on these). D holds an unpushed secret,
# K is clean; both push to their own bare remote.
X="$R.x"; rm -rf "$X"; mkdir -p "$X"
mkr() {  # mkr <dir>: a repo with one published commit on origin
  git init -q --bare "$1.git"; git init -q "$1"
  ( cd "$1" && git config user.email t@t && git config user.name t && git commit -q --allow-empty -m init \
    && git remote add origin "$1.git" && git push -q origin HEAD:main && git fetch -q origin )
}
mkr "$X/D"; mkr "$X/K"
printf 'k = %s\n' "${AK}${H16}" > "$X/D/s.txt"; git -C "$X/D" add s.txt; git -C "$X/D" commit -q -m s
run_in "$X/D" deny  "cd $X/K && cd $X/D && git push"          "two cds: the last one is where the push runs"
run_in "$X/D" deny  "cd $X/K && git -C $X/D push"             "cd clean, then git -C the dirty repo"
run_in "$X/D" deny  "git -C $X/K status && git push"          "-C of an earlier git command does not move the push"
run_in "$X/D" deny  "cd $X/nowhere; git push"                 "cd to a missing dir: the cwd is still scanned"
run_in "$X/D" deny  "for r in a; do cd $X/\$r && git push; done" "cd \$var: unknown dir, the cwd is still scanned"
run_in "$X/K" deny  "bash -c \"cd $X/D && git push\""         "bash -c: a dir named inside the quotes is scanned"
run_in "$X/K" allow "(cd $X/D) && git push"                   "a subshell's cd ends at its )"
run_in "$X/D" deny  "(cd $X/K) && git push"                   "a subshell's cd ends at its ) (dirty cwd)"
run_in "$X/K" allow "git -c x.y=1 -c 'credential.helper=!gh auth git-credential' push origin HEAD:main" \
                                                               "git -c (lower case) is not -C"
# a commit that only a second remote has is not published for the remote being pushed to
git init -q --bare "$X/fork.git"; git -C "$X/D" remote add fork "$X/fork.git"
git -C "$X/D" push -q fork HEAD:wip; git -C "$X/D" fetch -q fork
run_in "$X/D" deny  "git push origin HEAD:main"               "secret on fork/wip only, push to origin"
run_in "$X/D" deny  "git push -q $X/D.git HEAD:feat/x"        "push to a URL is matched to the remote it names"
run_in "$X/D" allow "git push fork HEAD:wip"                  "nothing new for the remote that has it"
git -C "$X/D" reset -q --hard origin/main
# a secret added only in a merge commit
( cd "$X/D" && git checkout -q -b side && echo a > a && git add a && git commit -q -m a && git checkout -q - \
  && echo b > b && git add b && git commit -q -m b && git merge -q --no-commit side ) 2>/dev/null
printf 'k = %s\n' "${AK}${H16}" > "$X/D/m.txt"; git -C "$X/D" add m.txt; git -C "$X/D" commit -q -m merge
run_in "$X/D" deny  "git push origin HEAD:main"               "secret only in a merge commit (--cc)"
git -C "$X/D" reset -q --hard origin/main
# a separate repo nested in the cwd's tree, pushed through a shell-variable URL
mkr "$X/K/apps/common"; echo d > "$X/K/apps/common/doc.md"; git -C "$X/K/apps/common" add doc.md
git -C "$X/K/apps/common" commit -q -m doc
NEST="cd $X/K/apps/common && U=$X/K/apps/common.git && git push -q \$U HEAD:main"
run_in "$X/K" allow "$NEST"                                   "nested repo, \$U URL, clean commit"
printf 'k = %s\n' "${AK}${H16}" > "$X/K/apps/common/s.md"; git -C "$X/K/apps/common" add s.md
git -C "$X/K/apps/common" commit -q -m s
run_in "$X/K" deny  "$NEST"                                   "nested repo, \$U URL, secret commit"
# a relative -C after a cd that cannot be resolved: tried against the cwd and every named dir
run_in "$X/K" deny  "cd \$Y && git -C apps/common push origin HEAD:main"           "relative -C after cd \$var, under the cwd"
run_in "$X/D" deny  "cd $X/K; cd \$Y && git -C apps/common push origin HEAD:main" "relative -C after cd \$var, under a named dir"
run_in "$X/D" allow "cd \$Y && git -C nowhere push origin HEAD:main"              "relative -C after cd \$var, nothing there, clean cwd"
# over the 64 KB pipe buffer: pipefail + `printf | grep -q` used to fail open (2026-11-05)
printf 'k = %s\n' "${AK}${H16}" > "$X/K/big.txt"; git -C "$X/K" add big.txt
BIG="$(head -c 100000 /dev/zero | tr '\0' x | fold -w 80)"
run_in "$X/K" deny  "git commit -F - <<'MSG'
$BIG
MSG"                                                           "100 KB command (heredoc message), staged secret"
git -C "$X/K" reset -q big.txt; rm -f "$X/K/big.txt"

# evh manifests (2026-11-05): an item id beside its sha256 is not a secret, only in an evh manifest,
# only in that exact shape, only when the id names no secret. The hash is built at runtime.
SHA="$( (printf x | sha256sum 2>/dev/null || printf x | shasum -a 256) | cut -d' ' -f1)"
mf() {  # mf <path> <line>: stage one line in a file at <path> in K
  mkdir -p "$X/K/$(dirname "$1")"; printf '{\n%s\n}\n' "$2" > "$X/K/$1"; git -C "$X/K" add "$1"
}
MAN=data/references/silver/filing_window_v1/manifest.json
mf "$MAN" "  \"api_key\": \"$SHA\","
run_in "$X/K" deny  "git commit -m x"                         "evh manifest: \"api_key\": <64 hex> is still caught"
git -C "$X/K" reset -q; rm -rf "$X/K/data"
if command -v gitleaks >/dev/null 2>&1; then
  ID="grafana_779e5ff58ed1e245_oom_compose""-api-1"
  mf "$MAN" "  \"$ID\": \"$SHA\","
  run_in "$X/K" allow "git commit -m x"                       "evh manifest: item id with \"api\" beside its sha256 (gitleaks false positive)"
  git -C "$X/K" reset -q; rm -rf "$X/K/data"
  mf data/datasets/fleet_v1.json "  \"$ID\": \"$SHA\","
  run_in "$X/K" allow "git commit -m x"                       "evh dataset file: the same line"
  git -C "$X/K" reset -q; rm -rf "$X/K/data"
  mf data/other/manifest.json "  \"$ID\": \"$SHA\","
  run_in "$X/K" deny  "git commit -m x"                       "the same line outside an evh manifest path is still scanned"
  git -C "$X/K" reset -q; rm -rf "$X/K/data"
  mf "$MAN" "  \"$ID\": \"${SHA}ab\","
  run_in "$X/K" deny  "git commit -m x"                       "evh manifest: a value that is not exactly 64 hex is still scanned"
  git -C "$X/K" reset -q; rm -rf "$X/K/data"
fi
# go.sum (2026-11-08): a module named like a secret beside its public checksum is not a secret, only in
# a file named go.sum and only in go.sum's exact shape. The hash is built at runtime.
H1="$(printf x | openssl dgst -sha256 -binary | base64)"
if [ "${#H1}" != 44 ]; then   # no silent skip: a missing helper must show as a failure
  fail=$((fail+1)); printf '  FAIL go.sum cases: could not build a 44-character h1 hash (openssl?)\n'
elif command -v gitleaks >/dev/null 2>&1; then
  gs() { mkdir -p "$X/K/$(dirname "$1")"; printf '%s\n' "$2" > "$X/K/$1"; git -C "$X/K" add "$1"; }
  gs go.sum "modernc.org/token v1.1.0 h1:$H1"
  run_in "$X/K" allow "git commit -m x"                       "go.sum: a module named token beside its checksum (gitleaks false positive)"
  git -C "$X/K" reset -q; rm -f "$X/K/go.sum"
  gs sub/go.sum "modernc.org/token v1.1.0/go.mod h1:$H1"
  run_in "$X/K" allow "git commit -m x"                       "go.sum in a subfolder, /go.mod line"
  git -C "$X/K" reset -q; rm -rf "$X/K/sub"
  gs notes.txt "modernc.org/token v1.1.0 h1:$H1"
  run_in "$X/K" deny  "git commit -m x"                       "the same line outside a go.sum is still scanned"
  git -C "$X/K" reset -q; rm -f "$X/K/notes.txt"
  gs go.sum "api_key = \"${AK}${H16}\""
  run_in "$X/K" deny  "git commit -m x"                       "go.sum: a key that is not a checksum line is still caught"
  git -C "$X/K" reset -q; rm -f "$X/K/go.sum"
  gs go.sum "modernc.org/token v1.1.0 h1:${H1%=}AB="   # 46 characters, still a gitleaks hit
  run_in "$X/K" deny  "git commit -m x"                       "go.sum: a hash that is not 44 characters is still scanned"
  git -C "$X/K" reset -q; rm -f "$X/K/go.sum"
fi
rm -rf "$X"

cp "$HOOK" ./hook-copy.sh; git add hook-copy.sh
run allow "git commit -m 'add hook'"  "hook's own regex source not self-flagged"; git reset -q hook-copy.sh; rm -f hook-copy.sh

echo; echo "RESULT: pass=$pass fail=$fail"
[ "$fail" = 0 ] || exit 1
