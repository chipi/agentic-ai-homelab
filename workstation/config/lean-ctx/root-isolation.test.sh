#!/usr/bin/env bash
# LeanCTX project-root isolation (config/lean-ctx/README.md). Drives the real agent
# path, hook JSON with a cwd -> `lean-ctx hook rewrite` -> the rewritten command run
# in that cwd, against scratch Git projects, a scratch LeanCTX state directory
# (so its own daemon) and a disposable tmux server. The real daemon, the real tmux
# server and /work are only read, to prove they are untouched.
#   bash workstation/config/lean-ctx/root-isolation.test.sh
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; WS="$(cd "$HERE/../.." && pwd)"
L="$(command -v lean-ctx || true)"
for c in jq git tmux; do command -v "$c" >/dev/null || { echo "SKIP: $c not installed"; exit 0; }; done
[ -n "$L" ] || { echo "SKIP: lean-ctx not installed"; exit 0; }
# The fix, exactly as install.sh writes it into ~/.bashrc.
FIX_LINE=$(sed -n "s/^LEANCTX_ROOT_LINE='\(.*\)'$/\1/p" "$WS/install.sh")
[ -n "$FIX_LINE" ] || { echo "FAIL install.sh defines no LEANCTX_ROOT_LINE"; exit 1; }
FIX_VAR=${FIX_LINE#export }; FIX_VAR=${FIX_VAR%%=*}; FIX_VAL=${FIX_LINE#*=}

REAL_DAEMON_PID=$(cat "$HOME/.local/share/lean-ctx/daemon.pid" 2>/dev/null)
REAL_DAEMON_CWD=$(readlink "/proc/$REAL_DAEMON_PID/cwd" 2>/dev/null)
REAL_SOCK="${TMUX%%,*}"; [ -n "$REAL_SOCK" ] || REAL_SOCK="/tmp/tmux-$(id -u)/default"
real_tmux_fp() { [ -S "$REAL_SOCK" ] || { echo none; return; }; env -u TMUX tmux -S "$REAL_SOCK" list-panes -a -F '#{pid} #{session_name} #{window_id} #{pane_id}' 2>/dev/null | sort; }
REAL_TMUX_BEFORE=$(real_tmux_fp)

T="$(mktemp -d)"
cleanup() {   # only processes whose environment names this scratch directory
  local p
  tmux -L lctxtest kill-server 2>/dev/null
  for p in $(pgrep -f 'lean-ctx|sleep 9'); do
    grep -qzF "LEAN_CTX_DATA_DIR=$T/data" "/proc/$p/environ" 2>/dev/null && kill "$p" 2>/dev/null
  done
  sleep 0.5; rm -rf "$T"
}
trap cleanup EXIT
pass=0; fail=0
chk() { if eval "$2"; then echo "  ok   $1"; pass=$((pass+1)); else echo "  FAIL $1"; fail=$((fail+1)); fi; }

unset LEAN_CTX_WRAPPED LEAN_CTX_ACTIVE LEAN_CTX_AGENT LEAN_CTX_EXEC_DEPTH CLAUDECODE CLAUDE_CODE_ENTRYPOINT "$FIX_VAR" TMUX
export HOME="$T/home" LEAN_CTX_DATA_DIR="$T/data" LEAN_CTX_STATE_DIR="$T/state" LEAN_CTX_CONFIG_DIR="$T/cfg" \
       LEAN_CTX_CACHE_DIR="$T/cache" XDG_DATA_HOME="$T/xdg" XDG_CONFIG_HOME="$T/xdgcfg" LEAN_CTX_NO_UPDATE_CHECK=1 TMUX_TMPDIR="$T/tmux"
mkdir -p "$HOME" "$T/data" "$T/state" "$T/cfg" "$T/cache" "$T/tmux" "$T/out"
# The tracked config (allowlist, jail settings) is what the agents run with.
cp "$HERE/config.toml" "$T/cfg/config.toml"

# Projects: alpha (main + two worktrees) and beta. Every context has a MARK file
# naming itself, so a read proves WHICH context answered.
W="$T/work"
mkproj() { mkdir -p "$W/$1/main"; git -C "$W/$1/main" init -q; echo "# project $1" > "$W/$1/main/README.md"
  git -C "$W/$1/main" add . && git -C "$W/$1/main" -c user.name=t -c user.email=t@t commit -qm init; echo "mark $1/main" > "$W/$1/main/MARK.md"; }
mkproj alpha; mkproj beta
for wt in task-a task-b; do git -C "$W/alpha/main" worktree add -q "$W/alpha/worktrees/$wt" -b "$wt"; echo "mark alpha/$wt" > "$W/alpha/worktrees/$wt/MARK.md"; done
CTX_alpha="$W/alpha/main"; CTX_beta="$W/beta/main"; CTX_a="$W/alpha/worktrees/task-a"; CTX_b="$W/alpha/worktrees/task-b"
want() { case $1 in "$CTX_alpha") echo "mark alpha/main" ;; "$CTX_beta") echo "mark beta/main" ;; "$CTX_a") echo "mark alpha/task-a" ;; "$CTX_b") echo "mark alpha/task-b" ;; esac; }

