#!/usr/bin/env bash
# second-brain on the mini: the read server and its weekly index build. Run by launchd on Sundays
# (com.homelab.second-brain), and safe to run by hand at any time:
#   update.sh        the weekly run: images, token, sync the content, fetch, fulltext, build, push the
#                    metrics, keep the server up
#   update.sh up     images, token and the server only (install, or after a change here)
# A failed step leaves the previous index serving. One line at the end: OK or FAIL. Exit 1 on FAIL.
# SB_BATCH_ARGS (unset in production) goes to fetch and fulltext, e.g. "--limit 3" for a test run.
set -uo pipefail
export PATH=/usr/local/bin:/opt/homebrew/bin:$PATH
HERE="$(cd "$(dirname "$0")" && pwd)"
KEYS="${SB_KEYS:-$HOME/.config/second-brain}"
LOCK=/tmp/second-brain.lock
ts() { date -u +%FT%TZ; }
say() { echo "$(ts) $*"; }
fail() { say "FAIL $*"; exit 1; }

if ! mkdir "$LOCK" 2>/dev/null; then
  holder="$(cat "$LOCK/pid" 2>/dev/null)"
  if [ -n "$holder" ] && kill -0 "$holder" 2>/dev/null; then say "BUSY another run is going (pid $holder)"; exit 0; fi
  rm -rf "$LOCK"; mkdir "$LOCK" || fail "could not take the lock $LOCK"
fi
echo $$ > "$LOCK/pid"
trap 'rm -rf "$LOCK"' EXIT

set -a
# shellcheck disable=SC1091
. "$HERE/second-brain.env"
set +a
dc() { docker compose --project-directory "$HERE" -f "$HERE/docker-compose.yml" --env-file "$HERE/second-brain.env" "$@"; }
tail2() { tail -2 <<<"$1" | tr '\n' ' '; }

for t in serve build; do
  img="local/second-brain:$t-$SB_REF"
  docker image inspect "$img" >/dev/null 2>&1 && continue
  say "building $img"
  out="$(docker build -q --target "$t" -t "$img" "https://github.com/chipi/second-brain.git#$SB_REF" 2>&1)" \
    || fail "image $t at ${SB_REF:0:7}: $(tail2 "$out")"
done

[ -s "$KEYS/sb-token" ] || fail "no token at $KEYS/sb-token"
out="$(dc run --rm -T token < "$KEYS/sb-token" 2>&1)" || fail "token: $(tail2 "$out")"

if [ "${1:-}" != up ]; then
  [ -f "$KEYS/content_deploy_key" ] || fail "no deploy key at $KEYS/content_deploy_key"
  out="$(dc run --rm -T sync < "$KEYS/content_deploy_key" 2>&1)" || fail "sync: $(tail2 "$out")"
  sha="$(sed -n 's/^SHA=//p' <<<"$out")"
  [ -n "$sha" ] || fail "sync printed no commit"
  # A paper that will not fetch is skipped and retried next run; it never fails the step (operator,
  # 2026-11-26: one rate-limited PDF of 291 kept the first index from ever serving). Its count is in
  # the step's metrics file. The step still fails on its own errors.
  for step in fetch fulltext; do
    # shellcheck disable=SC2086  # SB_BATCH_ARGS is word-split on purpose (e.g. "--limit 3" for a test run)
    out="$(dc run --rm -T batch "$step" --content /content --data /data --metrics-file "/out/$step.prom" --max-failed-share 1 ${SB_BATCH_ARGS:-} 2>&1)" \
      || fail "$step at ${sha:0:7}; the previous index still serves: $(tail2 "$out")"
  done
  out="$(dc run --rm -T batch build --content /content --data /data --version "${sha:0:7}" --metrics-file /out/build.prom 2>&1)" \
    || fail "build at ${sha:0:7}; the previous index still serves: $(tail2 "$out")"
  # Keep the index current points at and the one before it; build never removes old ones.
  # shellcheck disable=SC2016  # the script runs in the container, where $cur expands
  dc run --rm -T --entrypoint sh batch -c \
    'cd /data && cur=$(readlink current) && ls -1dt index-* | grep -vx "$cur" | tail -n +2 | while read -r d; do rm -rf "$d"; done' >/dev/null 2>&1 \
    || say "WARN could not prune old index folders"
fi

out="$(dc up -d --quiet-pull mcp 2>&1)" || fail "sb-mcp up: $(tail2 "$out")"
if [ "${1:-}" != up ]; then
  out="$(dc run --rm -T push 2>&1)" || fail "metrics push (the index is built and served): $(tail2 "$out")"
  say "OK content ${sha:0:7}, sb ${SB_REF:0:7}"
else
  say "OK sb-mcp up, sb ${SB_REF:0:7}"
fi
