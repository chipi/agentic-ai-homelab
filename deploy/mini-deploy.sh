#!/usr/bin/env bash
# deploy/mini-deploy.sh — deploy agentic-ai-homelab on the Mac mini: pull main, run the registered
# gates over the pulled code, and roll the checkout back if any gate is red.
#
# The mini runs its services in place from this checkout (launchd jobs, the hub, the alert rules, the
# fleets), so a deploy is `git pull`. What a deploy checks and records is not in this script: each
# part of the repo registers hook scripts (see deploy/README.md):
#   deploy/hooks/pre-pull.d/*.sh   before the pull (e.g. install a deploy log); never block the deploy
#   deploy/hooks/gate.d/*.sh       after the pull, from the pulled code; exit non-zero = RED = roll back
#   deploy/hooks/rollback.d/*.sh   after a rollback (e.g. log it); never block
# Hooks get CHECKOUT, PREV and NOW (short shas) in their environment.
#
# Run ON the mini:   bash ~/agentic-ai-homelab/deploy/mini-deploy.sh
# (signal-fleet/deploy/deploy.sh is a wrapper around this script, kept so old habits still work.)
#
# bash 3.2 (macOS /bin/bash): no arrays beyond the basics, no mapfile, no ${var,,}.
set -euo pipefail

# Run from a copy: the pull below can replace this file while bash is still reading it.
if [ -z "${MINI_DEPLOY_COPY:-}" ]; then
  copy="$(mktemp "${TMPDIR:-/tmp}/mini-deploy.XXXXXX")"
  cp "$0" "$copy"
  MINI_DEPLOY_COPY="$copy" exec bash "$copy" "$@"
fi
trap 'rm -f "$MINI_DEPLOY_COPY"' EXIT

CHECKOUT="${HOMELAB_CHECKOUT:-${SF_CHECKOUT:-$HOME/agentic-ai-homelab}}"
HOOKS="$CHECKOUT/deploy/hooks"

say()  { printf '  %s\n' "$*"; }
fail() { echo "DEPLOY FAIL: $*"; exit 1; }

# run_hooks PHASE: every executable-or-not *.sh in deploy/hooks/PHASE.d, in name order.
# Returns the number of hooks that exited non-zero (capped at 1 for the caller's test).
run_hooks() {
  local phase="$1" bad=0 h out rc
  for h in "$HOOKS/$phase.d"/*.sh; do
    [ -e "$h" ] || continue
    rc=0
    out="$(CHECKOUT="$CHECKOUT" PREV="${PREV:-}" NOW="${NOW:-}" bash "$h" 2>&1)" || rc=$?
    if [ "$rc" -eq 0 ]; then
      say "$phase: $(basename "$h") ok"
    else
      say "$phase: $(basename "$h") RED (exit $rc)"; bad=1
    fi
    [ -n "$out" ] && printf '%s\n' "$out" | sed 's/^/      /'
  done
  return "$bad"
}

[ -d "$CHECKOUT/.git" ] || fail "no git checkout at $CHECKOUT (set HOMELAB_CHECKOUT)"

echo "== homelab deploy $(date -u +%Y-%m-%dT%H:%M:%SZ) =="

# a dirty checkout would be clobbered by the pull, or hide drift — refuse
[ -z "$(git -C "$CHECKOUT" status --porcelain)" ] || fail "checkout is dirty — commit or stash first"

PREV="$(git -C "$CHECKOUT" rev-parse --short HEAD)"
say "current: $PREV"
run_hooks pre-pull || say "pre-pull: a hook failed (the deploy continues)"

git -C "$CHECKOUT" pull --ff-only origin main >/dev/null 2>&1 \
  || fail "git pull --ff-only failed (diverged history? fetch + inspect manually)"
NOW="$(git -C "$CHECKOUT" rev-parse --short HEAD)"
say "pulled : $NOW$([ "$PREV" = "$NOW" ] && echo '  (no new commits — re-verifying anyway)')"

if ! run_hooks gate; then
  say "gates RED on $NOW — rolling the checkout back to $PREV"
  git -C "$CHECKOUT" reset --hard "$PREV" >/dev/null 2>&1
  run_hooks rollback || true
  fail "rolled back to $PREV; services keep running the code they had"
fi

echo "DEPLOY PASS ($NOW) — in-place services run the new code (fleetd on its next cycle; launchd jobs on their next run)."
echo "  rollback: git -C $CHECKOUT reset --hard $PREV"
