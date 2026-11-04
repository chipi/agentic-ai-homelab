#!/bin/bash
# Langfuse (project agents): an LLM connection to the homelab gateway with the langfuse-judge key, for the
# Playground and LLM-as-a-judge evaluators; read it back (the key is never printed).
set -uo pipefail
set -a; . ~/signal-fleet/fleet-gateway.env; set +a
LF=http://127.0.0.1:4000; A="$LANGFUSE_PUBLIC_KEY:$LANGFUSE_SECRET_KEY"
K=$(grep '^LITELLM_API_KEY=' ~/langfuse-judge-litellm.env | cut -d= -f2-)
body=$(python3 -c 'import json,sys; print(json.dumps({"provider":"homelab-gateway","adapter":"openai","secretKey":sys.argv[1],"baseURL":"http://host.docker.internal:4001/v1","customModels":["assistant"],"withDefaultModels":False}))' "$K")
unset K
curl -s -m 20 -o /tmp/lfc.$$ -w 'PUT llm-connections: HTTP %{http_code}\n' -X PUT -u "$A" -H 'Content-Type: application/json' $LF/api/public/llm-connections -d "$body"
head -c 600 /tmp/lfc.$$; echo
rm -f /tmp/lfc.$$
curl -s -m 20 -u "$A" $LF/api/public/llm-connections | python3 -c 'import json,sys; print("connections:", [(c["provider"], c["adapter"], c.get("baseURL"), c.get("customModels")) for c in json.load(sys.stdin)["data"]])'
