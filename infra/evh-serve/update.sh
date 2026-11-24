#!/usr/bin/env bash
# Keeps each eval project's catalog and MCP server current on the mini. Run by launchd every 5 minutes
# (com.homelab.evh-serve), and safe to run by hand at any time:
#   update.sh                     every instance in instances/
#   update.sh fleet-evals         one instance
#   update.sh fleet-evals --force rebuild the catalog at the same commit
# Per instance: sync the checkout volume to the branch; build the harness image when the pin is new;
# rebuild the catalog when the commit moved; make sure catalog and mcp run. One line per instance:
# OK, UP TO DATE or FAIL. Exit 1 when any instance failed.
set -uo pipefail
export PATH=/usr/local/bin:/opt/homebrew/bin:$PATH
HERE="$(cd "$(dirname "$0")" && pwd)"
KEYS="${EVH_SERVE_KEYS:-$HOME/.config/evh-serve}"
LOCK=/tmp/evh-serve.lock
ts() { date -u +%FT%TZ; }

if ! mkdir "$LOCK" 2>/dev/null; then
  holder="$(cat "$LOCK/pid" 2>/dev/null)"
  if [ -n "$holder" ] && kill -0 "$holder" 2>/dev/null; then echo "$(ts) BUSY another update is running (pid $holder)"; exit 0; fi
  rm -rf "$LOCK"; mkdir "$LOCK" || { echo "$(ts) FAIL could not take the lock $LOCK"; exit 1; }
fi
echo $$ > "$LOCK/pid"
trap 'rm -rf "$LOCK"' EXIT

one() {
  local inst=$1 force=${2:-} env="$HERE/instances/$1.env"
  say() { echo "$(ts) [$inst] $*"; }
  [ -f "$env" ] || { say "FAIL no $env"; return 1; }
  local key="$KEYS/${inst}_deploy_key"
  [ -f "$key" ] || { say "FAIL no deploy key at $key"; return 1; }
  local own_ref; own_ref="$(sed -nE 's/^HARNESS_REF=([0-9a-f]{40})$/\1/p' "$env")"
  dc() { docker compose -p "$inst" --project-directory "$HERE" -f "$HERE/docker-compose.yml" --env-file "$env" "$@"; }

  local out sha pin deployed ref
  out="$(HARNESS_REF="${own_ref:-none}" dc run --rm -T sync < "$key" 2>&1)" || { say "FAIL sync: $(echo "$out" | tail -2 | tr '\n' ' ')"; return 1; }
  sha="$(sed -n 's/^SHA=//p' <<<"$out")"; pin="$(sed -n 's/^PIN=//p' <<<"$out")"; deployed="$(sed -n 's/^DEPLOYED=//p' <<<"$out")"
  ref="${pin:-$own_ref}"
  [ -n "$ref" ] || { say "FAIL no harness pin: none in pyproject.toml, none in $env"; return 1; }
  export HARNESS_REF="$ref" COMMIT="$sha"

  if ! docker image inspect "local/evh-serve:$ref" >/dev/null 2>&1; then
    say "building the image for harness ${ref:0:8}"
    docker build -q --build-arg HARNESS_REF="$ref" -t "local/evh-serve:$ref" "$HERE" >/dev/null || { say "FAIL image build (harness $ref)"; return 1; }
  fi

  local built=""
  if [ "$deployed" != "$sha" ] || [ "$force" = --force ]; then
    out="$(dc run --rm -T catalog-build 2>&1)" || { say "FAIL catalog build at ${sha:0:7}; the previous catalog still serves: $(echo "$out" | tail -2 | tr '\n' ' ')"; return 1; }
    built=1
  fi
  out="$(dc up -d --quiet-pull catalog mcp 2>&1)" || { say "FAIL catalog/mcp up: $(echo "$out" | tail -2 | tr '\n' ' ')"; return 1; }
  if [ -n "$built" ]; then say "OK ${deployed:0:7}${deployed:+ }-> ${sha:0:7} (harness ${ref:0:8})"
  else say "UP TO DATE ${sha:0:7} (harness ${ref:0:8})"; fi
}

rc=0
if [ -n "${1:-}" ]; then
  one "$1" "${2:-}" || rc=1
else
  for f in "$HERE"/instances/*.env; do one "$(basename "$f" .env)" || rc=1; done
fi
exit $rc
