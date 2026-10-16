#!/usr/bin/env bash
# Tests for session-reap.sh: the family rule (including the Model-B /work layout) and the
# orphan-watcher and stale-loop sweeps. Every process involved is started here, in a
# scratch work root (WB_WORK_ROOT) with a scratch HOME (so a scratch log), and the
# family gate keeps the reaper away from anything outside that root.
#   bash workstation/claude/hooks/session-reap.test.sh
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; REAP="$HERE/session-reap.sh"
[ -d /proc/self/fd ] || { echo "SKIP: needs Linux /proc"; exit 0; }
T="$(mktemp -d)"
cleanup() {   # stop only processes whose cwd is under this scratch dir
  local p
  for p in $(pgrep -u "$(id -u)" .); do
    case "$(readlink "/proc/$p/cwd" 2>/dev/null)" in "$T"/*) kill "$p" 2>/dev/null ;; esac
  done
  sleep 0.3; rm -rf "$T"
}
trap cleanup EXIT
pass=0; fail=0
chk() { if eval "$2"; then echo "  ok   $1"; pass=$((pass+1)); else echo "  FAIL $1"; fail=$((fail+1)); fi; }

REAL_AGENTS_BEFORE=$(pgrep -x claude | sort)
export HOME="$T/home" WB_WORK_ROOT="$T/work"; mkdir -p "$HOME/.claude/hooks"
A="$T/work/alpha"; mkdir -p "$A/main" "$A/worktrees/other" "$T/work/alpha2/main" "$T/work/beta/main"
reap() { (cd "$T" && SESSION_REAP_MAX_WATCH_AGE="${AGE:-0}" SESSION_REAP_MAX_LOOP_AGE="${AGE:-0}" bash "$REAP" "$@"); }

echo "== family rule"
eval "$(sed -n '/^family_prefix() {/,/^}/p' "$REAP")"
chk "Model-B main and worktree share one family, with a path boundary" \
  "[ \"\$(family_prefix $A/main)\" = '$A/' ] && [ \"\$(family_prefix $A/worktrees/x/y)\" = '$A/' ]"
chk "/work/alpha2 is NOT in alpha's family (boundary)" "case '$T/work/alpha2/main' in '$A/'*) false ;; *) true ;; esac"
chk "the work root alone names no family (fail safe)" "[ -z \"\$(family_prefix $T/work)\" ]"
chk "\$HOME layouts unchanged: ~/Projects/podcast_scraper-ai -> ~/Projects/podcast_scraper" \
  "[ \"\$(family_prefix $HOME/Projects/podcast_scraper-ai)\" = '$HOME/Projects/podcast_scraper' ]"
chk "session-orphan-report.sh uses the identical rule" \
  "[ \"\$(sed -n '/^family_prefix() {/,/^}/p' '$REAP' | grep -v '^ *#')\" = \"\$(sed -n '/^family_prefix() {/,/^}/p' '$HERE/session-orphan-report.sh' | grep -v '^ *#')\" ]"

# watcher <dir> <name> [live-parent]: start `tail -f <file> | grep`, then delete the file;
# the tail's pid lands in $T/pid.<name>. Orphaned (the setsid shell exits at once) unless
# live-parent, where the starting shell stays alive. Never run inside $( ): the fixture's
# processes must not hold a command-substitution pipe open.
watcher() {
  local d=$1 f="$1/$2.log"; echo start > "$f"
  if [ -n "${3:-}" ]; then (cd "$d" && setsid -f bash -c "tail -f '$f' | grep -q never-matches; sleep 600" </dev/null >/dev/null 2>&1)
  else (cd "$d" && setsid -f sh -c "tail -f '$f' | grep -q never-matches &" </dev/null >/dev/null 2>&1); fi
  sleep 0.5; [ "${KEEPFILE:-}" ] || rm -f "$f"; sleep 0.2
  pgrep -f "tail -f $f" | head -1 > "$T/pid.$2"
}
pid() { cat "$T/pid.$1"; }
group_of() { pgrep -g "$(ps -o pgid= -p "$1" | tr -d ' ')" | sort | tr '\n' ' '; }
alive() { local p; for p in $1; do kill -0 "$p" 2>/dev/null || return 1; done; }
dead() { local p i; for i in $(seq 1 40); do for p in $1; do kill -0 "$p" 2>/dev/null && continue 2; done; return 0; done; return 1; }

echo "== orphan-watcher sweep"
watcher "$A/main" w1; W=$(pid w1); G1=$(group_of "$W")
chk "fixture: an orphaned tail|grep whose file is deleted (tail + grep in one group)" "[ -n '$W' ] && [ \$(wc -w <<<'$G1') = 2 ] && [ \"\$(ps -o ppid= -p $W | tr -d ' ')\" = 1 ]"
SESSION_REAP_DRY_RUN=1 reap "$A/worktrees/other" > "$T/dry.out"
chk "dry-run names both processes and kills nothing" "[ \$(grep -c 'would reap watcher' '$T/dry.out') = 2 ] && alive '$G1'"
watcher "$A/main" live-parent live; GL=$(group_of "$(pid live-parent)")
watcher "$T/work/beta/main" other-family; GO=$(group_of "$(pid other-family)")
KEEPFILE=1 watcher "$A/main" keep; GK=$(group_of "$(pid keep)")
watcher "$T/work/alpha2/main" prefix-sibling; GP=$(group_of "$(pid prefix-sibling)")
chk "fixtures: live-parent, other-family and keep watchers are running" "[ -n '$GL' ] && [ -n '$GO' ] && [ -n '$GK' ] && alive '$GL $GO $GK'"
AGE=7200 reap "$A/worktrees/other" > "$T/young.out"
chk "age floor: a watcher younger than SESSION_REAP_MAX_WATCH_AGE is left alone" "alive '$G1' && ! grep -q 'swept' '$T/young.out'"
reap "$A/worktrees/other" > "$T/live.out"
chk "live run: the orphaned tail and its grep are gone" "dead '$G1'"
chk "a tail whose file still exists is kept" "alive '$GK'"
chk "a watcher with a live parent (its session still there) is kept" "alive '$GL'"
chk "another project family (beta) is never touched from alpha" "alive '$GO'"
chk "a prefix-sharing project (/work/alpha2) is not alpha's family: its orphaned watcher is kept" "alive '$GP' && ! grep -q 'REAP-WATCH.*alpha2' '$HOME/.claude/hooks/session-reap.log'"
chk "every kill is logged as REAP-WATCH with its group" "[ \$(grep -c 'REAP-WATCH' '$HOME/.claude/hooks/session-reap.log') -ge 2 ]"
watcher "$A/main" w2; G2=$(group_of "$(pid w2)")
SESSION_REAP_NO_WATCH_SWEEP=1 reap "$A/worktrees/other" > /dev/null
chk "SESSION_REAP_NO_WATCH_SWEEP=1 disables it" "alive '$G2'"

echo "== stale-loop sweep now reaches the Model-B layout"
mkdir -p "$T/bin"; printf '#!/bin/sh\nexit 0\n' > "$T/bin/gh"; chmod +x "$T/bin/gh"
(cd "$A/main" && PATH="$T/bin:$PATH" setsid -f bash -c 'while true; do gh run list >/dev/null; sleep 1; done' </dev/null >/dev/null 2>&1); sleep 0.5
LOOP=$(pgrep -f 'while true; do gh run list' | while read -r p; do [ "$(readlink /proc/$p/cwd)" = "$A/main" ] && echo "$p"; done | head -1)
reap "$A/worktrees/other" > "$T/loop.out"
chk "an unbounded gh-run loop under /work/<project> is reaped (was skipped: family=none)" "[ -n '$LOOP' ] && dead '$LOOP' && grep -q 'stale-loop sweep (family=$A/)' '$HOME/.claude/hooks/session-reap.log'"

echo "== the real environment was only read"
chk "real agents untouched" "[ \"\$(pgrep -x claude | sort)\" = \"\$REAL_AGENTS_BEFORE\" ]"

echo; echo "RESULT: pass=$pass fail=$fail"
[ "$fail" = 0 ]
