#!/usr/bin/env bash
# A deploy stand-down on the mini in flotilla while this deploy runs (flotilla RFC-0004 §5.1): flotilla
# defers its planned actions on the mini for 30 minutes. flotilla's own script takes it (a hold by its
# `deploy` caller) and never fails; this hook, like every pre-pull hook, never blocks the deploy.
S="$HOME/flotilla/repo/deploy/mini/standdown.sh"
if [ ! -f "$S" ]; then
  echo "flotilla stand-down: $S not found (skipped)"
  exit 0
fi
bash "$S" mini 30m "homelab deploy from ${PREV:-?}"
