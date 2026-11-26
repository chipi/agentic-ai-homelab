#!/bin/bash
# THROWAWAY proof of the case 1 MCP read servers on a DEV engine, never the mini: n8n at the production pin, its own Postgres, a stub
# of Google, the flows generated against the stub (gen_mcp_flows.js --base), installed by install-mcp.sh as on the mini, driven by
# flotilla's real McpClient (test_mcp.py). Tears its own compose project and volumes down at the end (KEEP=1 leaves it up).
#   FLOTILLA_RUNTIME=/path/to/flotilla/runtime bash run.sh
set -u
D="docker --context ${DEV_CONTEXT:-dev}"
HERE="$(cd "$(dirname "$0")" && pwd)"; FLOWS="$(dirname "$HERE")"
RUNTIME="${FLOTILLA_RUNTIME:?set FLOTILLA_RUNTIME to the runtime directory of the flotilla checkout (mcp_client.py)}"
$D info >/dev/null 2>&1 || { echo "STOP: no dev engine ($D info failed)"; exit 1; }
SOCK="$($D context inspect "${DEV_CONTEXT:-dev}" --format '{{.Endpoints.docker.Host}}')"
case "$SOCK" in unix://*) ;; *) echo "STOP: the dev context is not a local socket ($SOCK)"; exit 1;; esac
$D ps -a --format '{{.Names}}' | grep -qxE 'n8n|n8n-db|n8n-proof-stub' && { echo "STOP: a container named n8n, n8n-db or n8n-proof-stub already exists on this engine"; exit 1; }
W="$(mktemp -d)"; export PROOF_HOME="$W/home"; mkdir -p "$PROOF_HOME/flotilla/config/mcp" "$W/flows"
export FOLDER="$(sed -n "s/^const FOLDER = '\([^']*\)'.*/\1/p" "$FLOWS/gen_mcp_flows.js")" DOC="$(sed -n "s/^const DOC = '\([^']*\)'.*/\1/p" "$FLOWS/gen_mcp_flows.js")" LIST="$(sed -n "s/^const LIST = '\([^']*\)'.*/\1/p" "$FLOWS/gen_mcp_flows.js")"
export PROOF_PORT="${PROOF_PORT:-15678}" STUB_PORT="${STUB_PORT:-18080}"
# generated per run, never written down: the throwaway stack still gets no fixed credential
export PROOF_DB_PASSWORD="$(openssl rand -hex 16)" PROOF_ENCRYPTION_KEY="$(openssl rand -hex 24)"
C="$D compose -p n8nmcpproof -f $HERE/docker-compose.yml"
cleanup() { [ "${KEEP:-0}" = 1 ] && { echo "KEEP=1: project n8nmcpproof left up"; return; }; $C down -v --remove-orphans >/dev/null 2>&1; rm -rf "$W"; echo "torn down: project n8nmcpproof and its volumes, $W"; }
trap cleanup EXIT
$C up -d >/dev/null 2>&1 || { $C up -d; echo "STOP: compose up failed"; exit 1; }
for i in $(seq 1 60); do $D exec n8n wget -qO- http://127.0.0.1:5678/healthz >/dev/null 2>&1 && break; sleep 3; done
$D exec n8n wget -qO- http://127.0.0.1:5678/healthz >/dev/null 2>&1 || { echo "STOP: n8n not healthy"; exit 1; }
# n8n answers /healthz before its migrations are done: wait for the user table, or the owner setup lands on nothing
for i in $(seq 1 60); do $D exec n8n-db psql -U n8n -d n8n -tAc 'select count(*) from "user"' >/dev/null 2>&1 && break; sleep 3; done
sleep 5
# the install scripts address the engine by name; the proof gives them the dev socket and its own HOME
export DOCKER_HOST="$SOCK"; unset DOCKER_CONTEXT
HOME="$PROOF_HOME" bash "$FLOWS/../owner-setup.sh" | tail -2
# if the owner setup left the row without its email (seen once on a fresh 2.48.7, README "Not covered"), set it as the real row has it
$D exec n8n-db psql -U n8n -d n8n -tAc "update \"user\" set email='operator@homelab.local' where \"roleSlug\"='global:owner'" >/dev/null
OWNER=$($D exec n8n-db psql -U n8n -d n8n -tAc "select id from \"user\" where email='operator@homelab.local'")
# stand-in for the operator's Google sign-in: the same credential type and name, scopes as documented, a made-up token the stub accepts
printf '[{"id":"proofgoogle00001","name":"Google read-only (case 1)","type":"googleOAuth2Api","data":{"clientId":"proof","clientSecret":"proof","scope":"https://www.googleapis.com/auth/drive.readonly https://www.googleapis.com/auth/tasks.readonly","oauthTokenData":{"access_token":"'"$(openssl rand -hex 16)"'","token_type":"Bearer","refresh_token":"proof-refresh"}}}]' \
  | $D exec -i n8n sh -c 'cat > /tmp/g.json; n8n import:credentials --input=/tmp/g.json --userId='"$OWNER"' 2>&1 | grep -iE "success|error"; rm -f /tmp/g.json'
# the bearer tokens: random, in token files like flotilla's config/mcp/*.token (mode 600), never printed
for s in docs tasks; do ( umask 077; head -c 24 /dev/urandom | od -An -tx1 | tr -d ' \n' > "$PROOF_HOME/flotilla/config/mcp/$s.token" ); done
cp "$FLOWS/install-mcp.sh" "$W/flows/"
node "$FLOWS/gen_mcp_flows.js" "$W/flows" --base http://stub:8080
HOME="$PROOF_HOME" bash "$W/flows/install-mcp.sh"
sleep 12
cd "$FLOWS" && PYTHONPATH="$RUNTIME" \
  MCP_DOCS_URL="http://127.0.0.1:$PROOF_PORT/mcp/case1-docs" MCP_DOCS_TOKEN_FILE="$PROOF_HOME/flotilla/config/mcp/docs.token" \
  MCP_TASKS_URL="http://127.0.0.1:$PROOF_PORT/mcp/case1-tasks" MCP_TASKS_TOKEN_FILE="$PROOF_HOME/flotilla/config/mcp/tasks.token" \
  TEST_QUERY=pricing OUTSIDE_ID=outside STUB_LOG_URL="http://127.0.0.1:$STUB_PORT/__log" python3 test_mcp.py
RC=$?; echo "EXIT=$RC"; exit $RC
