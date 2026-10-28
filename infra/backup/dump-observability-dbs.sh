#!/bin/bash
# Nightly pg_dump of the homelab observability CONFIG databases so a volume
# reprovision (the 2026-08-14 OrbStack->colima cutover wiped these) is a restore,
# not permanent loss. Dumps GlitchTip (projects/DSN keys), Umami (websites/IDs),
# and Langfuse (projects/keys) postgres, plus Home Assistant's /config. Keeps the last
# N daily dumps.
#
# Runs on the mini as a KeepAlive/StartCalendarInterval LaunchDaemon
# (com.homelab.db-backup). Manual run: bash dump-observability-dbs.sh
set -uo pipefail

BACKUP_DIR="${DB_BACKUP_DIR:-/Users/markodragoljevic/db-backups}"
KEEP="${DB_BACKUP_KEEP:-14}"
PATH=/usr/local/bin:/usr/bin:/bin:$PATH
D="${DB_BACKUP_DOCKER:-sudo -u _dockerhost env PATH=$PATH HOME=/var/_dockerhost docker}"
STAMP=$(date +%Y%m%d-%H%M%S)
# The dumps and HA's .storage hold credentials: owner-only, never world-readable (the mini
# has other accounts, e.g. other agents' `claude`).
umask 077
mkdir -p "$BACKUP_DIR"
chmod 700 "$BACKUP_DIR"

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

# Home Assistant (chipi/home-automation): its /config as one tar.gz. The recorder DB is
# copied with SQLite's online-backup API (a plain file copy of a live WAL database can be
# torn); the live DB, its -wal/-shm, logs and HA's own backups/ are left out.
HA=home-assistant
HA_PY='
import os, sqlite3, sys, tarfile
db, snap = "/config/home-assistant_v2.db", "/tmp/ha-backup-snapshot.db"
out = tarfile.open(fileobj=sys.stdout.buffer, mode="w|gz")
for root, dirs, files in os.walk("/config"):
    dirs[:] = [d for d in dirs if not (root == "/config" and d in ("backups", "tts"))]
    for f in files:
        if f.startswith("home-assistant_v2.db") or ".log" in f:
            continue
        p = os.path.join(root, f)
        out.add(p, arcname="config" + p[len("/config"):], recursive=False)
if os.path.exists(db):
    src, dst = sqlite3.connect(db), sqlite3.connect(snap)
    src.backup(dst)
    dst.close(); src.close()
    out.add(snap, arcname="config/home-assistant_v2.db")
    os.remove(snap)
out.close()
'
out="$BACKUP_DIR/${HA}-${STAMP}.tar.gz"
if $D ps --format '{{.Names}}' | grep -qx "$HA"; then
  if $D exec -i "$HA" python3 -c "$HA_PY" > "$out" 2>/dev/null; then
    sz=$(wc -c < "$out" | tr -d ' ')
    if [ "$sz" -gt 200 ]; then echo "OK   $HA -> $out ($sz bytes)"; else echo "FAIL $HA -> archive too small ($sz)"; rm -f "$out"; rc=1; fi
  else echo "FAIL $HA -> archive errored"; rm -f "$out"; rc=1; fi
else echo "SKIP $HA -> not running"; fi

# Mosquitto (chipi/home-automation): /mosquitto/data (mosquitto.db, which the broker
# replaces atomically on autosave) and /mosquitto/config (passwd: hashed users).
MQ=mosquitto
out="$BACKUP_DIR/${MQ}-${STAMP}.tar.gz"
if $D ps --format '{{.Names}}' | grep -qx "$MQ"; then
  if $D exec "$MQ" tar -czf - -C /mosquitto data config > "$out" 2>/dev/null; then
    sz=$(wc -c < "$out" | tr -d ' ')
    if [ "$sz" -gt 100 ]; then echo "OK   $MQ -> $out ($sz bytes)"; else echo "FAIL $MQ -> archive too small ($sz)"; rm -f "$out"; rc=1; fi
  else echo "FAIL $MQ -> archive errored"; rm -f "$out"; rc=1; fi
else echo "SKIP $MQ -> not running"; fi

# rotation: keep the last $KEEP dumps per container
for c in "$HA" "$MQ"; do
  ls -1t "$BACKUP_DIR/${c}-"*.tar.gz 2>/dev/null | tail -n +$((KEEP+1)) | while read -r f; do rm -f "$f"; done
done
for c in glitchtip-postgres-1 umami-db langfuse-postgres-1 litellm-postgres; do
  ls -1t "$BACKUP_DIR/${c}-"*.sql.gz 2>/dev/null | tail -n +$((KEEP+1)) | while read -r f; do rm -f "$f"; done
done
echo "backup run $STAMP done (rc=$rc); dir=$BACKUP_DIR"
exit $rc