# agent <cwd> <native command> [fix]: what the agent's Bash tool would run and print.
agent() {
  local cwd=$1 cmd=$2 fixed=${3:-} rewritten
  rewritten=$(jq -nc --arg c "$cmd" --arg cwd "$cwd" '{session_id:"t",transcript_path:"/dev/null",cwd:$cwd,hook_event_name:"PreToolUse",tool_name:"Bash",tool_input:{command:$c}}' |
    "$L" hook rewrite 2>/dev/null | jq -r '.hookSpecificOutput.updatedInput.command // empty')
  [ -n "$rewritten" ] || rewritten=$cmd
  if [ -n "$fixed" ]; then (cd "$cwd" && env "$FIX_VAR=$FIX_VAL" bash -c "$rewritten" 2>&1)
  else (cd "$cwd" && bash -c "$rewritten" 2>&1); fi
}
REFUSED='escapes project root|outside the active project|outside active project|Access denied'
# ok_ctx <cwd> <output>: the output is THIS context's own file, not a refusal.
ok_ctx() { grep -qF "$(want "$1")" <<<"$2" && ! grep -qE "$REFUSED" <<<"$2"; }
CMDS=("cat MARK.md" "head -n 1 MARK.md" "sed -n 1,1p MARK.md" "tail -n 1 MARK.md" "grep -n mark MARK.md")

echo "== the hazard: a shared daemon started from one project (no fix)"
out=$(agent "$CTX_alpha" "cat MARK.md")
chk "first call, from alpha/main, works and starts the shared daemon" "ok_ctx '$CTX_alpha' \"\$out\""
sleep 1
DAEMON=$(for p in $(pgrep -f 'lean-ctx serve'); do grep -qzF "LEAN_CTX_DATA_DIR=$T/data" "/proc/$p/environ" 2>/dev/null && echo "$p"; done | head -1)
if [ -n "$DAEMON" ]; then
  echo "    scratch daemon pid $DAEMON, cwd $(readlink "/proc/$DAEMON/cwd")"
  out=$(agent "$CTX_beta" "cat MARK.md")
  if grep -qE "$REFUSED" <<<"$out"; then echo "    reproduced: beta/main refused with $(grep -oE 'root: [^)]*' <<<"$out" | head -1)"
  else echo "    NOTE: this LeanCTX no longer refuses beta through the daemon (upstream fix?); the checks below still apply"; fi
else
  echo "    NOTE: no shared daemon was started (upstream changed autostart?); the checks below still apply"
fi

echo "== sequential: alternate contexts and commands, with the fix, while the alpha-rooted daemon runs"
bad=0; n=0
for round in 1 2 3; do
  for ctx in "$CTX_alpha" "$CTX_beta" "$CTX_a" "$CTX_b" "$CTX_beta" "$CTX_alpha" "$CTX_b" "$CTX_a"; do
    for c in "${CMDS[@]}"; do
      out=$(agent "$ctx" "$c" fixed); n=$((n+1))
      ok_ctx "$ctx" "$out" || { bad=$((bad+1)); echo "    wrong: $ctx '$c' -> $(head -c 160 <<<"$out")"; }
    done
  done
done
chk "all $n alternating reads (cat/head/sed/tail/grep across alpha, beta, task-a, task-b) answered from their own context" "[ $bad = 0 ]"
out=$(agent "$CTX_beta" "ls ." fixed)
chk "ls (rewritten to lean-ctx ls) in beta lists beta's files" "grep -q MARK.md <<<\"\$out\" && ! grep -qE \"$REFUSED\" <<<\"\$out\""
out=$(agent "$CTX_a" "cat MARK.md" fixed)
chk "a worktree is its own root: task-a reads task-a, not main" "[ \"\$(grep -c 'mark alpha/task-a' <<<\"\$out\")\" -ge 1 ] && ! grep -q 'mark alpha/main' <<<\"\$out\""

