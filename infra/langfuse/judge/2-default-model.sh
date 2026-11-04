#!/bin/bash
# Langfuse project agents: the default evaluation model = homelab-gateway / assistant; read it back.
set -uo pipefail
E=~/agentic-ai-homelab/infra/langfuse/.env
U=$(grep '^LANGFUSE_INIT_USER_EMAIL=' $E | cut -d= -f2-); P=$(grep '^LANGFUSE_INIT_USER_PASSWORD=' $E | cut -d= -f2-)
LF=http://127.0.0.1:4000; J=/tmp/lfj.$$
csrf=$(curl -s -c $J $LF/api/auth/csrf | python3 -c 'import json,sys; print(json.load(sys.stdin)["csrfToken"])')
curl -s -b $J -c $J -o /dev/null -X POST $LF/api/auth/callback/credentials --data-urlencode "email=$U" --data-urlencode "password=$P" --data-urlencode "csrfToken=$csrf" --data-urlencode "json=true"
curl -s -b $J -H 'Content-Type: application/json' -X POST "$LF/api/trpc/defaultLlmModel.upsertDefaultModel?batch=1" \
  -d '{"0":{"json":{"projectId":"agents","provider":"homelab-gateway","adapter":"openai","model":"assistant","modelParams":{"temperature":0,"max_tokens":3000}}}}' | head -c 300; echo
curl -s -b $J "$LF/api/trpc/defaultLlmModel.fetchDefaultModel?batch=1&input=$(python3 -c 'import json,urllib.parse; print(urllib.parse.quote(json.dumps({"0":{"json":{"projectId":"agents"}}})))')" | head -c 300; echo
rm -f $J
