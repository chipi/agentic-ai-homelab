#!/bin/bash
# The second brain agent on the mini's n8n (RFC-0010 amendment A4): import the model credential (OpenAI-compatible: base URL + key), the Slack
# bridge's HMAC secret and the three MCP bearer credentials from files (stdin, never printed), put the Slack credential's id into the workflow,
# import it INACTIVE.
# Publishing is a separate, explicit step (README "Second brain agent (n8n only)"): this script never publishes.
# Runs on the mini from a copy of this folder. Inputs (environment; the files are mode 600, only their path is given here):
#   SB_MODEL_URL         the endpoint's base URL, e.g. http://litellm:4000/v1                    (required)
#   SB_MODEL_KEY_FILE    the key (a file with one line)                                           (required)
#   SB_LIBRARY_TOKEN_FILE  the library MCP's bearer token                                         (required)
#   SB_BRIDGE_SECRET_FILE  the HMAC secret the Slack bridge signs its calls with (32+ characters)  (required)
#   SB_DOCS_TOKEN_FILE   default ~/flotilla/config/mcp/docs.token    (the case 1 docs server's, same credential as install-mcp.sh)
#   SB_TASKS_TOKEN_FILE  default ~/flotilla/config/mcp/tasks.token
#   SLACK_CRED_NAME      picks the Slack credential by name when there are several
# An existing credential is left as is (to change a URL or a key, edit it in the editor).
set -u
export PATH=/usr/local/bin:$PATH
cd "$(dirname "$0")" || exit 1
q() { docker exec n8n-db psql -U n8n -d n8n -tAc "$1"; }
: "${SB_MODEL_URL:?STOP: set SB_MODEL_URL (the OpenAI-compatible base URL)}"
: "${SB_MODEL_KEY_FILE:?STOP: set SB_MODEL_KEY_FILE}"
: "${SB_LIBRARY_TOKEN_FILE:?STOP: set SB_LIBRARY_TOKEN_FILE}"
: "${SB_BRIDGE_SECRET_FILE:?STOP: set SB_BRIDGE_SECRET_FILE}"
[ "$(tr -d '[:space:]' < "$SB_BRIDGE_SECRET_FILE" 2>/dev/null | wc -c | tr -d ' ')" -ge 32 ] || { echo "STOP: $SB_BRIDGE_SECRET_FILE is missing or holds fewer than 32 characters"; exit 1; }
SB_DOCS_TOKEN_FILE=${SB_DOCS_TOKEN_FILE:-$HOME/flotilla/config/mcp/docs.token}
SB_TASKS_TOKEN_FILE=${SB_TASKS_TOKEN_FILE:-$HOME/flotilla/config/mcp/tasks.token}
case "$SB_MODEL_URL" in http://*|https://*) ;; *) echo "STOP: SB_MODEL_URL is not an http(s) URL"; exit 1;; esac
case "$SB_MODEL_URL" in *[\"\\\ ]*) echo "STOP: SB_MODEL_URL has a quote, backslash or space"; exit 1;; esac
OWNER=$(q "select id from \"user\" where email='operator@homelab.local'")
[ -n "$OWNER" ] || { echo "STOP: no owner"; exit 1; }
if [ -n "${SLACK_CRED_NAME:-}" ]; then
  case "$SLACK_CRED_NAME" in *"'"*) echo "STOP: a quote in SLACK_CRED_NAME"; exit 1;; esac
  SLACK=$(q "select id from credentials_entity where type='slackApi' and name='$SLACK_CRED_NAME'")
else
  SLACK=$(q "select id from credentials_entity where type='slackApi'")
