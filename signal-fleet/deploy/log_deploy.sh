#!/usr/bin/env bash
# signal-fleet/deploy/log_deploy.sh — append one line to the fleet's deploy log: which code the fleet runs from when.
#
#   log_deploy.sh EVENT OLD NEW [BY]     EVENT: pull | rollback | install | reflog-backfill
#
# The fleet runs each cycle from the checkout (deploy.sh), so every change of HEAD there is a deploy. The log is
# what the filing replay reads to run each decision on the code its cycle ran (the reflog it used before expires
# after 90 days and is per-machine). One line per change, tab-separated:
#   utc  event  old  new  mvp_tree  by
# mvp_tree is the hash of signal-fleet/mvp at NEW: two commits with the same tree ran the same fleet code.
# Never fails the caller: a logging problem must not break a pull or a deploy.
set -u
LOG="${SF_DEPLOY_LOG:-$HOME/signal-fleet/results/deploys.tsv}"
CHECKOUT="${SF_CHECKOUT:-$HOME/agentic-ai-homelab}"
event="${1:-?}"; old="${2:-}"; new="${3:-}"; by="${4:-${USER:-?}}"
{
  mkdir -p "$(dirname "$LOG")"
  [ -s "$LOG" ] || printf 'utc\tevent\told\tnew\tmvp_tree\tby\n' > "$LOG"
  # --verify -q: on failure (a commit from before signal-fleet/mvp existed) print nothing, not the argument
  tree="$(git -C "$CHECKOUT" rev-parse --verify -q "${new}:signal-fleet/mvp" 2>/dev/null)" || tree=-
  printf '%s\t%s\t%s\t%s\t%s\t%s\n' "${SF_DEPLOY_AT:-$(date -u +%Y-%m-%dT%H:%M:%SZ)}" "$event" \
    "$(git -C "$CHECKOUT" rev-parse --verify -q --short "$old" 2>/dev/null || echo "$old")" \
    "$(git -C "$CHECKOUT" rev-parse --verify -q --short "$new" 2>/dev/null || echo "$new")" "$tree" "$by" >> "$LOG"
} 2>/dev/null || true
exit 0
