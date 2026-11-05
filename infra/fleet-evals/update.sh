#!/bin/bash
# Deploy a new version of the fleet-eval-data catalog, on demand (no timer: the operator deploys, 2026-11-05).
# From the laptop: ssh homelab '~/agentic-ai-homelab/infra/fleet-evals/update.sh'  [--force]
# When the checkout's origin/main moved (or the site is not up, or --force): fast-forward, build the
# pages with the harness the checkout pins, and (re)start the web container. A failed build leaves the
# previous site serving.
set -uo pipefail
export PATH=/usr/local/bin:/opt/homebrew/bin:$PATH
REPO="${FLEET_EVAL_DATA:-$HOME/fleet-eval-data}"
HERE="$(cd "$(dirname "$0")" && pwd)"
ts() { date -u +%FT%TZ; }

cd "$REPO" || { echo "$(ts) FAIL no checkout at $REPO"; exit 1; }
git fetch -q origin main || { echo "$(ts) FAIL git fetch"; exit 1; }
old="$(git rev-parse HEAD)"; new="$(git rev-parse origin/main)"
up="$(docker inspect -f '{{.State.Running}}' fleet-evals-web 2>/dev/null)"
if [ "$old" = "$new" ] && [ "$up" = true ] && [ "${1:-}" != --force ]; then
  echo "$(ts) UP TO DATE ${new:0:7} (nothing to deploy; --force rebuilds)"; exit 0
fi

git merge -q --ff-only origin/main || { echo "$(ts) FAIL $old -> $new is not a fast-forward"; exit 1; }
ref="$(sed -nE 's/.*eval-harness@([0-9a-f]{40}).*/\1/p' pyproject.toml | head -1)"
[ -n "$ref" ] || { echo "$(ts) FAIL no eval-harness pin in pyproject.toml"; exit 1; }

cd "$HERE" || exit 1
export HARNESS_REF="$ref" FLEET_EVAL_DATA="$REPO"
docker compose --profile build build build >/dev/null || { echo "$(ts) FAIL image build (harness $ref)"; exit 1; }
docker compose --profile build run --rm build || { echo "$(ts) FAIL catalog build at ${new:0:7}; the previous site still serves"; exit 1; }
docker compose up -d web || { echo "$(ts) FAIL web up"; exit 1; }
echo "$(ts) OK ${old:0:7} -> ${new:0:7} (harness ${ref:0:8})"
