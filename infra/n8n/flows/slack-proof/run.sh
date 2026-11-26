#!/bin/bash
# THROWAWAY proof of the case 1 Slack flows on a DEV engine, never the mini: n8n at the production pin, its own Postgres, a stub of Slack's
# Web API and a stub of flotilla's ask hook; the flows generated against the stub (gen_slack_flows.js --base), installed by install-slack.sh as
# on the mini, driven by proof.py with flotilla's own plumbing/call.py. Every credential and secret is generated per run. Tears its own
# compose project and volumes down at the end (KEEP=1 leaves it up).
#   FLOTILLA_PLUMBING=/path/to/flotilla/plumbing bash run.sh
set -u
D="docker --context ${DEV_CONTEXT:-dev}"
HERE="$(cd "$(dirname "$0")" && pwd)"; FLOWS="$(dirname "$HERE")"
export FLOTILLA_PLUMBING="${FLOTILLA_PLUMBING:?set FLOTILLA_PLUMBING to the plumbing directory of the flotilla checkout (call.py)}"
[ -f "$FLOTILLA_PLUMBING/call.py" ] || { echo "STOP: no call.py in $FLOTILLA_PLUMBING"; exit 1; }
$D info >/dev/null 2>&1 || { echo "STOP: no dev engine ($D info failed)"; exit 1; }
SOCK="$($D context inspect "${DEV_CONTEXT:-dev}" --format '{{.Endpoints.docker.Host}}')"
case "$SOCK" in unix://*) ;; *) echo "STOP: the dev context is not a local socket ($SOCK)"; exit 1;; esac
$D ps -a --format '{{.Names}}' | grep -qxE 'n8n|n8n-db|n8n-proof-slack|n8n-proof-hook' && { echo "STOP: a container named n8n, n8n-db, n8n-proof-slack or n8n-proof-hook already exists on this engine"; exit 1; }
W="$(mktemp -d)"; export PROOF_HOME="$W/home"; mkdir -p "$PROOF_HOME/flotilla/config/hooks" "$PROOF_HOME/flotilla/config/plumbing" "$W/flows"
export PROOF_PORT="${PROOF_PORT:-15679}" SLACK_STUB_PORT="${SLACK_STUB_PORT:-18081}" HOOK_STUB_PORT="${HOOK_STUB_PORT:-18488}"
# generated per run, never written down
export PROOF_DB_PASSWORD="$(openssl rand -hex 16)" PROOF_ENCRYPTION_KEY="$(openssl rand -hex 24)"
export PROOF_SLACK_TOKEN="$(openssl rand -hex 24)" PROOF_HOOK_SECRET="$(openssl rand -hex 32)"
C="$D compose -p n8nslackproof -f $HERE/docker-compose.yml"
cleanup() { [ "${KEEP:-0}" = 1 ] && { echo "KEEP=1: project n8nslackproof left up"; return; }; $C down -v --remove-orphans >/dev/null 2>&1; rm -rf "$W"; echo "torn down: project n8nslackproof and its volumes, $W"; }
trap cleanup EXIT
$C up -d >/dev/null 2>&1 || { $C up -d; echo "STOP: compose up failed"; exit 1; }
for i in $(seq 1 60); do $D exec n8n wget -qO- http://127.0.0.1:5678/healthz >/dev/null 2>&1 && break; sleep 3; done
$D exec n8n wget -qO- http://127.0.0.1:5678/healthz >/dev/null 2>&1 || { echo "STOP: n8n not healthy"; exit 1; }
# n8n answers /healthz before its migrations are done: wait for the user table, or the owner setup lands on nothing
for i in $(seq 1 60); do $D exec n8n-db psql -U n8n -d n8n -tAc 'select count(*) from "user"' >/dev/null 2>&1 && break; sleep 3; done
sleep 5
export DOCKER_HOST="$SOCK"; unset DOCKER_CONTEXT
HOME="$PROOF_HOME" bash "$FLOWS/../owner-setup.sh" | tail -2
$D exec n8n-db psql -U n8n -d n8n -tAc "update \"user\" set email='operator@homelab.local' where \"roleSlug\"='global:owner'" >/dev/null
OWNER=$($D exec n8n-db psql -U n8n -d n8n -tAc "select id from \"user\" where email='operator@homelab.local'")
# stand-in for the operator's Slack credential: the same type, any name, a made-up token the stub accepts
printf '[{"id":"proofslack000001","name":"Slack (proof)","type":"slackApi","data":{"accessToken":"%s"}}]' "$PROOF_SLACK_TOKEN" \
  | $D exec -i n8n sh -c 'cat > /tmp/g.json; n8n import:credentials --input=/tmp/g.json --userId='"$OWNER"' 2>&1 | grep -iE "success|error"; rm -f /tmp/g.json'
# the two HMAC secret files as flotilla's config has them (mode 600)
( umask 077; printf '%s' "$PROOF_HOOK_SECRET" > "$PROOF_HOME/flotilla/config/hooks/ask.secret"; openssl rand -hex 32 > "$PROOF_HOME/flotilla/config/plumbing/reply.secret" )
cp "$FLOWS/install-slack.sh" "$W/flows/"
node "$FLOWS/gen_slack_flows.js" "$W/flows" --base http://slack:8080
HOME="$PROOF_HOME" bash "$W/flows/install-slack.sh"
$D restart n8n >/dev/null; for i in $(seq 1 60); do $D exec n8n wget -qO- http://127.0.0.1:5678/healthz >/dev/null 2>&1 && break; sleep 2; done; sleep 8
export DEV_CONTEXT="${DEV_CONTEXT:-dev}" N8N_URL="http://127.0.0.1:$PROOF_PORT" SLACK_URL="http://127.0.0.1:$SLACK_STUB_PORT" HOOK_URL="http://127.0.0.1:$HOOK_STUB_PORT"
export REPLY_SECRET_FILE="$PROOF_HOME/flotilla/config/plumbing/reply.secret"
PYTHONPATH="$FLOTILLA_PLUMBING" python3 "$HERE/proof.py"
RC=$?; echo "EXIT=$RC"; exit $RC