echo "== no broadening: the fix changes where a call runs, not what LeanCTX allows"
# rewrite <cwd> <command> [fix]: the hook's decision (the command the agent will run).
rewrite() {
  jq -nc --arg c "$2" --arg cwd "$1" '{session_id:"t",cwd:$cwd,hook_event_name:"PreToolUse",tool_name:"Bash",tool_input:{command:$c}}' |
    if [ -n "${3:-}" ]; then env "$FIX_VAR=$FIX_VAL" "$L" hook rewrite; else "$L" hook rewrite; fi 2>/dev/null |
    jq -r '.hookSpecificOutput.updatedInput.command // "PASSTHROUGH"'
}
same=1
for pair in "$CTX_alpha|cat MARK.md" "$CTX_alpha|cat $CTX_beta/MARK.md" "$CTX_a|cat $CTX_b/MARK.md" "$CTX_beta|grep -n mark $CTX_a/MARK.md" "$CTX_b|sed -n 1,1p $CTX_alpha/MARK.md" "$CTX_beta|ls ."; do
  [ "$(rewrite "${pair%%|*}" "${pair#*|}")" = "$(rewrite "${pair%%|*}" "${pair#*|}" fixed)" ] || { same=0; echo "    differs: $pair"; }
done
chk "the hook makes identical decisions with and without the fix (6 in- and cross-context commands)" "[ $same = 1 ]"
chk "cross-context reads are not rewritten into lean-ctx at all (native command, before and after the fix)" \
  "[ \"\$(rewrite '$CTX_alpha' 'cat $CTX_beta/MARK.md' fixed)\" = PASSTHROUGH ] && [ \"\$(rewrite '$CTX_a' 'cat $CTX_b/MARK.md')\" = PASSTHROUGH ]"
mcp_read() {  # mcp_read <cwd> <path> [fix]: ctx_read through a fresh MCP server started in <cwd>
  { printf '%s\n' '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"t","version":"0"}}}' '{"jsonrpc":"2.0","method":"notifications/initialized"}'
    jq -nc --arg p "$2" '{jsonrpc:"2.0",id:2,method:"tools/call",params:{name:"ctx_read",arguments:{path:$p,mode:"full"}}}'; sleep 3; } |
    (cd "$1" && if [ -n "${3:-}" ]; then env "$FIX_VAR=$FIX_VAL" timeout 20 "$L"; else timeout 20 "$L"; fi 2>/dev/null) |
    grep '"id":2' | jq -r '.result.content[0].text // .error.message' 2>/dev/null
}
out=$(mcp_read "$CTX_alpha" "$CTX_beta/MARK.md" fixed)
chk "MCP ctx_read jail still refuses another project (alpha -> beta), with the fix" "grep -qE \"$REFUSED\" <<<\"\$out\" && ! grep -q 'mark beta/main' <<<\"\$out\""
out=$(mcp_read "$CTX_a" "$CTX_b/MARK.md" fixed)
chk "MCP ctx_read jail still refuses a sibling worktree (task-a -> task-b), with the fix" "grep -qE \"$REFUSED\" <<<\"\$out\" && ! grep -q 'mark alpha/task-b' <<<\"\$out\""
out=$(mcp_read "$CTX_a" "MARK.md" fixed)
chk "MCP ctx_read in a worktree reads that worktree" "grep -q 'mark alpha/task-a' <<<\"\$out\" && ! grep -qE \"$REFUSED\" <<<\"\$out\""

echo "== concurrent: four contexts at once, plus an unfixed caller keeping the daemon busy"
worker() {  # worker <ctx> <name>: 20 rounds over all commands, failures counted
  local ctx=$1 name=$2 i c out bad=0 done=0
  for i in $(seq 1 20); do for c in "${CMDS[@]}"; do
    out=$(agent "$ctx" "$c" fixed); done=$((done+1)); ok_ctx "$ctx" "$out" || bad=$((bad+1))
  done; done
  echo "$done $bad" > "$T/out/$name"
}
noise() { local i; for i in $(seq 1 40); do agent "$CTX_alpha" "cat MARK.md" >/dev/null; done; }
worker "$CTX_alpha" alpha & worker "$CTX_beta" beta & worker "$CTX_a" task-a & worker "$CTX_b" task-b & noise &
wait
res=$(for w in alpha beta task-a task-b; do echo "$w $(cat "$T/out/$w" 2>/dev/null)"; done)
echo "$res" | sed 's/^/    /'
chk "every concurrent worker completed 100 calls with 0 wrong-context answers" \
  "[ \"\$(awk '\$2 == 100 && \$3 == 0' <<<\"\$res\" | wc -l)\" = 4 ]"

echo "== tmux: project sessions in a disposable server, the fix coming from ~/.bashrc"
printf '%s\n' "$FIX_LINE" > "$HOME/.bashrc"
printf '[[ -f ~/.bashrc ]] && . ~/.bashrc\n' > "$HOME/.bash_profile"   # tmux panes are login shells; Omarchy's profile sources .bashrc
t() { tmux -L lctxtest -f /dev/null "$@"; }
t new-session -d -s alpha -n main -c "$CTX_alpha" -x 160 -y 40
t new-window -d -t alpha -n task-a -c "$CTX_a"
t new-session -d -s beta -n main -c "$CTX_beta" -x 160 -y 40
t new-window -d -t beta -n other -c "$CTX_b"
chk "the tmux server itself does not carry the variable (it comes from each pane's shell)" \
  "! t show-environment -g \"$FIX_VAR\" 2>/dev/null | grep -q '^$FIX_VAR='"
export -f agent want ok_ctx; export L REFUSED FIX_VAR FIX_VAL CTX_alpha CTX_beta CTX_a CTX_b T
pane_run() {  # pane_run <target> <name>: the pane's own shell runs one agent call per command
  t send-keys -t "$1" "for c in 'cat MARK.md' 'sed -n 1,1p MARK.md' 'grep -n mark MARK.md'; do jq -nc --arg c \"\$c\" --arg cwd \"\$PWD\" '{session_id:\"t\",cwd:\$cwd,hook_event_name:\"PreToolUse\",tool_name:\"Bash\",tool_input:{command:\$c}}' | lean-ctx hook rewrite | jq -r .hookSpecificOutput.updatedInput.command | bash; done > $T/out/$2 2>&1; echo \"\${$FIX_VAR:-unset}\" > $T/out/$2.env" C-m
}
for i in $(seq 1 50); do [ -n "$(t capture-pane -p -t alpha | tr -d '[:space:]')" ] && break; sleep 0.1; done; sleep 0.5
pane_run alpha:main p-alpha; pane_run beta:main p-beta; pane_run alpha:task-a p-task-a; pane_run beta:other p-task-b
for i in $(seq 1 100); do [ -s "$T/out/p-alpha.env" ] && [ -s "$T/out/p-beta.env" ] && [ -s "$T/out/p-task-a.env" ] && [ -s "$T/out/p-task-b.env" ] && break; sleep 0.2; done
chk "each pane's shell got the fix from ~/.bashrc" "[ \"\$(cat $T/out/p-*.env | sort -u)\" = '$FIX_VAL' ]"
chk "tmux alpha pane answers alpha/main, beta pane beta/main (3 commands each)" \
  "[ \$(grep -c 'mark alpha/main' $T/out/p-alpha) = 3 ] && [ \$(grep -c 'mark beta/main' $T/out/p-beta) = 3 ] && ! grep -qE \"$REFUSED\" $T/out/p-alpha $T/out/p-beta"
for f in p-alpha p-beta; do
  [ -n "${LCTX_TEST_DEBUG:-}" ] && { echo "    $f output:"; sed 's/^/      /' "$T/out/$f" | cut -c1-200; }
done
chk "tmux worktree windows answer their own worktree (task-a, task-b), never main" \
  "[ \$(grep -c 'mark alpha/task-a' $T/out/p-task-a) = 3 ] && [ \$(grep -c 'mark alpha/task-b' $T/out/p-task-b) = 3 ] && ! grep -qE \"$REFUSED|mark alpha/main\" $T/out/p-task-a $T/out/p-task-b"

echo "== the real environment was only read"
chk "real LeanCTX daemon: same process, same cwd" "[ \"\$(readlink /proc/$REAL_DAEMON_PID/cwd 2>/dev/null)\" = '$REAL_DAEMON_CWD' ]"
chk "real tmux server: same pid, sessions, windows and panes" "[ \"\$(real_tmux_fp)\" = \"\$REAL_TMUX_BEFORE\" ]"
NAMES='orr''ery|ocean''canvas|chemi''gram|aby''ss|bath''ys'   # split so this file never matches itself
chk "no project name or /work path in the fix, its installer block, or this test" \
  "! grep -qiE \"\$NAMES|/work/\" <<<\"\$FIX_LINE\" && ! sed -n '/^LEANCTX_ROOT_LINE=/,/^}/p' '$WS/install.sh' | grep -v '^#' | grep -qiE \"\$NAMES|/work/\" && ! grep -qiE \"\$NAMES\" '$HERE/root-isolation.test.sh'"

echo; echo "RESULT: pass=$pass fail=$fail"
[ "$fail" = 0 ]
