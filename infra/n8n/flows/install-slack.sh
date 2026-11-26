#!/bin/bash
# Case 1 Slack flows on the mini's n8n (RFC-0010 amendment A3): import the two HMAC credentials from flotilla's secret files (stdin,
# never printed), put the Slack credential's id into the two workflows, import both, publish the REPLY flow. The question flow
# (case1slackask001) is imported inactive: it starts polling #ask only when the operator publishes it (README, "Case 1 Slack flows").
# Runs on the mini from a copy of this folder. The Slack credential is the operator's, made in the editor (README): this script only
# looks its id up, by type, and stops if it is not exactly one.
set -u
export PATH=/usr/local/bin:$PATH
cd "$(dirname "$0")" || exit 1
q() { docker exec n8n-db psql -U n8n -d n8n -tAc "$1"; }
OWNER=$(q "select id from \"user\" where email='operator@homelab.local'")
[ -n "$OWNER" ] || { echo "STOP: no owner"; exit 1; }
# The Slack credential is the one of type Slack API, whatever the editor named it; SLACK_CRED_NAME picks one by name when there are several.
if [ -n "${SLACK_CRED_NAME:-}" ]; then
  case "$SLACK_CRED_NAME" in *"'"*) echo "STOP: a quote in SLACK_CRED_NAME"; exit 1;; esac
  SLACK=$(q "select id from credentials_entity where type='slackApi' and name='$SLACK_CRED_NAME'")
else
  SLACK=$(q "select id from credentials_entity where type='slackApi'")
fi
[ -n "$SLACK" ] || { echo "STOP: no Slack API credential: create it in the editor first (README)"; exit 1; }
[ "$(printf '%s\n' "$SLACK" | wc -l | tr -d ' ')" = 1 ] || { echo "STOP: more than one Slack API credential: name the right one in SLACK_CRED_NAME. They are:"; q "select name from credentials_entity where type='slackApi'"; exit 1; }
case "$SLACK" in *[!A-Za-z0-9]*) echo "STOP: the credential id has an unexpected character"; exit 1;; esac
echo "Slack credential: $(q "select name from credentials_entity where id='$SLACK'")"
cred() {  # id, name, secret file
  local f="$3"
  [ -f "$f" ] || { echo "STOP: $f missing"; exit 1; }
  echo "$2: file mode $(stat -c %a "$f" 2>/dev/null || stat -f %Lp "$f"), $(tr -d '[:space:]' < "$f" | wc -c | tr -d ' ') chars"
  if [ -n "$(q "select 1 from credentials_entity where id='$1'")" ]; then echo "  exists, left as is"; return; fi
  local S; S=$(tr -d '[:space:]' < "$f")
  printf '[{"id":"%s","name":"%s","type":"crypto","data":{"hmacSecret":"%s"}}]' "$1" "$2" "$S" \
    | docker exec -i n8n sh -c 'umask 077; cat > /tmp/c.json; n8n import:credentials --input=/tmp/c.json --userId='"$OWNER"' 2>&1 | grep -iE "success|error"; rm -f /tmp/c.json'
  unset S
}
cred c1slackaskhook01 'flotilla ask hook (HMAC)' ~/flotilla/config/hooks/ask.secret
cred c1slackreplycb01 'flotilla reply callback (HMAC)' ~/flotilla/config/plumbing/reply.secret
docker exec n8n sh -c 'ls /tmp/c.json 2>/dev/null && echo "STOP: temp file left" || echo "temp credential file: gone"'
for f in case1-slack-reply.json case1-slack-ask.json; do
  sed "s/__SLACK_CRED_ID__/$SLACK/g" "$f" \
    | docker exec -i n8n sh -c 'cat > /tmp/w.json; n8n import:workflow --input=/tmp/w.json --userId='"$OWNER"' 2>&1 | grep -iE "success|error"; rm -f /tmp/w.json'
done
docker exec n8n n8n publish:workflow --id=case1slackreply1 2>&1 | grep -viE "^$|deprecat|license|migration lock|postgres"
echo "-- workflows (the question flow stays inactive until you publish it):"; q "select id, name, active from workflow_entity where id like 'case1slack%' order by id"
echo "-- the reply callback URL flotilla's PLUMBING_REPLY_URL takes (as its network sees it): http://n8n:5678/webhook/flotilla-reply"
echo "-- to start the question flow: docker exec n8n n8n publish:workflow --id=case1slackask001, (README)"
