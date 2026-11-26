#!/bin/bash
# THROWAWAY proof of the second brain agent on a DEV engine, never the mini: n8n at the production pin (host network, listening on 127.0.0.1:
# the X3's Ollama listens on the tailnet address only, which a bridge container cannot reach), its own Postgres, second-brain's real read server
# (`docker build --target serve` of its checkout, over an index built from its own test fixtures), a stub of docs and tasks MCP, a stub of
# Slack (Web API and Socket Mode), and the real bridge (sb-bridge/bridge.js, run in n8n's image). The workflow is generated against them (gen_sb_agent.js, with the proof seam), installed by install-sb-agent.sh as on the
# mini, driven by proof.py. Every credential, token and key is generated per run. Tears its compose project, volumes and temp dir down at
# the end (KEEP=1 leaves it up). The model is the X3's Ollama (SB_MODEL_URL, SB_MODEL), the one model it keeps loaded.
#   [SB_CHECKOUT=/work/second-brain/main] bash run.sh
set -u
D="docker --context ${DEV_CONTEXT:-dev}"
HERE="$(cd "$(dirname "$0")" && pwd)"; FLOWS="$(dirname "$HERE")"
SB_CHECKOUT="${SB_CHECKOUT:-/work/second-brain/main}"
export SB_MODEL_URL="${SB_MODEL_URL:-http://100.92.54.65:11435/v1}" SB_MODEL="${SB_MODEL:-qwen3:30b-a3b-instruct-2507-q4_K_M}"
[ -x "$SB_CHECKOUT/bin/sb" ] && [ -f "$SB_CHECKOUT/Dockerfile" ] || { echo "STOP: no second-brain checkout at $SB_CHECKOUT"; exit 1; }
$D info >/dev/null 2>&1 || { echo "STOP: no dev engine ($D info failed)"; exit 1; }
SOCK="$($D context inspect "${DEV_CONTEXT:-dev}" --format '{{.Endpoints.docker.Host}}')"
case "$SOCK" in unix://*) ;; *) echo "STOP: the dev context is not a local socket ($SOCK)"; exit 1;; esac
$D ps -a --format '{{.Names}}' | grep -qxE 'n8n|n8n-db|n8n-proof-slack|n8n-proof-library|n8n-proof-docs|n8n-proof-tasks|n8n-proof-bridge|n8n-proof-bridge2|n8n-proof-bridge3' && { echo "STOP: a container of this proof (n8n, n8n-db, n8n-proof-*) already exists on this engine"; exit 1; }
curl -fsS -m 10 "${SB_MODEL_URL%/v1}/api/ps" | grep -q "$SB_MODEL" || echo "NOTE: $SB_MODEL is not listed as loaded at $SB_MODEL_URL (the first answer will wait for it to load)"
W="$(mktemp -d)"; chmod 755 "$W"; export PROOF_HOME="$W/home"; mkdir -p "$PROOF_HOME" "$W/flows" "$W/sb"
cleanup() { $D rm -f n8n-proof-bridge2 n8n-proof-bridge3 >/dev/null 2>&1; [ "${KEEP:-0}" = 1 ] && { echo "KEEP=1: project n8nsbagentproof left up, $W kept"; return; }; $C --profile bridge down -v --remove-orphans >/dev/null 2>&1; rm -rf "$W"; echo "torn down: project n8nsbagentproof and its volumes, $W"; }
export PROOF_PORT="${PROOF_PORT:-15680}" PROOF_BROKER_PORT=15690 DB_PORT="${DB_PORT:-15432}" SLACK_STUB_PORT="${SLACK_STUB_PORT:-18081}" SLACK_WS_PORT="${SLACK_WS_PORT:-18084}" BRIDGE_PORT="${BRIDGE_PORT:-18085}" LIB_PORT="${LIB_PORT:-18790}" DOCS_PORT="${DOCS_PORT:-18082}" TASKS_PORT="${TASKS_PORT:-18083}"
export PROOF_DB_PASSWORD="$(openssl rand -hex 16)" PROOF_ENCRYPTION_KEY="$(openssl rand -hex 24)" PROOF_SLACK_TOKEN="$(openssl rand -hex 24)" PROOF_APP_TOKEN="xapp-proof-$(openssl rand -hex 16)" PROOF_BRIDGE_SECRET="$(openssl rand -hex 32)"
export PROOF_DOCS_TOKEN="$(openssl rand -hex 24)" PROOF_TASKS_TOKEN="$(openssl rand -hex 24)" PROOF_LIB_TOKEN="$(openssl rand -hex 24)" PROOF_MODEL_KEY="$(openssl rand -hex 24)"
C="$D compose -p n8nsbagentproof -f $HERE/docker-compose.yml"
trap cleanup EXIT
# second-brain's real server image, and an index built from its own fixtures (seed, then build), as its README does
$D build --target serve -t sb-proof:serve "$SB_CHECKOUT" >/dev/null 2>&1 || { $D build --target serve -t sb-proof:serve "$SB_CHECKOUT" | tail -5; echo "STOP: second-brain image build failed"; exit 1; }
cp -r "$SB_CHECKOUT/tests/fixtures/content" "$W/sb/content"; cp -r "$SB_CHECKOUT/tests/fixtures/data" "$W/sb/data"
G="git -C $W/sb/content -c user.email=proof@example.test -c user.name=proof"
git -C "$W/sb/content" init -q && $G add -A && $G commit -qm fixtures
"$SB_CHECKOUT/bin/sb" seed --content "$W/sb/content" >/dev/null && $G add -A && $G commit -qm papers
"$SB_CHECKOUT/bin/sb" build --content "$W/sb/content" --data "$W/sb/data" | tail -1 || { echo "STOP: sb build failed"; exit 1; }
chmod -R a+rX "$W/sb/data"
printf '%s' "$PROOF_LIB_TOKEN" > "$W/sb.token"; chmod 644 "$W/sb.token"
export SB_IMAGE=sb-proof:serve SB_DATA="$W/sb/data" SB_TOKEN_FILE="$W/sb.token"
mkdir -p "$W/secrets"; chmod 755 "$W/secrets"; printf "%s" "$PROOF_APP_TOKEN" > "$W/secrets/slack-app.token"; printf "%s" "$PROOF_BRIDGE_SECRET" > "$W/secrets/hook.secret"; chmod 644 "$W/secrets/"*
export PROOF_SECRETS="$W/secrets" SB_BRIDGE_DIR="$(cd "$FLOWS/../sb-bridge" && pwd)"
$C up -d >/dev/null 2>&1 || { $C up -d; echo "STOP: compose up failed"; exit 1; }
for i in $(seq 1 60); do $D exec n8n wget -qO- http://127.0.0.1:$PROOF_PORT/healthz >/dev/null 2>&1 && break; sleep 3; done
$D exec n8n wget -qO- http://127.0.0.1:$PROOF_PORT/healthz >/dev/null 2>&1 || { echo "STOP: n8n not healthy"; exit 1; }
for i in $(seq 1 60); do $D exec n8n-db psql -U n8n -d n8n -tAc 'select count(*) from "user"' >/dev/null 2>&1 && break; sleep 3; done
sleep 5
export DOCKER_HOST="$SOCK"; unset DOCKER_CONTEXT
sed "s/5678/$PROOF_PORT/g" "$FLOWS/../owner-setup.sh" > "$W/owner-setup.sh"
HOME="$PROOF_HOME" bash "$W/owner-setup.sh" | tail -2
$D exec n8n-db psql -U n8n -d n8n -tAc "update \"user\" set email='operator@homelab.local' where \"roleSlug\"='global:owner'" >/dev/null
OWNER=$($D exec n8n-db psql -U n8n -d n8n -tAc "select id from \"user\" where email='operator@homelab.local'")
printf '[{"id":"proofslack000001","name":"Slack (proof)","type":"slackApi","data":{"accessToken":"%s"}}]' "$PROOF_SLACK_TOKEN" \
  | $D exec -i n8n sh -c 'cat > /tmp/g.json; n8n import:credentials --input=/tmp/g.json --userId='"$OWNER"' 2>&1 | grep -iE "success|error"; rm -f /tmp/g.json'
