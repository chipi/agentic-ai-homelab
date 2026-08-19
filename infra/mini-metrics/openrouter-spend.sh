#!/bin/bash
# Per-vertical OpenRouter spend -> VictoriaMetrics (homepage cards + weekly
# reconciliation ritual). Separate-key-per-vertical was INTENDED, but as of
# 2026-08-18 only TWO keys actually exist: a SHARED key used by the litellm
# gateway + triage fleet + bugfix-fleet (the pi/opencode bake-off all run on it),
# and a separate podcast key. So pi/opencode can't be broken out yet — their spend
# lands under the shared 'gateway' label. Keep OR_KEY_PI/OPENCODE BLANK until each
# is minted its own OpenRouter key (else the shared spend double-counts under 3
# labels). The loop skips empty keys.
#
# Keys live in openrouter-verticals.env next to this script (gitignored; the
# operator home dir is chmod 700 so the claude workbench user can't read it):
#   OR_KEY_GATEWAY=sk-or-...     (the SHARED key; == infra/litellm OPENROUTER_API_KEY)
#   OR_KEY_PODCAST=sk-or-...     (== OPENROUTER_API_KEY_PODCAST)
#   OR_KEY_PI=                   (blank until pi gets its own key)
#   OR_KEY_OPENCODE=             (blank until opencode gets its own key)
#
# /auth/key returns usage for THE KEY MAKING THE CALL — that's why every key
# must be present here; there is no list-all endpoint on a normal key.
# Metrics (gauges, absolute USD as OpenRouter reports them):
#   openrouter_vertical_usd{vertical, window="day|week|month|total"}
VM=http://localhost:8428/api/v1/import/prometheus
HERE="$(cd "$(dirname "$0")" && pwd)"
ENVF="$HERE/openrouter-verticals.env"

poll() {
  [ -f "$ENVF" ] || { echo "no $ENVF — nothing to do"; return; }
  # shellcheck disable=SC1090
  . "$ENVF"
  local LINES=""
  for V in pi:$OR_KEY_PI opencode:$OR_KEY_OPENCODE gateway:$OR_KEY_GATEWAY podcast:$OR_KEY_PODCAST; do
    local NAME="${V%%:*}" KEY="${V#*:}"
    [ -n "$KEY" ] || continue
    local J
    J=$(curl -s -m 15 https://openrouter.ai/api/v1/auth/key -H "Authorization: Bearer $KEY")
    local T D W M
    T=$(echo "$J" | /usr/bin/python3 -c "import json,sys; d=json.load(sys.stdin).get('data',{}); print(d.get('usage') or 0)" 2>/dev/null)
    D=$(echo "$J" | /usr/bin/python3 -c "import json,sys; d=json.load(sys.stdin).get('data',{}); print(d.get('usage_daily') or 0)" 2>/dev/null)
    W=$(echo "$J" | /usr/bin/python3 -c "import json,sys; d=json.load(sys.stdin).get('data',{}); print(d.get('usage_weekly') or 0)" 2>/dev/null)
    M=$(echo "$J" | /usr/bin/python3 -c "import json,sys; d=json.load(sys.stdin).get('data',{}); print(d.get('usage_monthly') or 0)" 2>/dev/null)
    [ -n "$T" ] || continue   # auth/network failure: skip silently, keep last sample
    LINES+="openrouter_vertical_usd{vertical=\"$NAME\",window=\"total\",service=\"openrouter-spend\",environment=\"operations\"} $T
openrouter_vertical_usd{vertical=\"$NAME\",window=\"day\",service=\"openrouter-spend\",environment=\"operations\"} $D
openrouter_vertical_usd{vertical=\"$NAME\",window=\"week\",service=\"openrouter-spend\",environment=\"operations\"} $W
openrouter_vertical_usd{vertical=\"$NAME\",window=\"month\",service=\"openrouter-spend\",environment=\"operations\"} $M
"
  done
  [ -n "$LINES" ] && printf '%s' "$LINES" | curl -s -o /dev/null --data-binary @- "$VM"
}

while true; do
  poll
  sleep 600
done
