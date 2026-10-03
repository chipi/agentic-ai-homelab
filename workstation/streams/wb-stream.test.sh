#!/usr/bin/env bash
# Tests for wb-stream and the Model-B Worktrunk template. Everything runs in a
# scratch dir: scratch repos under a scratch work root, a private tmux server
# (TMUX_TMPDIR), a scratch HOME and Worktrunk config. /work and the real tmux
# server are only read, to prove they are untouched.
#   bash workstation/streams/wb-stream.test.sh
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CMD="$HERE/wb-stream"; CONFIG="$HERE/../config/worktrunk/config.toml"
for c in git wt tmux jq; do command -v "$c" >/dev/null || { echo "SKIP: $c not installed"; exit 0; }; done

T="$(mktemp -d)"; ROOT="$T/work"
cleanup() { tmux kill-server 2>/dev/null; rm -rf "$T"; }
pass=0; fail=0
ok()  { echo "  ok   $1"; pass=$((pass+1)); }
bad() { echo "  FAIL $1"; fail=$((fail+1)); }
chk() { if eval "$2"; then ok "$1"; else bad "$1"; fi; }

# --- read-only snapshot of real state, to prove it is untouched ---------------
REAL_HOME="$HOME"
renv() { env -u TMUX_TMPDIR -u GIT_CONFIG_GLOBAL HOME="$REAL_HOME" "$@"; }   # the real environment
real_state() {
  for d in /work/*/main; do
    [ -d "$d/.git" ] || continue
    echo "$d"; renv git -C "$d" status --porcelain; renv git -C "$d" worktree list --porcelain
    renv git -C "$d" for-each-ref --format='%(refname)' refs/heads
  done
  renv tmux list-sessions -F '#{session_name} #{session_windows}' 2>/dev/null
}
REAL_BEFORE="$(real_state)"

# --- isolation -----------------------------------------------------------------
export HOME="$T/home" GIT_CONFIG_GLOBAL="$T/home/.gitconfig" TMUX_TMPDIR="$T/tmux"
export WORKTRUNK_APPROVALS_PATH="$T/approvals.toml" WORKTRUNK_CONFIG_PATH="$T/wt.toml" WB_WORK_ROOT="$ROOT"
export PATH="$HERE:$PATH"            # the config's workspace hooks resolve wb-workspace to this repo's copy
unset TMUX WORKTRUNK_DIRECTIVE_CD_FILE WORKTRUNK_DIRECTIVE_EXEC_FILE
mkdir -p "$HOME" "$TMUX_TMPDIR"; trap cleanup EXIT
git config --global user.name test; git config --global user.email test@example.invalid
git config --global init.defaultBranch trunk
# The tracked template, with its /work root swapped for the scratch root.
parts=$(( $(printf '%s' "$ROOT/p/main" | tr -cd '/' | wc -c) + 1 ))
sed -e "s#'/work/'#'$ROOT/'#" -e "s#length) == 4 #length) == $parts #" "$CONFIG" > "$WORKTRUNK_CONFIG_PATH"
grep -q "'$ROOT/'" "$WORKTRUNK_CONFIG_PATH" || { echo "could not adapt $CONFIG"; exit 1; }

mkrepo() { mkdir -p "$1"; git -C "$1" init -q; git -C "$1" commit -q --allow-empty -m init; }
P="$ROOT/proj/main"
mkrepo "$P"; mkdir -p "$ROOT/proj/worktrees"
git -C "$P" checkout -q -b primary-line                         # primary is NOT on main/trunk
git -C "$P" commit -q --allow-empty -m "primary-line work"
tmux new-session -d -s proj -n editor -c "$P"
tmux new-session -d -s other -n x -c "$T"

windows()  { tmux list-windows -t "=$1" -F '#{window_name}' | sort | tr '\n' ' '; }
sessions() { tmux list-sessions -F '#{session_name}' | sort | tr '\n' ' '; }
wts()      { git -C "$P" worktree list --porcelain | grep -c '^worktree '; }
heads()    { git -C "$P" for-each-ref --format='%(refname)' refs/heads | sort | tr '\n' ' '; }
run()      { (cd "$1" && shift && "$CMD" "$@") > "$T/out" 2>&1; echo $?; }

echo "== happy path: wb-stream map-fix from the primary checkout"
s0=$(sessions); w0=$(windows proj); o0=$(windows other)
rc=$(run "$P" map-fix); cat "$T/out" | sed 's/^/     /'
chk "exit 0" "[ $rc = 0 ]"
chk "worktree at <root>/proj/worktrees/map-fix" "[ -d '$ROOT/proj/worktrees/map-fix' ] && git -C '$P' worktree list --porcelain | grep -qx 'worktree $ROOT/proj/worktrees/map-fix'"
chk "branch map-fix based on the current primary branch (primary-line, not main/trunk)" \
  "[ \"\$(git -C '$P' merge-base map-fix primary-line)\" = \"\$(git -C '$P' rev-parse primary-line)\" ] && [ \"\$(git -C '$P' rev-parse map-fix)\" = \"\$(git -C '$P' rev-parse primary-line)\" ]"
chk "worktree is on branch map-fix" "[ \"\$(git -C '$ROOT/proj/worktrees/map-fix' branch --show-current)\" = map-fix ]"
chk "window map-fix added to session proj, rooted in the worktree" \
  "[ \"\$(windows proj)\" = 'editor map-fix ' ] && [ \"\$(tmux display-message -p -t '=proj:map-fix' '#{pane_current_path}')\" = '$ROOT/proj/worktrees/map-fix' ]"
chk "no new tmux session; other session untouched" "[ \"\$(sessions)\" = '$s0' ] && [ \"\$(windows other)\" = '$o0' ]"
chk "primary checkout still on primary-line and clean" "[ \"\$(git -C '$P' branch --show-current)\" = primary-line ] && [ -z \"\$(git -C '$P' status --porcelain)\" ]"
chk "prints the explicit-target merge hint" "grep -q 'wt merge primary-line' '$T/out'"

echo "== slash in the name: fix/map → worktrees/fix-map, window fix-map"
rc=$(run "$P" fix/map)
chk "exit 0, branch fix/map, dir + window fix-map" "[ $rc = 0 ] && git -C '$P' show-ref -q --verify refs/heads/fix/map && [ -d '$ROOT/proj/worktrees/fix-map' ] && windows proj | grep -qw fix-map"

echo "== plain Worktrunk (agents): same layout, no tmux"
w1=$(windows proj)
( cd "$P" && command wt switch --create agent-x --base primary-line --no-cd >/dev/null 2>&1 )
chk "agent-x at worktrees/agent-x, no tmux window" "[ -d '$ROOT/proj/worktrees/agent-x' ] && [ \"\$(windows proj)\" = '$w1' ]"
( cd "$ROOT/proj/worktrees/agent-x" && command wt switch --create from-stream --base @ --no-cd >/dev/null 2>&1 )
chk "created from inside a stream: still a sibling in worktrees/ (no nesting)" "[ -d '$ROOT/proj/worktrees/from-stream' ]"
mkrepo "$T/code/elsewhere"
( cd "$T/code/elsewhere" && command wt switch --create side --no-cd >/dev/null 2>&1 )
chk "repo outside <root>/<project>/main keeps Worktrunk's default layout" "[ -d '$T/code/elsewhere.side' ] && [ ! -e '$T/code/worktrees' ]"
mkrepo "$ROOT/flat"
( cd "$ROOT/flat" && command wt switch --create side --no-cd >/dev/null 2>&1 )
chk "repo directly under <root> (not <project>/main) keeps the default layout" "[ -d '$ROOT/flat.side' ] && [ ! -e '$ROOT/worktrees' ]"

echo "== refusals: nonzero exit, nothing created"
refuse() {  # refuse <label> <expected-rc> <dir> <args...>
  local label=$1 want=$2 dir=$3; shift 3
  local h0 t0 w0 rc; h0=$(heads); t0=$(wts); w0=$(windows proj)
  rc=$(run "$dir" "$@")
  chk "$label (exit $rc): $(head -1 "$T/out" | cut -c1-90)" \
    "[ $rc = $want ] && [ \"\$(heads)\" = '$h0' ] && [ \"\$(wts)\" = '$t0' ] && [ \"\$(windows proj)\" = '$w0' ]"
}
refuse "no argument"                          2 "$P"
refuse "option-like argument"                 2 "$P" --help
refuse "outside any Git repository"           1 "$T"         s1
refuse "from a linked worktree"               1 "$ROOT/proj/worktrees/map-fix" s2
refuse "repo not at <root>/<project>/main"    1 "$ROOT/flat" s3
refuse "invalid branch name"                  1 "$P"         'bad..name'
refuse "branch already exists"                1 "$P"         map-fix
refuse "name is the current primary branch"   1 "$P"         primary-line
mkdir -p "$ROOT/proj/worktrees/occupied"
refuse "target directory already exists"      1 "$P"         occupied
tmux new-window -d -t '=proj:' -n taken
refuse "window name already taken in session" 1 "$P"         taken
tmux kill-window -t '=proj:taken'
git -C "$P" checkout -q --detach
refuse "detached HEAD in primary checkout"    1 "$P"         s4
git -C "$P" checkout -q primary-line
mkrepo "$ROOT/lonely/main"; mkdir -p "$ROOT/lonely/worktrees"
h0=$(git -C "$ROOT/lonely/main" for-each-ref refs/heads | wc -l); rc=$(run "$ROOT/lonely/main" s5)
chk "no tmux session for the project (exit $rc): nothing created" \
  "[ $rc = 1 ] && grep -q \"no tmux session 'lonely'\" '$T/out' && [ \$(git -C '$ROOT/lonely/main' for-each-ref refs/heads | wc -l) = $h0 ] && [ ! -e '$ROOT/lonely/worktrees/s5' ]"

echo "== partial failures after Worktrunk ran: no rollback, real state + recovery"
mkdir -p "$T/shim-tmux" "$T/shim-wt"
REAL_TMUX=$(command -v tmux)
printf '#!/bin/sh\n[ "$1" = new-window ] && { echo "tmux: simulated failure" >&2; exit 1; }\nexec %s "$@"\n' "$REAL_TMUX" > "$T/shim-tmux/tmux"
# simulate Worktrunk creating the branch, then failing; called as: wt -C <top> switch --create <name> ...
printf '#!/bin/sh\ngit -C "$2" branch "$5" >/dev/null 2>&1; exit 1\n' > "$T/shim-wt/wt"
chmod +x "$T/shim-tmux/tmux" "$T/shim-wt/wt"
rcmd() { grep -A1 "$1" "$T/out" | tail -1 | sed 's/^ *//'; }   # the command printed under a heading

w0=$(windows proj)
rc=$( (cd "$P" && PATH="$T/shim-tmux:$PATH" "$CMD" tmux-fails) > "$T/out" 2>&1; echo $?); sed 's/^/     /' "$T/out"
chk "tmux fails: exit 1, no window, worktree + branch kept (no rollback)" \
  "[ $rc = 1 ] && [ \"\$(windows proj)\" = '$w0' ] && [ -d '$ROOT/proj/worktrees/tmux-fails' ] && git -C '$P' show-ref -q --verify refs/heads/tmux-fails"
chk "tmux fails: reports branch + worktree at the Model-B path" "grep -q 'state: branch tmux-fails exists, with a worktree at $ROOT/proj/worktrees/tmux-fails' '$T/out' && ! grep -q 'not the Model-B location' '$T/out'"
open_cmd=$(rcmd 'open it in the project session'); rm_cmd=$(rcmd 'or discard it through Worktrunk')
chk "printed open command works (window rooted in the worktree)" \
  "eval \"\$open_cmd\" && [ \"\$(tmux display-message -p -t '=proj:tmux-fails' '#{pane_current_path}')\" = '$ROOT/proj/worktrees/tmux-fails' ]"
chk "printed discard command is 'wt … remove' and removes the worktree" \
  "[[ \"\$rm_cmd\" == 'wt -C '*' remove tmux-fails' ]] && (cd '$T' && eval \"\$rm_cmd\" >/dev/null 2>&1) && [ ! -e '$ROOT/proj/worktrees/tmux-fails' ]"
tmux kill-window -t '=proj:tmux-fails' 2>/dev/null

printf 'worktree-path = "{%% if %%}"\n' > "$T/broken.toml"
h0=$(heads); w0=$(windows proj)
rc=$( (cd "$P" && WORKTRUNK_CONFIG_PATH="$T/broken.toml" "$CMD" broken-tpl) > "$T/out" 2>&1; echo $?)
chk "Worktrunk refuses (broken template): exit 1, 'nothing was created', nothing created" \
  "[ $rc = 1 ] && grep -q 'wt switch failed' '$T/out' && grep -q 'state: nothing was created' '$T/out' && [ \"\$(heads)\" = '$h0' ] && [ \"\$(windows proj)\" = '$w0' ]"

rc=$( (cd "$P" && PATH="$T/shim-wt:$PATH" "$CMD" branch-only) > "$T/out" 2>&1; echo $?)
chk "Worktrunk fails after creating the branch: reports branch without worktree + recovery" \
  "[ $rc = 1 ] && grep -q 'state: branch branch-only exists, but no worktree' '$T/out' && grep -q 'switch branch-only --no-cd' '$T/out' && grep -q 'branch -d branch-only' '$T/out' && git -C '$P' show-ref -q --verify refs/heads/branch-only"
git -C "$P" branch -q -d branch-only

w0=$(windows proj); printf '' > "$T/default.toml"
rc=$( (cd "$P" && WORKTRUNK_CONFIG_PATH="$T/default.toml" "$CMD" misplaced) > "$T/out" 2>&1; echo $?)
chk "worktree outside Model-B (config drift): exit 1, no window, reports actual location + note" \
  "[ $rc = 1 ] && grep -q 'expected $ROOT/proj/worktrees/misplaced' '$T/out' && grep -q 'state: branch misplaced exists, with a worktree at $ROOT/proj/main.misplaced' '$T/out' && grep -q 'not the Model-B location' '$T/out' && [ \"\$(windows proj)\" = '$w0' ] && [ -d '$ROOT/proj/main.misplaced' ]"

echo "== real state untouched"
REAL_AFTER="$(real_state)"
chk "/work primary checkouts (status, worktrees, branches) and the real tmux sessions unchanged" \
  "[ \"\$REAL_AFTER\" = \"\$REAL_BEFORE\" ]"

echo; echo "RESULT: pass=$pass fail=$fail"
[ "$fail" = 0 ]
