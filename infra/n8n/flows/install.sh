#!/bin/bash
# Case 3 on the mini's n8n (operator's go 2026-11-23): import the HMAC credentials from flotilla's secret files
# (stdin, never printed), the three workflows, the two callback webhooks published. Runs on the mini from a copy of this folder.
set -u
export PATH=/usr/local/bin:$PATH
cd "$(dirname "$0")" || exit 1
q() { docker exec n8n-db psql -U n8n -d n8n -tAc "$1"; }
OWNER=$(q "select id from \"user\" where email='operator@homelab.local'")
[ -n "$OWNER" ] || { echo "STOP: no owner"; exit 1; }
cred() {  # id, name, secret file
  local f="$3"
  [ -f "$f" ] || { echo "STOP: $f missing"; exit 1; }
  echo "$2: file mode $(stat -f %Lp "$f"), $(tr -d '[:space:]' < "$f" | wc -c | tr -d ' ') chars"
  if [ -n "$(q "select 1 from credentials_entity where id='$1'")" ]; then echo "  exists, left as is"; return; fi
  local S; S=$(tr -d '[:space:]' < "$f")
  printf '[{"id":"%s","name":"%s","type":"crypto","data":{"hmacSecret":"%s"}}]' "$1" "$2" "$S" \
    | docker exec -i n8n sh -c 'umask 077; cat > /tmp/c.json; n8n import:credentials --input=/tmp/c.json --userId='"$OWNER"' 2>&1 | grep -iE "success|error"; rm -f /tmp/c.json'
  unset S
}
cred c3meetingsecret1 'flotilla meeting hook (HMAC)' ~/flotilla/config/hooks/meeting.secret
cred c3createtasks001 'flotilla create_tasks callback (HMAC)' ~/flotilla/config/plumbing/create_tasks.secret
cred c3postdecision01 'flotilla post_decisions callback (HMAC)' ~/flotilla/config/plumbing/post_decisions.secret
docker exec n8n sh -c 'ls /tmp/c.json 2>/dev/null && echo "STOP: temp file left" || echo "temp credential file: gone"'
for f in case3-create-tasks.json case3-post-decisions.json case3-meeting.json; do
  docker exec -i n8n sh -c 'cat > /tmp/w.json; n8n import:workflow --input=/tmp/w.json --userId='"$OWNER"' 2>&1 | grep -iE "success|error"; rm -f /tmp/w.json' < "$f"
done
for id in case3createtasks case3postdecisio; do docker exec n8n n8n publish:workflow --id=$id 2>&1 | grep -viE "^$|deprecat|license|migration lock"; done
echo "-- workflows:"; q "select id, name, active from workflow_entity where id like 'case3%' order by id"
echo "-- webhooks registered: $(q "select string_agg(\"webhookPath\" || ' ' || method, ', ') from webhook_entity where \"workflowId\" like 'case3%'")"
