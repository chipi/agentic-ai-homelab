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
#   OR_KEY_ORRERY=sk-or-...      (== OPENROUTER_API_KEY_ORRERY; the orrery /ask vertical,
#                                 dedicated key on both the prod + mini litellm — /auth/key
#                                 reports its GLOBAL usage across both instances)
#   OR_KEY_EVALS=sk-or-...       (== OPENROUTER_API_KEY_EVALS; eval-harness sweeps, added
#                                 2026-11-02 after $16.64 of its spend went uncollected)
#   OR_KEY_PI=                   (blank until pi gets its own key)
#   OR_KEY_OPENCODE=             (blank until opencode gets its own key)
#
# /auth/key returns usage for THE KEY MAKING THE CALL — that's why every key
# must be present here; there is no list-all endpoint on a normal key.
# Metrics (gauges, absolute USD as OpenRouter reports them):
#   openrouter_vertical_usd{vertical, window="day|week|month|total"}
#   openrouter_account_usd{kind="credits|usage"}   account-wide, from /api/v1/credits (any key
#     can read it). usage minus the sum of the vertical totals is spend on keys this file
#     does not hold (the VPS, dev machines, deleted keys): $94 of $229.62 on 2026-11-02.
#   openrouter_key_usd{key, workspace, disabled, window}   EVERY key on the account, from the
#     provisioning key in openrouter-provisioning.env (gitignored, mode 600; it can create and
#     delete keys, so it lives in its own file). GET /workspaces, then GET /keys per workspace:
#     a provisioning key lists only its own workspace without workspace_id. The $94 was
#     pi-key $72.75, photo-key $15.12, opencode-key $6.35 (2026-11-02).
VM=http://localhost:8428/api/v1/import/prometheus
HERE="$(cd "$(dirname "$0")" && pwd)"
ENVF="$HERE/openrouter-verticals.env"

