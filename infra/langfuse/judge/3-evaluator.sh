#!/bin/bash
# Langfuse project agents: an LLM-as-a-judge evaluator on the morning briefing (traces tagged hub-briefing):
# Faithfulness v2, context = the trace input (the facts), answer = the trace output (the opening).
set -uo pipefail
E=~/agentic-ai-homelab/infra/langfuse/.env
U=$(grep '^LANGFUSE_INIT_USER_EMAIL=' $E | cut -d= -f2-); P=$(grep '^LANGFUSE_INIT_USER_PASSWORD=' $E | cut -d= -f2-)
LF=http://127.0.0.1:4000; J=/tmp/lfj.$$
csrf=$(curl -s -c $J $LF/api/auth/csrf | python3 -c 'import json,sys; print(json.load(sys.stdin)["csrfToken"])')
curl -s -b $J -c $J -o /dev/null -X POST $LF/api/auth/callback/credentials --data-urlencode "email=$U" --data-urlencode "password=$P" --data-urlencode "csrfToken=$csrf" --data-urlencode "json=true"
BODY='{"0":{"json":{"projectId":"agents","evalTemplateId":"cmal6wart010lynrdtpv6olfv2","scoreName":"briefing-faithfulness","target":"trace",
 "filter":[{"type":"arrayOptions","column":"Tags","operator":"any of","value":["hub-briefing"]}],
 "mapping":[{"templateVariable":"context","langfuseObject":"trace","selectedColumnId":"input","jsonSelector":null,"objectName":null},
            {"templateVariable":"answer","langfuseObject":"trace","selectedColumnId":"output","jsonSelector":null,"objectName":null}],
 "sampling":1,"delay":30000,"timeScope":["NEW"],"status":"ACTIVE"}}}'
curl -s -b $J -H 'Content-Type: application/json' -X POST "$LF/api/trpc/evals.createJob?batch=1" -d "$BODY" | head -c 500; echo
rm -f $J
