#!/usr/bin/env bash
# Prepare a training checkout for the robotics GPU slot (run as ops, the account that owns the GPU
# stacks): /opt/robotics/<project> at its pinned commit, and the cache folder the container writes as
# ops. Idempotent; it never touches a running training container.
#
#   infra/robotics/microduck/prepare.sh [PROJECT] [REF]
#     PROJECT  microduck_rl (default; pollen-robotics/microduck_rl, branch develop)
#              microduck-nav (chipi/microduck-nav: obstacle avoidance on Pollen's walker)
#     REF      defaults to the project's pin below; a bare 40-hex REF alone means microduck_rl
#
# The pins are reviewed commits. Change them here, in a reviewed commit, to train other code. The
# stack trains the project its .env names in ROBOTICS_PROJECT (docker-compose.yml).
set -euo pipefail
if [[ "${1:-}" =~ ^[0-9a-f]{40}$ ]]; then set -- microduck_rl "$1"; fi
PROJECT="${1:-microduck_rl}"
case "$PROJECT" in
  microduck_rl)
    REPO=https://github.com/pollen-robotics/microduck_rl
    PIN=0daab160d3fb1c2cbaba16a4a19052f36709dd9e ;;   # develop, 2026-11-13
  microduck-nav)
    REPO=https://github.com/chipi/microduck-nav
    PIN= ;;                                           # none reviewed yet: pass REF
  *) echo "PREPARE FAIL: unknown project $PROJECT (microduck_rl or microduck-nav)"; exit 1 ;;
esac
REF="${2:-$PIN}"
[ -n "$REF" ] || { echo "PREPARE FAIL: $PROJECT has no pinned commit yet: prepare.sh $PROJECT <REF>"; exit 1; }
ROOT="${ROBOTICS_ROOT:-/opt/robotics}"
SRC="$ROOT/$PROJECT"

[ "$(id -un)" = ops ] || { echo "PREPARE FAIL: run as ops (sudo -u ops $0)"; exit 1; }
[ -d "$ROOT" ] || { echo "PREPARE FAIL: $ROOT is missing; once, as an admin: sudo install -d -o ops -g ops $ROOT"; exit 1; }
mkdir -p "$ROOT/cache"
if [ ! -d "$SRC/.git" ]; then
  git clone --quiet "$REPO" "$SRC"
fi
git -C "$SRC" fetch --quiet origin
git -C "$SRC" checkout --quiet --detach "$REF"
echo "PREPARE PASS: $SRC at $(git -C "$SRC" rev-parse --short=12 HEAD); cache $ROOT/cache"
