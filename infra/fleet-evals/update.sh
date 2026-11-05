#!/bin/bash
# Deploy a new version of the fleet-eval-data catalog, on demand (no timer: the operator deploys, 2026-11-05).
# From any agent's machine (the X3 or the laptop; the same key and user host-run uses):
#   ssh -i ~/.ssh/homelab_mini -o IdentitiesOnly=yes markodragoljevic@homelab '~/agentic-ai-homelab/infra/fleet-evals/update.sh'  [--force]
# When GitHub's main differs from the commit the site was built from (or the site is not up, or
# --force): fast-forward the checkout, build the pages with the harness it pins, swap them in only if
# the build passed, and (re)start the web container. The last line is OK, UP TO DATE, BUSY or FAIL.
#
# The deploy itself runs detached (nohup, log /tmp/fleet-evals.log) and this call follows it, so a
# dropped ssh connection or a caller's timeout cannot stop a build halfway (the old version merged
# first and built second, so a run killed in between left the checkout looking current while the
# site was not). Running the command again is always safe: it compares against what is deployed.
set -uo pipefail
export PATH=/usr/local/bin:/opt/homebrew/bin:$PATH
REPO="${FLEET_EVAL_DATA:-$HOME/fleet-eval-data}"
HERE="$(cd "$(dirname "$0")" && pwd)"
LOG=/tmp/fleet-evals.log
LOCK=/tmp/fleet-evals.lock
ts() { date -u +%FT%TZ; }

if [ -z "${FLEET_EVALS_RUN:-}" ]; then
  run="$(date +%s)-$$"
  touch "$LOG"; n="$(wc -l < "$LOG")"
  FLEET_EVALS_RUN="$run" nohup "$0" "$@" >> "$LOG" 2>&1 < /dev/null &
  pid=$!
  while :; do
    total="$(wc -l < "$LOG")"
    [ "$total" -gt "$n" ] && { sed -n "$((n + 1)),${total}p" "$LOG"; n="$total"; }
    result="$(grep -E "\[$run\] (OK|UP TO DATE|BUSY|FAIL)" "$LOG" | tail -1)"
    if [ -z "$result" ] && ! kill -0 "$pid" 2>/dev/null; then
      sleep 1; result="$(grep -E "\[$run\] (OK|UP TO DATE|BUSY|FAIL)" "$LOG" | tail -1)"
      [ -n "$result" ] || { echo "$(ts) FAIL the deploy ended without a result; see $LOG"; exit 1; }
    fi
    if [ -n "$result" ]; then
      total="$(wc -l < "$LOG")"; [ "$total" -gt "$n" ] && sed -n "$((n + 1)),${total}p" "$LOG"
      case "$result" in *"] OK "*|*"] UP TO DATE"*) exit 0 ;; *) exit 1 ;; esac
    fi
    sleep 2
  done
fi

say() { echo "$(ts) [$FLEET_EVALS_RUN] $*"; }
# One deploy at a time; a lock left by a killed run (its pid gone) is taken over.
if ! mkdir "$LOCK" 2>/dev/null; then
  holder="$(cat "$LOCK/pid" 2>/dev/null)"
  if [ -n "$holder" ] && kill -0 "$holder" 2>/dev/null; then say "BUSY another deploy is running (pid $holder)"; exit 1; fi
  rm -rf "$LOCK"; mkdir "$LOCK" || { say "FAIL could not take the lock $LOCK"; exit 1; }
fi
echo $$ > "$LOCK/pid"
trap 'rm -rf "$LOCK"' EXIT

cd "$REPO" || { say "FAIL no checkout at $REPO"; exit 1; }
git fetch -q origin main || { say "FAIL git fetch"; exit 1; }
new="$(git rev-parse origin/main)"
deployed="$(docker exec fleet-evals-web cat /site/live/.deployed 2>/dev/null)"
if [ "$deployed" = "$new" ] && [ "${1:-}" != --force ]; then
  say "UP TO DATE ${new:0:7} is deployed (--force rebuilds)"; exit 0
fi

git merge -q --ff-only origin/main || { say "FAIL $(git rev-parse --short HEAD) -> ${new:0:7} is not a fast-forward"; exit 1; }
ref="$(sed -nE 's/.*eval-harness@([0-9a-f]{40}).*/\1/p' pyproject.toml | head -1)"
[ -n "$ref" ] || { say "FAIL no eval-harness pin in pyproject.toml"; exit 1; }

cd "$HERE" || exit 1
export HARNESS_REF="$ref" FLEET_EVAL_DATA="$REPO" COMMIT="$new"
say "building ${new:0:7} (harness ${ref:0:8}; about 15 minutes)"
docker compose --profile build build build >/dev/null || { say "FAIL image build (harness $ref)"; exit 1; }
docker compose --profile build run --rm build || { say "FAIL catalog build at ${new:0:7}; the previous site still serves"; exit 1; }
docker compose up -d web || { say "FAIL web up"; exit 1; }
say "OK ${deployed:0:7}${deployed:+ }-> ${new:0:7} deployed (harness ${ref:0:8})"