( umask 077; printf '%s' "$PROOF_LIB_TOKEN" > "$W/lib.token"; printf '%s' "$PROOF_DOCS_TOKEN" > "$W/docs.token"; printf '%s' "$PROOF_TASKS_TOKEN" > "$W/tasks.token"; printf '%s' "$PROOF_MODEL_KEY" > "$W/model.key" )


cp "$FLOWS/install-sb-agent.sh" "$W/flows/"
node "$FLOWS/gen_sb_agent.js" "$W/flows" --proof-seam --model "$SB_MODEL" --slack-base "http://127.0.0.1:$SLACK_STUB_PORT" \
  --library-url "http://127.0.0.1:$LIB_PORT/mcp" --docs-url "http://127.0.0.1:$DOCS_PORT/mcp" --tasks-url "http://127.0.0.1:$TASKS_PORT/mcp"
SB_ALLOWED_USERS=U0PROOFUSR1 SB_ALLOWED_CHANNELS=C0PROOFASK1 SB_BRIDGE_SECRET_FILE="$W/secrets/hook.secret" SB_MODEL_KEY_FILE="$W/model.key" SB_LIBRARY_TOKEN_FILE="$W/lib.token" SB_DOCS_TOKEN_FILE="$W/docs.token" SB_TASKS_TOKEN_FILE="$W/tasks.token" \
  HOME="$PROOF_HOME" bash "$W/flows/install-sb-agent.sh" || { echo "STOP: install failed"; exit 1; }
