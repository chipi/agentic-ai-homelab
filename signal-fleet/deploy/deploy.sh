#!/usr/bin/env bash
# signal-fleet/deploy/deploy.sh — deploy the signal-fleet MVP to the running fleet.
#
# The fleet runs its cycle from the GIT CHECKOUT: fleetd's triage block sets
# workdir = ~/agentic-ai-homelab/signal-fleet/mvp and runs `python3 orchestrator.py`
# fresh every 10-min cycle. So DEPLOY = `git pull` the checkout — no scp, no
# restart, no launchctl. The code goes live on the next cycle.
# (The ~/signal-fleet/mvp/ directory is a vestigial leftover of the OLD scp method
#  and is NOT used; only ~/signal-fleet/{results,queue,*.env} state is live.)
#
# Run ON the mini as the fleet user:   bash signal-fleet/deploy/deploy.sh
#
# It pulls main, then runs the three DETERMINISTIC gates (no LLM, no network) over
# the freshly-pulled code. If any gate is red, it auto-rolls-back the checkout to
# the previous commit so the fleet never picks up broken code.
set -euo pipefail

CHECKOUT="${SF_CHECKOUT:-$HOME/agentic-ai-homelab}"
SF="$CHECKOUT/signal-fleet"

say()  { printf '  %s\n' "$*"; }
fail() { echo "DEPLOY FAIL: $*"; exit 1; }

[ -d "$CHECKOUT/.git" ]            || fail "no git checkout at $CHECKOUT (set SF_CHECKOUT)"
[ -f "$SF/mvp/orchestrator.py" ]  || fail "$SF/mvp not found — wrong checkout?"

echo "== signal-fleet deploy $(date -u +%Y-%m-%dT%H:%M:%SZ) =="

# a dirty checkout would be clobbered by pull / hide drift — refuse
[ -z "$(git -C "$CHECKOUT" status --porcelain)" ] || fail "checkout is dirty — commit or stash first"

PREV="$(git -C "$CHECKOUT" rev-parse --short HEAD)"
say "current: $PREV"
git -C "$CHECKOUT" pull --ff-only origin main >/dev/null 2>&1 \
  || fail "git pull --ff-only failed (diverged history? fetch + inspect manually)"
NOW="$(git -C "$CHECKOUT" rev-parse --short HEAD)"
say "pulled : $NOW$([ "$PREV" = "$NOW" ] && echo '  (no new commits — re-verifying anyway)')"

# verify the deployed code with the deterministic gates (no LLM, no network, no cost)
say "verifying: eval_hardening · eval_dedup · test_units"
cd "$SF/mvp"
ok=1
for g in eval_hardening.py eval_dedup.py test_units.py; do
  if SF_OBSERV_DISABLED=1 python3 "$g" >"/tmp/sf-deploy-$g.log" 2>&1; then
    say "  PASS $g"
  else
    say "  FAIL $g:"; tail -3 "/tmp/sf-deploy-$g.log" | sed 's/^/        /'; ok=0
  fi
done

if [ "$ok" -ne 1 ]; then
  say "gates RED on $NOW — rolling checkout back to $PREV so the fleet stays on known-good code"
  git -C "$CHECKOUT" reset --hard "$PREV" >/dev/null 2>&1
  fail "rolled back to $PREV; running fleet unaffected"
fi

echo "DEPLOY PASS ($NOW) — fleetd runs the new code on its next 10-min cycle."
echo "  watch:    tail -f ~/fleetd/fleetd.log"
echo "  rollback: git -C $CHECKOUT reset --hard $PREV"
