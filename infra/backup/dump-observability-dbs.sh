#!/bin/bash
# Nightly pg_dump of the homelab observability CONFIG databases so a volume
# reprovision (the 2026-08-14 OrbStack->colima cutover wiped these) is a restore,
# not permanent loss. Dumps GlitchTip (projects/DSN keys), Umami (websites/IDs),
# and Langfuse (projects/keys) postgres. Keeps the last N daily dumps.
#
# Runs on the mini as a KeepAlive/StartCalendarInterval LaunchDaemon
# (com.homelab.db-backup). Manual run: bash dump-observability-dbs.sh
set -uo pipefail

BACKUP_DIR="${DB_BACKUP_DIR:-/Users/markodragoljevic/db-backups}"
KEEP="${DB_BACKUP_KEEP:-14}"
PATH=/usr/local/bin:/usr/bin:/bin:$PATH
D="sudo -u _dockerhost env PATH=$PATH HOME=/var/_dockerhost docker"
STAMP=$(date +%Y%m%d-%H%M%S)
mkdir -p "$BACKUP_DIR"

# container : pg-user : db
DBS="glitchtip-postgres-1:glitchtip:glitchtip umami-db:umami:umami langfuse-postgres-1:postgres:postgres litellm-postgres:litellm:litellm"

rc=0
for spec in $DBS; do
  c="${spec%%:*}"; rest="${spec#*:}"; u="${rest%%:*}"; db="${rest##*:}"
  out="$BACKUP_DIR/${c}-${STAMP}.sql.gz"
  if $D ps --format '{{.Names}}' | grep -qx "$c"; then
    if $D exec "$c" pg_dump -U "$u" "$db" 2>/dev/null | gzip > "$out"; then
      sz=$(stat -f%z "$out" 2>/dev/null || echo 0)
      if [ "$sz" -gt 200 ]; then echo "OK   $c -> $out ($sz bytes)"; else echo "FAIL $c -> dump too small ($sz)"; rm -f "$out"; rc=1; fi
    else echo "FAIL $c -> pg_dump errored"; rm -f "$out"; rc=1; fi
  else echo "SKIP $c -> not running"; fi
done

# rotation: keep the last $KEEP dumps per container
for c in glitchtip-postgres-1 umami-db langfuse-postgres-1 litellm-postgres; do
  ls -1t "$BACKUP_DIR/${c}-"*.sql.gz 2>/dev/null | tail -n +$((KEEP+1)) | while read -r f; do rm -f "$f"; done
done
echo "backup run $STAMP done (rc=$rc); dir=$BACKUP_DIR"
exit $rc