# the publish step the README documents (the installer never does it); n8n registers a production webhook at start
$D exec n8n n8n publish:workflow --id=sbaskagent00001 2>&1 | grep -viE "^$|deprecat|license|migration lock|postgres"
$D restart n8n >/dev/null; for i in $(seq 1 60); do $D exec n8n wget -qO- http://127.0.0.1:$PROOF_PORT/healthz >/dev/null 2>&1 && break; sleep 2; done; sleep 8
$C --profile bridge up -d bridge >/dev/null 2>&1 || { echo "STOP: the bridge did not start"; exit 1; }
for i in $(seq 1 30); do curl -fsS -m 2 "http://127.0.0.1:$BRIDGE_PORT/healthz" >/dev/null 2>&1 && break; sleep 1; done
curl -fsS -m 2 "http://127.0.0.1:$BRIDGE_PORT/healthz" >/dev/null || { echo "STOP: the bridge is not healthy (no Socket Mode hello)"; exit 1; }
export SB_MODEL_KEY_FILE="$W/model.key" SB_LIBRARY_TOKEN_FILE="$W/lib.token" SB_DOCS_TOKEN_FILE="$W/docs.token" SB_TASKS_TOKEN_FILE="$W/tasks.token" SB_BRIDGE_SECRET_FILE="$W/secrets/hook.secret" PROOF_FLOWS="$W/flows" PROOF_HOME PROOF_PORT
export N8N_URL="http://127.0.0.1:$PROOF_PORT" BRIDGE_URL="http://127.0.0.1:$BRIDGE_PORT" WS_URL="http://127.0.0.1:$SLACK_WS_PORT" PROOF_APP_TOKEN PROOF_BRIDGE_SECRET
export DEV_CONTEXT="${DEV_CONTEXT:-dev}" SLACK_URL="http://127.0.0.1:$SLACK_STUB_PORT" LIB_URL="http://127.0.0.1:$LIB_PORT" DOCS_URL="http://127.0.0.1:$DOCS_PORT" TASKS_URL="http://127.0.0.1:$TASKS_PORT"
if [ "${PROOF:-1}" = 0 ]; then echo "PROOF=0: environment up, proof not run"; trap - EXIT; echo "W=$W"; exit 0; fi
python3 "$HERE/proof.py"
RC=$?; echo "EXIT=$RC"; exit $RC
