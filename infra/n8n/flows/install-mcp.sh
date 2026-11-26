#!/bin/bash
# Case 1 read servers on the mini's n8n (RFC-0010 amendment A2): import the two bearer-token credentials from flotilla's token
# files (stdin, never printed), put the read-only Google credential's id into the two workflows, import and publish them.
# Runs on the mini from a copy of this folder. The Google credential is the operator's sign-in in the editor (README): this
# script only looks its id up and stops if it is not there.
set -u
export PATH=/usr/local/bin:$PATH
cd "$(dirname "$0")" || exit 1
q() { docker exec n8n-db psql -U n8n -d n8n -tAc "$1"; }
OWNER=$(q "select id from \"user\" where email='operator@homelab.local'")
[ -n "$OWNER" ] || { echo "STOP: no owner"; exit 1; }
# The read-only sign-in is the one credential of the generic type Google OAuth2 API (case 3's are the Drive, Docs and Tasks
# types), whatever the editor named it; GOOGLE_RO_CRED_NAME picks one by name when there are several.
if [ -n "${GOOGLE_RO_CRED_NAME:-}" ]; then
  case "$GOOGLE_RO_CRED_NAME" in *"'"*) echo "STOP: a quote in GOOGLE_RO_CRED_NAME"; exit 1;; esac
  GOOGLE=$(q "select id from credentials_entity where type='googleOAuth2Api' and name='$GOOGLE_RO_CRED_NAME'")
else
  GOOGLE=$(q "select id from credentials_entity where type='googleOAuth2Api'")
fi
[ -n "$GOOGLE" ] || { echo "STOP: no Google OAuth2 API credential: create the read-only one in the editor first (README)"; exit 1; }
[ "$(printf '%s\n' "$GOOGLE" | wc -l | tr -d ' ')" = 1 ] || { echo "STOP: more than one Google OAuth2 API credential: name the read-only one in GOOGLE_RO_CRED_NAME. They are:"; q "select name from credentials_entity where type='googleOAuth2Api'"; exit 1; }
case "$GOOGLE" in *[!A-Za-z0-9]*) echo "STOP: the credential id has an unexpected character"; exit 1;; esac
echo "Google read-only credential: $(q "select name from credentials_entity where id='$GOOGLE'")"
cred() {  # id, name, token file
  local f="$3"
  [ -f "$f" ] || { echo "STOP: $f missing"; exit 1; }
  local n; n=$(tr -d '[:space:]' < "$f" | wc -c | tr -d ' ')
  echo "$2: file mode $(stat -c %a "$f" 2>/dev/null || stat -f %Lp "$f"), $n chars"
  # an empty or short file would become a bearer token anyone can guess
  [ "$n" -ge 32 ] || { echo "STOP: $f holds $n characters, fewer than 32"; exit 1; }
  if [ -n "$(q "select 1 from credentials_entity where id='$1'")" ]; then echo "  exists, left as is"; return; fi
  local S; S=$(tr -d '[:space:]' < "$f")
  printf '[{"id":"%s","name":"%s","type":"httpBearerAuth","data":{"token":"%s"}}]' "$1" "$2" "$S" \
    | docker exec -i n8n sh -c 'umask 077; cat > /tmp/c.json; n8n import:credentials --input=/tmp/c.json --userId='"$OWNER"' 2>&1 | grep -iE "success|error"; rm -f /tmp/c.json'
  unset S
}
cred c1mcpdocstoken01 'case 1 docs MCP (bearer)' ~/flotilla/config/mcp/docs.token
cred c1mcptaskstoken1 'case 1 tasks MCP (bearer)' ~/flotilla/config/mcp/tasks.token
docker exec n8n sh -c 'ls /tmp/c.json 2>/dev/null && echo "STOP: temp file left" || echo "temp credential file: gone"'
for f in case1-mcp-docs.json case1-mcp-tasks.json; do
  sed "s/__GOOGLE_RO_CRED_ID__/$GOOGLE/g" "$f" \
    | docker exec -i n8n sh -c 'cat > /tmp/w.json; n8n import:workflow --input=/tmp/w.json --userId='"$OWNER"' 2>&1 | grep -iE "success|error"; rm -f /tmp/w.json'
done
# the sub-workflows first: a tool node calls them by id, and n8n runs only a published one
for id in case1mcpdsearch01 case1mcpdread00001 case1mcptlist0001 case1mcpdocs0001 case1mcptasks001; do docker exec n8n n8n publish:workflow --id=$id 2>&1 | grep -viE "^$|deprecat|license|migration lock|postgres"; done
echo "-- workflows:"; q "select id, name, active from workflow_entity where id like 'case1mcp%' order by id"
echo "-- the MCP URLs flotilla uses (as flotillad's network sees them): http://n8n:5678/mcp/case1-docs and http://n8n:5678/mcp/case1-tasks"