fi
[ -n "$SLACK" ] || { echo "STOP: no Slack API credential: create it in the editor first (README, Case 1 Slack flows)"; exit 1; }
[ "$(printf '%s\n' "$SLACK" | wc -l | tr -d ' ')" = 1 ] || { echo "STOP: more than one Slack API credential: name the right one in SLACK_CRED_NAME. They are:"; q "select name from credentials_entity where type='slackApi'"; exit 1; }
case "$SLACK" in *[!A-Za-z0-9]*) echo "STOP: the credential id has an unexpected character"; exit 1;; esac
echo "Slack credential: $(q "select name from credentials_entity where id='$SLACK'")"
cred() {  # id, name, type, data template (one %s: the secret), secret file, extra printf arg
  local f="$5"
  [ -s "$f" ] || { echo "STOP: $f missing or empty"; exit 1; }
  local n; n=$(tr -d '[:space:]' < "$f" | wc -c | tr -d ' ')
  echo "$2: file mode $(stat -c %a "$f" 2>/dev/null || stat -f %Lp "$f"), $n chars"
  [ "$n" -ge 16 ] || { echo "STOP: $f holds $n characters, want 16 or more"; exit 1; }
  if [ -n "$(q "select 1 from credentials_entity where id='$1'")" ]; then echo "  exists, left as is"; return; fi
  local S; S=$(tr -d '[:space:]' < "$f")
  case "$S" in *[\"\\]*) echo "STOP: $f has a quote or backslash"; exit 1;; esac
  { if [ -n "${6:-}" ]; then printf '[{"id":"%s","name":"%s","type":"%s","data":'"$4"'}]' "$1" "$2" "$3" "$S" "$6"; else printf '[{"id":"%s","name":"%s","type":"%s","data":'"$4"'}]' "$1" "$2" "$3" "$S"; fi; } \
    | docker exec -i n8n sh -c 'umask 077; cat > /tmp/c.json; n8n import:credentials --input=/tmp/c.json --userId='"$OWNER"' > /tmp/c.out 2>&1; s=$?; rm -f /tmp/c.json; grep -iE "success|error" /tmp/c.out; rm -f /tmp/c.out; exit $s' \
    || { echo "STOP: importing $2 failed"; exit 1; }
  unset S
  [ -n "$(q "select 1 from credentials_entity where id='$1'")" ] || { echo "STOP: $2 is not in n8n after the import"; exit 1; }
}
cred sbmodelkey000001 'second brain model (OpenAI-compatible)' openAiApi '{"apiKey":"%s","url":"%s"}' "$SB_MODEL_KEY_FILE" "$SB_MODEL_URL"
cred sbmentionhook0001 'second brain mention hook (HMAC)' crypto '{"hmacSecret":"%s"}' "$SB_BRIDGE_SECRET_FILE"
cred sbasklibtoken0001 'second brain library MCP (bearer)' httpBearerAuth '{"token":"%s"}' "$SB_LIBRARY_TOKEN_FILE"
cred c1mcpdocstoken01 'case 1 docs MCP (bearer)' httpBearerAuth '{"token":"%s"}' "$SB_DOCS_TOKEN_FILE"
cred c1mcptaskstoken1 'case 1 tasks MCP (bearer)' httpBearerAuth '{"token":"%s"}' "$SB_TASKS_TOKEN_FILE"
docker exec n8n sh -c 'ls /tmp/c.json 2>/dev/null' && { echo "STOP: temp credential file left in the container"; exit 1; }
echo "temp credential file: gone"
sed "s/__SLACK_CRED_ID__/$SLACK/g" sb-agent.json \
  | docker exec -i n8n sh -c 'cat > /tmp/w.json; n8n import:workflow --input=/tmp/w.json --userId='"$OWNER"' > /tmp/w.out 2>&1; s=$?; rm -f /tmp/w.json; grep -iE "success|error" /tmp/w.out; rm -f /tmp/w.out; exit $s' \
  || { echo "STOP: importing sb-agent.json failed"; exit 1; }
[ "$(q "select active from workflow_entity where id='sbaskagent00001'")" = f ] || { echo "STOP: the workflow is not in n8n, or is active"; exit 1; }
echo "-- workflow (inactive until you publish it):"; q "select id, name, active from workflow_entity where id='sbaskagent00001'"
echo "-- to start answering (the bridge posts to /webhook/second-brain-mention only when it is published): docker exec n8n n8n publish:workflow --id=sbaskagent00001 (README, Second brain agent)"
