#!/usr/bin/env bash
# Tests for wb-integrate. Scratch Model-B repos (primary checkout on primary-line,
# repository default branch trunk), the real Worktrunk with the tracked config's
# hooks (root swapped for the scratch dir), and a stub `wt` (WB_WT) where only the
# invocation matters. /work and the real Worktrunk config are only read.
#   bash workstation/streams/wb-integrate.test.sh
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CMD="$HERE/wb-integrate"; CONFIG="$HERE/../config/worktrunk/config.toml"
for c in git wt jq; do command -v "$c" >/dev/null || { echo "SKIP: $c not installed"; exit 0; }; done

T="$(mktemp -d)"; ROOT="$T/work"; LOG="$T/hooks.log"
pass=0; fail=0
chk() { if eval "$2"; then echo "  ok   $1"; pass=$((pass+1)); else echo "  FAIL $1"; fail=$((fail+1)); fi; }

REAL_HOME="$HOME"
renv() { env -u GIT_CONFIG_GLOBAL -u WORKTRUNK_CONFIG_PATH HOME="$REAL_HOME" "$@"; }
real_state() {
  for d in /work/*/main; do
    [ -d "$d/.git" ] || continue
    echo "$d"; renv git -C "$d" status --porcelain; renv git -C "$d" worktree list --porcelain
    renv git -C "$d" for-each-ref --format='%(refname) %(objectname)' refs/heads
  done
}
REAL_BEFORE="$(real_state)"
trap 'rm -rf "$T"' EXIT

export HOME="$T/home" GIT_CONFIG_GLOBAL="$T/home/.gitconfig" WB_WORK_ROOT="$ROOT" WB_INTEGRATE_WAIT=20
export WORKTRUNK_CONFIG_PATH="$T/wt.toml" WORKTRUNK_APPROVALS_PATH="$T/approvals.toml"
export EDITOR=true GIT_EDITOR=true PATH="$T/bin:$HERE:$PATH"
unset TMUX WORKTRUNK_DIRECTIVE_CD_FILE WORKTRUNK_DIRECTIVE_EXEC_FILE WB_WT
mkdir -p "$HOME" "$T/bin"
git config --global user.name test; git config --global user.email test@example.invalid
git config --global init.defaultBranch trunk; git config --global advice.detachedHead false
parts=$(( $(printf '%s' "$ROOT/p/main" | tr -cd '/' | wc -c) + 1 ))
sed -e "s#'/work/'#'$ROOT/'#" -e "s#length) == 4 #length) == $parts #" "$CONFIG" > "$WORKTRUNK_CONFIG_PATH"
grep -q "'$ROOT/'" "$WORKTRUNK_CONFIG_PATH" || { echo "could not adapt $CONFIG"; exit 1; }
# tmux must never be called: a stub that records any call.
printf '#!/bin/sh\necho "tmux $*" >> %s\nexit 0\n' "$T/tmux.calls" > "$T/bin/tmux"; chmod +x "$T/bin/tmux"
# stub wt: records its arguments, changes nothing, exits 9.
printf '#!/bin/sh\necho "$*" >> %s\nexit 9\n' "$T/wt.calls" > "$T/stub-wt"; chmod +x "$T/stub-wt"

# mkproject <name>: bare origin (default branch trunk), primary checkout on primary-line, trunk diverged.
mkproject() {
  local p=$1 m="$ROOT/$1/main"
  git init -q --bare "$T/$p-origin.git"
  git clone -q "$T/$p-origin.git" "$m" 2>/dev/null; mkdir -p "$ROOT/$p/worktrees"
  printf 'base\n' > "$m/README"; printf 'line1\nline2\nline3\n' > "$m/conflict.txt"
  printf '*.ignored\n.env.workspace\n' > "$m/.gitignore"
  mkdir -p "$m/.config/workspace"
  cat > "$m/.config/workspace/teardown" <<EOF
#!/usr/bin/env bash
exists=no; [ -d "\$WORKSPACE_PATH" ] && exists=yes
echo "TEARDOWN \$WORKSPACE_ID exists=\$exists" >> "$LOG"
[ ! -e "$T/fail-teardown" ] || { echo "teardown: simulated failure" >&2; exit 1; }
EOF
  chmod +x "$m/.config/workspace/teardown"
  git -C "$m" add -A; git -C "$m" commit -q -m "T1 base"
  git -C "$m" push -q origin trunk; git -C "$T/$p-origin.git" symbolic-ref HEAD refs/heads/trunk
  git -C "$m" remote set-head origin trunk >/dev/null
  git -C "$m" checkout -q -b primary-line; printf 'p\n' > "$m/primary.txt"
  git -C "$m" add primary.txt; git -C "$m" commit -q -m "P1 primary-line"
  git -C "$m" checkout -q trunk; printf 't\n' > "$m/trunk.txt"; git -C "$m" add trunk.txt
  git -C "$m" commit -q -m "T2 trunk only"; git -C "$m" checkout -q primary-line
}
stream() { ( cd "$ROOT/$1/main" && wt switch --create "$2" --base @ --no-cd >/dev/null 2>&1 ); }
run()  { ( cd "$1" && "$CMD" ) > "$T/out" 2>&1; echo $?; }
runs() { : > "$T/wt.calls"; ( cd "$1" && WB_WT="$T/stub-wt" "$CMD" ) > "$T/out" 2>&1; echo $?; }   # stub wt
rev()  { git -C "$ROOT/$1/main" rev-parse --verify -q "$2"; }
wt_called() { [ -s "$T/wt.calls" ]; }
first() { head -1 "$T/out" | cut -c1-110; }

mkproject proj; M="$ROOT/proj/main"; W="$ROOT/proj/worktrees"
mkproject flatp >/dev/null; mv "$ROOT/flatp/main" "$ROOT/flat"   # a repo under the root, not Model-B

echo "== where it may run"
rc=$(run "$T"); chk "outside any Git checkout: exit 2 ($(first))" "[ $rc = 2 ] && grep -q 'not inside a Git checkout' '$T/out'"
rc=$(run "$ROOT/flat"); chk "Git repo under the root but not Model-B: exit 2" "[ $rc = 2 ] && grep -q 'not a Model-B side worktree' '$T/out'"
rc=$(run "$M"); chk "from the primary checkout: exit 2 ($(first))" "[ $rc = 2 ] && grep -q 'this is the primary checkout' '$T/out'"
rc=$( (cd "$T" && "$CMD" extra) >/dev/null 2>&1; echo $?); chk "any argument (no target can be passed): exit 2" "[ $rc = 2 ]"

echo "== invocation (stub wt)"
stream proj s-stub; S="$W/s-stub"; printf 'x\n' > "$S/x.txt"; git -C "$S" add x.txt; git -C "$S" commit -q -m "s-stub: x"
rc=$(runs "$S")
chk "target derived from main (primary-line, while the default branch is trunk): exact 'wt -C <side> merge primary-line --stage tracked'" \
  "[ \"\$(cat '$T/wt.calls')\" = '-C $S merge primary-line --stage tracked' ]"
chk "never a bare merge, never --stage all" "! grep -qE '(^| )merge( --|\$)' '$T/wt.calls' && ! grep -q 'stage all' '$T/wt.calls'"
chk "unknown outcome (wt exit 9, nothing changed): exit 5, UNKNOWN, state reported, branch + worktree intact" \
  "[ $rc = 5 ] && grep -q 'UNKNOWN: Worktrunk exited 9' '$T/out' && grep -q 'state: Worktrunk exit 9' '$T/out' && [ -d '$S' ] && rev proj s-stub >/dev/null"

echo "== preconditions: refused, Worktrunk never invoked"
git -C "$M" checkout -q --detach
rc=$(runs "$S"); chk "detached primary: exit 2" "[ $rc = 2 ] && grep -q 'detached HEAD' '$T/out' && ! wt_called"
git -C "$M" checkout -q primary-line
printf 'dirty\n' >> "$M/README"
rc=$(runs "$S"); chk "dirty tracked file in primary: exit 2, path listed" "[ $rc = 2 ] && grep -q 'uncommitted changes' '$T/out' && grep -q 'M README' '$T/out' && ! wt_called"
git -C "$M" checkout -q -- README
printf 'wip\n' > "$M/wip.txt"
rc=$(runs "$S"); chk "untracked file in primary: exit 2, path listed" "[ $rc = 2 ] && grep -q '?? wip.txt' '$T/out' && ! wt_called"
rm "$M/wip.txt"; printf 'local\n' > "$M/local.ignored"
rc=$(runs "$S"); chk "ignored file in primary only: preconditions pass (wt invoked)" "wt_called"
rm "$M/local.ignored"
printf 'junk\n' > "$S/notes.tmp"; mkdir -p "$S/dir with space"; printf 'y\n' > "$S/dir with space/f.txt"
rc=$(runs "$S"); chk "untracked files in side: exit 2, each path listed (spaces intact)" \
  "[ $rc = 2 ] && grep -q 'untracked files' '$T/out' && grep -q 'notes.tmp' '$T/out' && grep -q 'dir with space/f.txt' '$T/out' && ! wt_called"
rm -rf "$S/notes.tmp" "$S/dir with space"; printf 'gen\n' > "$S/.env.workspace"
rc=$(runs "$S"); chk "ignored file in side: preconditions pass (wt invoked)" "wt_called"
mkdir -p "$(git -C "$S" rev-parse --git-path rebase-merge)"
rc=$(runs "$S"); chk "interrupted rebase in side: exit 2" "[ $rc = 2 ] && grep -q 'rebase is in progress' '$T/out' && ! wt_called"
rm -rf "$(git -C "$S" rev-parse --git-path rebase-merge)"
stream proj s-empty
rc=$(runs "$W/s-empty"); chk "nothing to integrate: exit 2" "[ $rc = 2 ] && grep -q 'nothing to integrate' '$T/out' && ! wt_called"

echo "== real Worktrunk: complete integration"
stream proj s-ok; S="$W/s-ok"
printf 'f1\n' > "$S/feature.txt"; git -C "$S" add feature.txt; git -C "$S" commit -q -m "s-ok: 1"
printf 'f2\n' >> "$S/feature.txt"; git -C "$S" commit -q -am "s-ok: 2"
printf 'tracked edit\n' >> "$S/README"                       # uncommitted tracked edit rides along
printf 'gen\n' > "$S/.env.workspace"                          # ignored, never committed
P0=$(rev proj primary-line); T0=$(rev proj trunk); : > "$LOG"; : > "$T/tmux.calls"
rc=$(run "$S"); sed 's/^/     /' "$T/out" | grep -v -e 'shell integration' -e 'shell install'
chk "exit 0, COMPLETE" "[ $rc = 0 ] && grep -q 'COMPLETE: s-ok integrated into primary-line' '$T/out'"
chk "primary-line advanced (fast-forward from its old tip) and holds the feature + tracked edit" \
  "[ \"\$(rev proj primary-line)\" != '$P0' ] && git -C '$M' merge-base --is-ancestor '$P0' primary-line && git -C '$M' show primary-line:feature.txt | grep -q f2 && git -C '$M' show primary-line:README | grep -q 'tracked edit'"
chk "ignored .env.workspace not committed" "! git -C '$M' ls-tree --name-only primary-line | grep -qx .env.workspace"
chk "repository default branch (trunk) did not move" "[ \"\$(rev proj trunk)\" = '$T0' ]"
chk "teardown ran while the worktree still existed" "grep -q 'TEARDOWN proj-s-ok exists=yes' '$LOG'"
chk "side worktree and branch removed" "[ ! -e '$S' ] && ! rev proj s-ok >/dev/null"
chk "primary checkout updated and clean" "[ \"\$(git -C '$M' rev-parse HEAD)\" = \"\$(rev proj primary-line)\" ] && [ -z \"\$(git -C '$M' status --porcelain)\" ]"
chk "tmux never called" "[ ! -s '$T/tmux.calls' ]"

echo "== real Worktrunk: teardown fails after the fast-forward"
stream proj s-td; S="$W/s-td"; printf 'td\n' > "$S/td.txt"; git -C "$S" add td.txt; git -C "$S" commit -q -m "s-td"
P0=$(rev proj primary-line); touch "$T/fail-teardown"
rc=$(run "$S")
chk "exit 3, INTEGRATED, CLEANUP FAILED (not reported as a merge failure)" \
  "[ $rc = 3 ] && grep -q 'INTEGRATED, CLEANUP FAILED: s-td is in primary-line' '$T/out' && ! grep -q 'CONFLICT\|UNKNOWN' '$T/out'"
chk "primary-line advanced; worktree + branch left in place; told not to rerun" \
  "[ \"\$(rev proj primary-line)\" != '$P0' ] && [ -d '$S' ] && rev proj s-td >/dev/null && grep -q 'do NOT rerun wb-integrate' '$T/out'"
rm -f "$T/fail-teardown"
rm_cmd=$(grep -o "wt -C [^ ]* remove s-td" "$T/out"); del_cmd=$(grep -o "git -C [^ ]* merge-base --is-ancestor s-td primary-line && git -C [^ ]* branch -d s-td" "$T/out")
chk "printed recovery works: wt remove, then ancestry-checked branch -d (no -D)" \
  "[ -n \"\$rm_cmd\" ] && [ -n \"\$del_cmd\" ] && eval \"\$rm_cmd\" >/dev/null 2>&1 && sleep 2 && [ ! -e '$S' ] && { rev proj s-td >/dev/null && eval \"\$del_cmd\" >/dev/null 2>&1 || true; } && ! rev proj s-td >/dev/null && ! grep -q -- ' -D' '$T/out'"

echo "== real Worktrunk: rebase conflict (multi-commit stream)"
stream proj s-cf; S="$W/s-cf"
sed -i 's/line2/line2-side/' "$S/conflict.txt"; git -C "$S" commit -q -am "s-cf: 1"
printf 'z\n' > "$S/z.txt"; git -C "$S" add z.txt; git -C "$S" commit -q -m "s-cf: 2"
sed -i 's/line2/line2-primary/' "$M/conflict.txt"; git -C "$M" commit -q -am "P2 conflicting"
P0=$(rev proj primary-line); : > "$LOG"
rc=$(run "$S")
chk "exit 4, CONFLICT, primary-line NOT integrated, rebase left active" \
  "[ $rc = 4 ] && grep -q 'CONFLICT: the rebase onto primary-line stopped' '$T/out' && [ \"\$(rev proj primary-line)\" = '$P0' ] && [ -d \"\$(git -C '$S' rev-parse --git-path rebase-merge)\" ]"
chk "recovery text: abort, resolve + rerun, squash/reflog caveat; no teardown ran" \
  "grep -q 'git -C $S rebase --abort' '$T/out' && grep -q 'rebase --continue' '$T/out' && grep -q 'wb-integrate' '$T/out' && grep -q 'reflog show s-cf' '$T/out' && [ ! -s '$LOG' ]"
git -C "$S" rebase --abort
chk "after abort: branch checked out again, no rebase" "[ \"\$(git -C '$S' branch --show-current)\" = s-cf ] && [ ! -d \"\$(git -C '$S' rev-parse --git-path rebase-merge)\" ]"

echo "== real Worktrunk: slash in the stream name"
stream proj fix/map; S="$W/fix-map"; printf 'm\n' > "$S/map.txt"; git -C "$S" add map.txt; git -C "$S" commit -q -m "fix/map"
rc=$(run "$S")
chk "fix/map from worktrees/fix-map: exit 0, branch fix/map removed, worktree removed" \
  "[ $rc = 0 ] && grep -q 'COMPLETE: fix/map integrated into primary-line' '$T/out' && ! rev proj fix/map >/dev/null && [ ! -e '$S' ]"

echo "== real state untouched"
chk "/work primary checkouts (status, worktrees, branches) unchanged" "[ \"\$(real_state)\" = \"\$REAL_BEFORE\" ]"

echo; echo "RESULT: pass=$pass fail=$fail"
[ "$fail" = 0 ]
