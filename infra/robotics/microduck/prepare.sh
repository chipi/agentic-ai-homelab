#!/usr/bin/env bash
# Prepare the Microduck training checkout for the robotics GPU slot (run as ops, the account that owns
# the GPU stacks): /opt/robotics/microduck_rl at the pinned commit, and the cache folder the container
# writes as ops. Idempotent; it never touches a running training container.
#
#   infra/robotics/microduck/prepare.sh [REF]     REF defaults to the pin below
#
# The pin is the reviewed commit of github.com/pollen-robotics/microduck_rl (branch develop). Change it
# here, in a reviewed commit, to train other code.
set -euo pipefail
MICRODUCK_REPO=https://github.com/pollen-robotics/microduck_rl
MICRODUCK_REF="${1:-0daab160d3fb1c2cbaba16a4a19052f36709dd9e}"   # develop, 2026-11-13
ROOT="${ROBOTICS_ROOT:-/opt/robotics}"
SRC="$ROOT/microduck_rl"

[ "$(id -un)" = ops ] || { echo "PREPARE FAIL: run as ops (sudo -u ops $0)"; exit 1; }
[ -d "$ROOT" ] || { echo "PREPARE FAIL: $ROOT is missing; once, as an admin: sudo install -d -o ops -g ops $ROOT"; exit 1; }
mkdir -p "$ROOT/cache"
if [ ! -d "$SRC/.git" ]; then
  git clone --quiet "$MICRODUCK_REPO" "$SRC"
fi
git -C "$SRC" fetch --quiet origin
git -C "$SRC" checkout --quiet --detach "$MICRODUCK_REF"
echo "PREPARE PASS: $SRC at $(git -C "$SRC" rev-parse --short=12 HEAD); cache $ROOT/cache"
