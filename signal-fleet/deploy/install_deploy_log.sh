#!/usr/bin/env bash
# signal-fleet/deploy/install_deploy_log.sh — make every change of the fleet checkout's HEAD land in the deploy log.
#
# Installs a post-merge hook in the checkout (any `git pull` that moves HEAD, whoever runs it: deploy.sh or another
# pull) that calls log_deploy.sh. Rollbacks (`git reset --hard` in deploy.sh) do not fire post-merge, so deploy.sh
# logs those itself. When the log does not exist yet it is first backfilled once from the checkout's reflog (oldest
# first), so the history before the log is kept when the reflog expires. Idempotent: safe to run on every deploy.
set -eu
CHECKOUT="${SF_CHECKOUT:-$HOME/agentic-ai-homelab}"
LOG="${SF_DEPLOY_LOG:-$HOME/signal-fleet/results/deploys.tsv}"
HOOK="$CHECKOUT/.git/hooks/post-merge"
MARK="# signal-fleet deploy log (install_deploy_log.sh)"
LOGGER="$CHECKOUT/signal-fleet/deploy/log_deploy.sh"

# 1. backfill, before anything writes the log: every reflog entry as (time, previous HEAD, HEAD), oldest first
if [ ! -s "$LOG" ]; then
  tmp="$(mktemp)"
  git -C "$CHECKOUT" reflog --date=iso-strict --format='%gd %H' > "$tmp.desc"
  { tac "$tmp.desc" 2>/dev/null || tail -r "$tmp.desc"; } > "$tmp"
  prev=""
  while read -r gd sha; do
    at="$(printf '%s' "$gd" | sed -E 's/^HEAD@\{(.*)\}$/\1/')"
    utc="$(python3 -c 'import sys,datetime;print(datetime.datetime.fromisoformat(sys.argv[1]).astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))' "$at" 2>/dev/null || echo "$at")"
    SF_DEPLOY_AT="$utc" bash "$LOGGER" reflog-backfill "${prev:-$sha}" "$sha" reflog
    prev="$sha"
  done < "$tmp"
  rm -f "$tmp" "$tmp.desc"
  echo "backfilled $(($(wc -l < "$LOG") - 1)) reflog entries into $LOG"
fi

# 2. the hook: every later pull that moves HEAD
if ! grep -qF "$MARK" "$HOOK" 2>/dev/null; then
  [ -e "$HOOK" ] && { echo "REFUSED: $HOOK exists and is not ours; merge it by hand"; exit 2; }
  cat > "$HOOK" <<EOF
#!/usr/bin/env bash
$MARK
bash "\$(git rev-parse --show-toplevel)/signal-fleet/deploy/log_deploy.sh" pull ORIG_HEAD HEAD "\${USER:-?}"
EOF
  chmod +x "$HOOK"
  bash "$LOGGER" install HEAD HEAD "${USER:-?}"
  echo "installed $HOOK"
fi
echo "deploy log: $LOG"
