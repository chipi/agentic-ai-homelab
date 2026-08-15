#!/bin/bash
# Langfuse trace-export health check. Verifies each LiteLLM gateway's Langfuse
# credentials are ACCEPTED (200) by the homelab Langfuse and emits
# langfuse_export_up{gateway} to local VictoriaMetrics.
#
# Why this exists: 2026-08-15 the OrbStack->colima migration reseeded Langfuse with
# fresh volumes + a new project key pair. LiteLLM kept the stale keys, 401'd on EVERY
# trace export, and logged NOTHING at any level — a silent 3h LLM-observability
# outage found only by chance. This turns that silent failure loud (alert in ~15m).
#
# Runs on the mini as a KeepAlive LaunchDaemon (com.homelab.langfuse-check).
set -uo pipefail
REPO=/Users/markodragoljevic/agentic-ai-homelab/infra
# /api/public/projects: authed + fast (~30ms, no ClickHouse) — a valid key pair 200s,
# a stale/rejected pair 401s. Same signal as querying traces but robust under load.
LF="http://127.0.0.1:4000/api/public/projects"
VM="http://localhost:8428/api/v1/import/prometheus"

val()  { grep "^$1=" "$2" 2>/dev/null | head -1 | cut -d= -f2-; }
probe(){ curl -s -o /dev/null -w '%{http_code}' -u "$1:$2" "$LF" --max-time 10; }  # 200 = keys accepted

while true; do
  {
    # --- homelab gateway (keys live on this box) ---
    hpk=$(val LANGFUSE_PUBLIC_KEY "$REPO/litellm/.env")
    hsk=$(val LANGFUSE_SECRET_KEY "$REPO/litellm/.env")
    if [ -n "$hpk" ]; then
      [ "$(probe "$hpk" "$hsk")" = "200" ] && u=1 || u=0
      printf 'langfuse_export_up{gateway="homelab"} %s\n' "$u"
    fi
    # --- prod gateway (optional) ---
    # Prod's LiteLLM keys are box-only (VPS). To also check prod FROM HERE, drop them
    # into infra/langfuse-check/prod.env (gitignored) as:
    #   PROD_LF_PUBLIC_KEY=pk-lf-...
    #   PROD_LF_SECRET_KEY=sk-lf-...
    # (Owned by the prod agent — see docs/wip/level3-prod-handover.md.)
    if [ -f "$REPO/langfuse-check/prod.env" ]; then
      # shellcheck disable=SC1091
      . "$REPO/langfuse-check/prod.env"
      if [ -n "${PROD_LF_PUBLIC_KEY:-}" ]; then
        [ "$(probe "$PROD_LF_PUBLIC_KEY" "${PROD_LF_SECRET_KEY:-}")" = "200" ] && u=1 || u=0
        printf 'langfuse_export_up{gateway="prod"} %s\n' "$u"
      fi
    fi
  } | curl -s -m8 -o /dev/null --data-binary @- "$VM"
  sleep 60
done
