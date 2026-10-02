#!/usr/bin/env bash
# Check out the code as it was BEFORE the fix into a throwaway git worktree, so the
# replay can run the real old code next to the new one (any language: Python, TS, Go).
#
#   eval "$(baseline_worktree.sh <BASE_REV>)"   # exports BASELINE_DIR
#   ... run the replay once in "$BASELINE_DIR" and once in the working tree ...
#   baseline_worktree.sh --remove               # removes it again
#
# Read-only for your branch: a detached worktree under the system temp dir; your
# checkout, index and stash are untouched.
set -euo pipefail
root="$(git rev-parse --show-toplevel)"
dir="${TMPDIR:-/tmp}/replay-baseline-$(basename "$root")"
if [ "${1:-}" = "--remove" ]; then
  git -C "$root" worktree remove --force "$dir" 2>/dev/null || true
  echo "removed $dir" >&2
  exit 0
fi
rev="${1:?usage: baseline_worktree.sh <BASE_REV> | --remove}"
git -C "$root" rev-parse --verify --quiet "$rev^{commit}" >/dev/null || { echo "unknown revision: $rev" >&2; exit 2; }
git -C "$root" worktree remove --force "$dir" 2>/dev/null || true
git -C "$root" worktree add --detach --quiet "$dir" "$rev"
echo "baseline $(git -C "$dir" rev-parse --short HEAD) at $dir" >&2
echo "export BASELINE_DIR='$dir'"