poll() {
  [ -f "$ENVF" ] || { echo "no $ENVF — nothing to do"; return; }
  # shellcheck disable=SC1090
  . "$ENVF"
  local LINES=""
  for V in pi:$OR_KEY_PI opencode:$OR_KEY_OPENCODE gateway:$OR_KEY_GATEWAY podcast:$OR_KEY_PODCAST orrery:$OR_KEY_ORRERY evals:$OR_KEY_EVALS; do
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
  local AK="${OR_KEY_GATEWAY:-$OR_KEY_PODCAST}" CJ C U
  if [ -n "$AK" ]; then
    CJ=$(curl -s -m 15 https://openrouter.ai/api/v1/credits -H "Authorization: Bearer $AK")
    C=$(echo "$CJ" | /usr/bin/python3 -c "import json,sys; print(json.load(sys.stdin)['data']['total_credits'])" 2>/dev/null)
    U=$(echo "$CJ" | /usr/bin/python3 -c "import json,sys; print(json.load(sys.stdin)['data']['total_usage'])" 2>/dev/null)
    if [ -n "$C" ] && [ -n "$U" ]; then
      LINES+="openrouter_account_usd{kind=\"credits\",service=\"openrouter-spend\",environment=\"operations\"} $C
openrouter_account_usd{kind=\"usage\",service=\"openrouter-spend\",environment=\"operations\"} $U
"
    fi
  fi
  local PF="$HERE/openrouter-provisioning.env"
  if [ -f "$PF" ]; then
    LINES+=$(OR_PROVISIONING_KEY="$(sed -n 's/^OR_PROVISIONING_KEY=//p' "$PF")" /usr/bin/python3 - <<'PY' 2>/dev/null
import json, os, urllib.request
pk = os.environ.get("OR_PROVISIONING_KEY", "").strip()
def get(path):
    req = urllib.request.Request("https://openrouter.ai/api/v1" + path, headers={"Authorization": "Bearer " + pk})
    return json.load(urllib.request.urlopen(req, timeout=20))["data"]
if pk:
    esc = lambda s: str(s or "-").replace("\\", "").replace('"', "")
    for w in get("/workspaces"):
        for k in get(f"/keys?include_disabled=true&workspace_id={w['id']}"):
            lab = f'key="{esc(k.get("name"))}",workspace="{esc(w.get("name"))}",disabled="{str(bool(k.get("disabled"))).lower()}",service="openrouter-spend",environment="operations"'
            for win, f in (("total", "usage"), ("day", "usage_daily"), ("week", "usage_weekly"), ("month", "usage_monthly")):
                print(f'openrouter_key_usd{{{lab},window="{win}"}} {k.get(f) or 0}')
    # Per key x model x provider: GET /activity returns one row per day x model x provider
    # endpoint for the last 30 COMPLETED UTC days (today is never in it); ?api_key_hash=<hash>
    # narrows it to one key (found by trying names 2026-11-02: it returned 140 of 536 rows for
    # evals-harness; key_hash and key are ignored). vendor = the maker (anthropic/...),
    # provider = who served it (novita/fp8 -> novita).
    # Windows, the same for every series so the hub can compare them: "month" = this UTC
    # calendar month's completed days, "30d", "7d", "yesterday" = the latest completed day.
    # Spend on keys that no longer exist stays in the account-wide /activity only; it is
    # emitted as key="(deleted keys)" so the per-key series always sum to the account.
    from collections import defaultdict
    import datetime
    allrows = get("/activity")
    days = sorted({r["date"][:10] for r in allrows})
    month = datetime.datetime.utcnow().strftime("%Y-%m")
    wins = lambda d: [w for w, ok in (("30d", True), ("7d", d in days[-7:]), ("yesterday", bool(days) and d == days[-1]),
                                       ("month", d.startswith(month))) if ok]
    agg = defaultdict(lambda: defaultdict(float))
    def add(rows, keyname, wsname, sign=1):
        for r in rows:
            d, m = r["date"][:10], r.get("model") or "-"
            base = (keyname, wsname, m, m.split("/")[0], (r.get("provider_name") or "-").split("/")[0])
            for w in wins(d):
                a = agg[base + (w,)]
                a["usd"] += sign * float(r.get("usage") or 0); a["req"] += sign * int(r.get("requests") or 0)
                a["prompt"] += sign * int(r.get("prompt_tokens") or 0); a["completion"] += sign * int(r.get("completion_tokens") or 0)
    add(allrows, "(deleted keys)", "-")
    for w in get("/workspaces"):
        for k in get(f"/keys?include_disabled=true&workspace_id={w['id']}"):
            rows = get(f"/activity?api_key_hash={k['hash']}")
            add(rows, k.get("name"), w.get("name"))
            add(rows, "(deleted keys)", "-", -1)
    for (key, ws, m, ven, prov, w), a in agg.items():
        if key == "(deleted keys)" and abs(a["usd"]) < 1e-6 and abs(a["req"]) < 1: continue
        lab = (f'key="{esc(key)}",workspace="{esc(ws)}",model="{esc(m)}",vendor="{esc(ven)}",provider="{esc(prov)}",'
               f'window="{w}",service="openrouter-spend",environment="operations"')
        print(f'openrouter_model_usd{{{lab}}} {round(a["usd"], 6)}')
        print(f'openrouter_model_requests{{{lab}}} {int(a["req"])}')
        print(f'openrouter_model_tokens{{{lab},kind="prompt"}} {int(a["prompt"])}')
        print(f'openrouter_model_tokens{{{lab},kind="completion"}} {int(a["completion"])}')
    # one gauge per vendor per day, account-wide, for the Spend tab's daily sparklines
    vday = defaultdict(float)
    for r in allrows:
        vday[((r.get("model") or "-").split("/")[0], r["date"][:10])] += float(r.get("usage") or 0)
    for (ven, d), usd in vday.items():
        print(f'openrouter_vendor_day_usd{{vendor="{esc(ven)}",day="{d}",service="openrouter-spend",environment="operations"}} {usd}')
PY
)
    LINES+=$'\n'
  fi
  [ -n "$LINES" ] && printf '%s' "$LINES" | curl -s -o /dev/null --data-binary @- "$VM"
}

while true; do
  poll
  sleep 600
done
