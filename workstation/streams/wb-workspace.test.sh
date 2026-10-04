#!/usr/bin/env bash
# Tests for wb-workspace and the Worktrunk workspace hooks. Everything runs in a
# scratch dir: scratch repos under a scratch work root, a scratch HOME and
# Worktrunk config. /work is only read, to prove it is untouched.
#   bash workstation/streams/wb-workspace.test.sh
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CMD="$HERE/wb-workspace"; CONFIG="$HERE/../config/worktrunk/config.toml"
for c in git wt jq python3; do command -v "$c" >/dev/null || { echo "SKIP: $c not installed"; exit 0; }; done

T="$(mktemp -d)"; ROOT="$T/work"
cleanup() { [ -n "${LISTENER:-}" ] && kill "$LISTENER" 2>/dev/null; rm -rf "$T"; }
pass=0; fail=0
ok()  { echo "  ok   $1"; pass=$((pass+1)); }
bad() { echo "  FAIL $1"; fail=$((fail+1)); }
chk() { if eval "$2"; then ok "$1"; else bad "$1"; fi; }

REAL_HOME="$HOME"
real_state() {
  for d in /work/*/main; do
    [ -d "$d/.git" ] || continue
    echo "$d"; env -u GIT_CONFIG_GLOBAL HOME="$REAL_HOME" git -C "$d" status --porcelain
    env -u GIT_CONFIG_GLOBAL HOME="$REAL_HOME" git -C "$d" worktree list --porcelain
  done
}
REAL_BEFORE="$(real_state)"

# --- isolation -----------------------------------------------------------------
export HOME="$T/home" GIT_CONFIG_GLOBAL="$T/home/.gitconfig"
export WORKTRUNK_APPROVALS_PATH="$T/approvals.toml" WORKTRUNK_CONFIG_PATH="$T/wt.toml" WB_WORK_ROOT="$ROOT"
export PATH="$HERE:$PATH"            # hooks resolve wb-workspace to this repo's copy
unset WB_WT WORKTRUNK_DIRECTIVE_CD_FILE WORKTRUNK_DIRECTIVE_EXEC_FILE COMPOSE_PROJECT_NAME
mkdir -p "$HOME"; trap cleanup EXIT
git config --global user.name test; git config --global user.email test@example.invalid
git config --global init.defaultBranch trunk
parts=$(( $(printf '%s' "$ROOT/p/main" | tr -cd '/' | wc -c) + 1 ))
sed -e "s#'/work/'#'$ROOT/'#" -e "s#length) == 4 #length) == $parts #" "$CONFIG" > "$WORKTRUNK_CONFIG_PATH"
grep -q "'$ROOT/'" "$WORKTRUNK_CONFIG_PATH" || { echo "could not adapt $CONFIG"; exit 1; }

mkrepo() { mkdir -p "$1"; git -C "$1" init -q; git -C "$1" commit -q --allow-empty -m init; }
run()    { local d=$1; shift; (cd "$d" && "$CMD" "$@") > "$T/out" 2> "$T/err"; echo $?; }
val()    { grep "^$1=" "$T/out" | cut -d= -f2-; }

P="$ROOT/proj/main"; mkrepo "$P"; mkdir -p "$ROOT/proj/worktrees"
git -C "$P" worktree add -q -b s1 "$ROOT/proj/worktrees/s1"
W="$ROOT/proj/worktrees/s1"

echo "== identity"
rc=$(run "$P" env)
chk "primary: exit 0, stream main, id proj-main, primary = path" \
  "[ $rc = 0 ] && [ \"\$(val WORKSPACE_PROJECT)\" = proj ] && [ \"\$(val WORKSPACE_STREAM)\" = main ] && [ \"\$(val WORKSPACE_ID)\" = proj-main ] && [ \"\$(val WORKSPACE_PRIMARY)\" = '$P' ] && [ \"\$(val WORKSPACE_PATH)\" = '$P' ] && [ \"\$(val COMPOSE_PROJECT_NAME)\" = proj-main ]"
rc=$(run "$W" env)
chk "side worktree: stream s1, primary is main, path is the worktree" \
  "[ $rc = 0 ] && [ \"\$(val WORKSPACE_STREAM)\" = s1 ] && [ \"\$(val WORKSPACE_ID)\" = proj-s1 ] && [ \"\$(val WORKSPACE_PRIMARY)\" = '$P' ] && [ \"\$(val WORKSPACE_PATH)\" = '$W' ] && [ \"\$(val COMPOSE_PROJECT_NAME)\" = proj-s1 ]"
mkdir -p "$W/deep/dir"; rc=$(run "$W/deep/dir" env)
chk "from a subdirectory: same identity as the worktree root" "[ $rc = 0 ] && [ \"\$(val WORKSPACE_PATH)\" = '$W' ]"

echo "== invalid paths: env and port refuse, setup/teardown do nothing"
mkdir -p "$T/plain"; mkrepo "$ROOT/flat"; mkrepo "$T/elsewhere/proj/main"
mkrepo "$ROOT/other/main"; git -C "$ROOT/other/main" worktree add -q -b x "$ROOT/proj/worktrees/foreign"
mkrepo "$ROOT/proj/worktrees/standalone"; mkrepo "$ROOT/a/b/main"
for d in "$T/plain" "$ROOT/flat" "$T/elsewhere/proj/main" "$ROOT/proj/worktrees/foreign" "$ROOT/proj/worktrees/standalone" "$ROOT/a/b/main"; do
  label=${d#"$T"/}
  rc=$(run "$d" env);  chk "env refuses $label (exit $rc)" "[ $rc = 1 ] && grep -q 'not a Model-B checkout' '$T/err'"
  rc=$(run "$d" port web); chk "port refuses $label" "[ $rc = 1 ]"
  mkdir -p "$d/.config/workspace"; printf '#!/bin/sh\ntouch "%s/ran"\n' "$d" > "$d/.config/workspace/setup"; chmod +x "$d/.config/workspace/setup"
  rc=$(run "$d" setup); chk "setup in $label: exit 0, project script NOT run" "[ $rc = 0 ] && [ ! -e '$d/ran' ] && grep -q 'not a Model-B checkout' '$T/err'"
done
rc=$(cd "$T" && "$CMD" teardown > /dev/null 2>&1; echo $?); chk "teardown outside Git: exit 0" "[ $rc = 0 ]"
mkrepo "$ROOT/bad+name/main"; rc=$(run "$ROOT/bad+name/main" env)
chk "Model-B path with an unusable project name: exit 1, names the problem" "[ $rc = 1 ] && grep -q \"unsupported project name 'bad+name'\" '$T/err'"
rc=$(run "$ROOT/bad+name/main" setup); chk "… and setup fails closed for it" "[ $rc = 1 ]"

echo "== Compose project names"
mkrepo "$ROOT/My.Proj/main"; mkdir -p "$ROOT/My.Proj/worktrees"
git -C "$ROOT/My.Proj/main" worktree add -q -b Feat_X "$ROOT/My.Proj/worktrees/Feat_X"
rc=$(run "$ROOT/My.Proj/worktrees/Feat_X" env)
chk "My.Proj + Feat_X → my-proj-feat_x (lowercase, '.' → '-', '_' kept)" "[ $rc = 0 ] && [ \"\$(val COMPOSE_PROJECT_NAME)\" = my-proj-feat_x ] && [ \"\$(val WORKSPACE_ID)\" = My.Proj-Feat_X ]"
mkrepo "$ROOT/_lead/main"; rc=$(run "$ROOT/_lead/main" env)
chk "name starting with '_' (no valid Compose name start): refused, exit 1" "[ $rc = 1 ] && grep -q 'unsupported project name' '$T/err'"
mkrepo "$ROOT/x-y/main"; mkrepo "$ROOT/x/main"; mkdir -p "$ROOT/x/worktrees"
git -C "$ROOT/x/main" worktree add -q -b y-main "$ROOT/x/worktrees/y-main"
rc=$(run "$ROOT/x/worktrees/y-main" setup)
chk "two checkouts deriving the same name (x + y-main, x-y + main): setup refuses" "[ $rc = 1 ] && grep -q \"Compose project name 'x-y-main' is also derived\" '$T/err'"
git -C "$ROOT/x/main" worktree remove --force "$ROOT/x/worktrees/y-main"; rm -rf "$ROOT/x-y" "$ROOT/x"

echo "== ports"
rc=$(run "$W" port web e2e lab); ports1=$(cat "$T/out")
rc2=$(run "$W" port web e2e lab); ports2=$(cat "$T/out")
chk "three slots: exit 0, three ports, deterministic across runs" "[ $rc = 0 ] && [ $rc2 = 0 ] && [ \$(printf '%s\n' \"$ports1\" | wc -l) = 3 ] && [ \"$ports1\" = \"$ports2\" ]"
want=$(cd "$W" && wt step eval '{{ "proj/s1/web" | hash_port }}')
chk "port = Worktrunk hash_port(\"<project>/<stream>/<slot>\")" "[ \"\$(printf '%s\n' \"$ports1\" | head -1)\" = '$want' ]"
chk "ports in hash_port's range 10000-19999" "printf '%s\n' \"$ports1\" | awk '\$1<10000||\$1>19999{e=1} END{exit e}'"
rc=$(run "$P" port web); pm=$(cat "$T/out")
chk "different stream, same slot → different port" "[ $rc = 0 ] && [ '$pm' != \"\$(printf '%s\n' \"$ports1\" | head -1)\" ]"
rc=$(run "$W" port web); chk "single slot prints just the port" "[ $rc = 0 ] && [ \"\$(cat '$T/out')\" = \"\$(printf '%s\n' \"$ports1\" | head -1)\" ]"
rc=$(run "$W" port); chk "no slot: usage (exit 2)" "[ $rc = 2 ]"
rc=$(run "$W" port Web); chk "invalid slot name: exit 2" "[ $rc = 2 ] && grep -q \"invalid slot name 'Web'\" '$T/err'"
rc=$(run "$W" port web web); chk "same slot twice: exit 2" "[ $rc = 2 ] && grep -q 'requested twice' '$T/err'"

mkdir -p "$T/stub"
# Stub Worktrunk: each line of the template becomes a port from $T/stub/map ("<key> <port>"), else 20000.
cat > "$T/stub/wt" <<'EOF'
#!/usr/bin/env bash
tpl=${@: -1}
while IFS= read -r line; do
  [ -n "$line" ] || continue
  key=$(printf '%s' "$line" | sed -E 's/.*"([^"]*)".*/\1/')
  p=$(awk -v k="$key" '$1==k{print $2}' "$STUB_MAP"); echo "${p:-20000}"
done <<<"$tpl"
EOF
chmod +x "$T/stub/wt"; export STUB_MAP="$T/stub/map"
printf 'proj/s1/web 15001\nproj/s1/e2e 15001\n' > "$STUB_MAP"
rc=$( (cd "$W" && WB_WT="$T/stub/wt" "$CMD" port web e2e) > "$T/out" 2> "$T/err"; echo $?)
chk "two slots of one checkout collide: exit 3, nothing printed, both slots named" "[ $rc = 3 ] && [ ! -s '$T/out' ] && grep -q \"slots 'web' and 'e2e' both hash to 15001\" '$T/err'"
printf 'proj/s1/web 15002\nproj/s1/e2e 15003\nproj/main/e2e 15002\n' > "$STUB_MAP"
rc=$( (cd "$W" && WB_WT="$T/stub/wt" "$CMD" port web e2e) > "$T/out" 2> "$T/err"; echo $?)
chk "collides with another checkout's slot: exit 3, names that checkout, no other port picked" "[ $rc = 3 ] && [ ! -s '$T/out' ] && grep -q \"slot 'web' of proj-s1 hashes to 15002, as does $P (e2e); resolve the collision explicitly\" '$T/err' && ! grep -qi 'rename' '$T/err'"
printf 'proj/s1/web 15004\n' > "$STUB_MAP"
rc=$( (cd "$W" && WB_WT="$T/stub/wt" "$CMD" port web) > "$T/out" 2> "$T/err"; echo $?)
chk "stub without collisions: exit 0, its port" "[ $rc = 0 ] && [ \"\$(cat '$T/out')\" = 15004 ]"

# A real host listener on the port the stub hands out.
LPORT=$(python3 -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1",0)); print(s.getsockname()[1]); s.close()')
python3 -m http.server "$LPORT" --bind 127.0.0.1 >/dev/null 2>&1 & LISTENER=$!
for _ in $(seq 50); do ss -Hltn | grep -q ":$LPORT\b" && break; sleep 0.1; done
printf 'proj/s1/web %s\n' "$LPORT" > "$STUB_MAP"
rc=$( (cd "$W" && WB_WT="$T/stub/wt" "$CMD" port web) > "$T/out" 2> "$T/err"; echo $?)
chk "port with a host listener: reported on stderr, still exit 0 (it may be this checkout's own server)" "[ $rc = 0 ] && [ \"\$(cat '$T/out')\" = $LPORT ] && grep -q 'already has a listener' '$T/err'"
rc=$( (cd "$W" && WB_WT="$T/stub/wt" "$CMD" port --require-free web) > "$T/out" 2> "$T/err"; echo $?)
chk "--require-free with a listener: exit 4, nothing printed" "[ $rc = 4 ] && [ ! -s '$T/out' ]"
kill "$LISTENER" 2>/dev/null; LISTENER=""
printf '#!/bin/sh\nexit 9\n' > "$T/stub/wt-broken"; chmod +x "$T/stub/wt-broken"
rc=$( (cd "$W" && WB_WT="$T/stub/wt-broken" "$CMD" port web) > /dev/null 2> "$T/err"; echo $?)
chk "Worktrunk failure: exit 1, says so" "[ $rc = 1 ] && grep -q 'could not evaluate hash_port' '$T/err'"

echo "== setup/teardown dispatch"
mkdir -p "$W/.config/workspace"
for a in setup teardown; do
  cat > "$W/.config/workspace/$a" <<EOF
#!/usr/bin/env bash
{ echo "action=$a args=\$* cwd=\$PWD"; env | grep -E '^(WORKSPACE_|COMPOSE_PROJECT_NAME=)' | sort; } > "$T/$a.env"
cat > "$T/$a.stdin"
exit \${EXIT_WITH:-0}
EOF
  chmod +x "$W/.config/workspace/$a"
done
JSON='{"hook_type":"pre-start","branch":"s1","worktree_path":"'"$W"'"}'
for a in setup teardown; do
  rc=$( (cd "$W/deep" && printf '%s' "$JSON" | "$CMD" $a one "two words") > /dev/null 2>&1; echo $?)
  chk "$a: runs the project script from the worktree root with its args" "[ $rc = 0 ] && grep -qx 'action=$a args=one two words cwd=$W' '$T/$a.env'"
  chk "$a: script sees the full identity" "grep -qx 'WORKSPACE_STREAM=s1' '$T/$a.env' && grep -qx 'WORKSPACE_PRIMARY=$P' '$T/$a.env' && grep -qx 'WORKSPACE_PATH=$W' '$T/$a.env' && grep -qx 'WORKSPACE_ID=proj-s1' '$T/$a.env' && grep -qx 'WORKSPACE_PROJECT=proj' '$T/$a.env' && grep -qx 'COMPOSE_PROJECT_NAME=proj-s1' '$T/$a.env'"
  chk "$a: stdin reaches the project script byte for byte" "[ \"\$(cat '$T/$a.stdin')\" = '$JSON' ]"
  rc=$( (cd "$W" && EXIT_WITH=7 "$CMD" $a </dev/null) >/dev/null 2>&1; echo $?)
  chk "$a: project script failure propagates (exit 7)" "[ $rc = 7 ]"
done
chmod -x "$W/.config/workspace/setup"; rc=$(run "$W" setup)
chk "setup script present but not executable: exit 1, says so" "[ $rc = 1 ] && grep -q 'exists but is not executable' '$T/err'"
rm -rf "$W/.config"; rc=$(run "$W" setup); rc2=$(run "$W" teardown)
chk "no project scripts: setup and teardown exit 0 with a note" "[ $rc = 0 ] && [ $rc2 = 0 ] && grep -q 'has no .config/workspace/teardown' '$T/err'"
rc=$(run "$W" bogus); chk "unknown command: usage (exit 2)" "[ $rc = 2 ]"

echo "== Worktrunk integration (tracked config, real wt)"
# The project scripts are committed on the primary branch, so new worktrees carry them.
mkdir -p "$P/.config/workspace"
cat > "$P/.config/workspace/setup" <<EOF
#!/usr/bin/env bash
{ echo "cwd=\$PWD stream=\$WORKSPACE_STREAM compose=\$COMPOSE_PROJECT_NAME"; } >> "$T/hook.log"
cat > "$T/hook-setup.json"
[ "\$WORKSPACE_STREAM" != fail-setup ]
EOF
cat > "$P/.config/workspace/teardown" <<EOF
#!/usr/bin/env bash
echo "teardown stream=\$WORKSPACE_STREAM exists=\$([ -d "\$WORKSPACE_PATH" ] && echo yes || echo no)" >> "$T/hook.log"
cat > "$T/hook-teardown.json"
[ ! -e "\$WORKSPACE_PATH/keep-me" ]
EOF
chmod +x "$P/.config/workspace/setup" "$P/.config/workspace/teardown"
git -C "$P" add .config && git -C "$P" commit -q -m 'workspace scripts'
: > "$T/hook.log"
rc=$( (cd "$P" && wt switch --create feat/a --base @ --no-cd) >/dev/null 2>&1; echo $?)
chk "wt switch --create: exit 0, pre-start ran the project setup in the new worktree" \
  "[ $rc = 0 ] && grep -qx 'cwd=$ROOT/proj/worktrees/feat-a stream=feat-a compose=proj-feat-a' '$T/hook.log'"
chk "setup received Worktrunk's hook JSON on stdin (hook_type pre-start, branch feat/a)" \
  "jq -e '.hook_type == \"pre-start\" and .branch == \"feat/a\" and .worktree_path == \"$ROOT/proj/worktrees/feat-a\"' '$T/hook-setup.json' >/dev/null"
rc=$( (cd "$P" && wt switch --create fail-setup --base @ --no-cd) >/dev/null 2>&1; echo $?)
chk "failing project setup: wt exits non-zero, worktree kept (Worktrunk does not roll back)" "[ $rc != 0 ] && [ -d '$ROOT/proj/worktrees/fail-setup' ]"
touch "$ROOT/proj/worktrees/feat-a/keep-me"; echo keep-me >> "$P/.git/info/exclude"   # ignored: only the teardown can block removal
rc=$( (cd "$P" && wt remove feat/a) >/dev/null 2> "$T/rm.err"; echo $?)
chk "failing project teardown: removal stopped, worktree still there, Worktrunk names the pre-remove hook" "[ $rc != 0 ] && [ -d '$ROOT/proj/worktrees/feat-a' ] && grep -q 'pre-remove' '$T/rm.err'"
rm "$ROOT/proj/worktrees/feat-a/keep-me"; : > "$T/hook.log"
rc=$( (cd "$P" && wt remove feat/a) >/dev/null 2>&1; echo $?); sleep 1
chk "wt remove: teardown ran while the worktree still existed, then it was removed" \
  "[ $rc = 0 ] && grep -qx 'teardown stream=feat-a exists=yes' '$T/hook.log' && [ ! -e '$ROOT/proj/worktrees/feat-a' ]"
chk "teardown received the hook JSON (hook_type pre-remove)" "jq -e '.hook_type == \"pre-remove\"' '$T/hook-teardown.json' >/dev/null"
mkrepo "$T/code/elsewhere"; : > "$T/hook.log"
rc=$( (cd "$T/code/elsewhere" && wt switch --create side --no-cd) >/dev/null 2>&1; echo $?)
chk "repo outside Model-B: hooks are harmless no-ops, worktree created as before" "[ $rc = 0 ] && [ -d '$T/code/elsewhere.side' ] && [ ! -s '$T/hook.log' ]"

echo "== real state untouched"
chk "/work primary checkouts (status, worktrees) unchanged" "[ \"\$(real_state)\" = \"\$REAL_BEFORE\" ]"

echo; echo "RESULT: pass=$pass fail=$fail"
[ "$fail" = 0 ]
