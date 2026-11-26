#!/usr/bin/env bash
# shellcheck disable=SC2034,SC2016  # the check strings are eval'd later, where rc and T expand
# Test infra/backup/dump-observability-dbs.sh against a fake docker in a sandbox, offsite off.
# Cases: docker unreachable is a failure, not "not running" (2026-11-21: every container read as
# SKIP, nothing was dumped, and only the offsite step failed); docker reachable with nothing running
# skips; a running container is dumped.
# Run: bash infra/backup/test_dump_observability_dbs.sh infra/backup/dump-observability-dbs.sh
set -u
SCRIPT="$(cd "$(dirname "$1")" && pwd)/$(basename "$1")"
T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
fails=0
check() { if eval "$2"; then echo "ok   $1"; else echo "FAIL $1"; fails=$((fails+1)); fi; }
mkdir -p "$T/bin"
# FAKE_DOCKER=denied: every call fails as the 11-21 night did. Otherwise `ps` lists $FAKE_RUNNING
# and `exec` prints a payload larger than the size checks.
cat > "$T/bin/docker" <<'EOF'
#!/usr/bin/env bash
if [ "${FAKE_DOCKER:-}" = denied ]; then
  echo "permission denied while trying to connect to the docker API at unix:///var/run/docker.sock" >&2
  exit 1
fi
case "$1" in
  ps) for n in ${FAKE_RUNNING:-}; do echo "$n"; done ;;
  exec) head -c 4096 /dev/urandom ;;
  *) exit 1 ;;
esac
EOF
chmod 755 "$T/bin/docker"
run() {
  rm -rf "$T/dumps"
  env DB_BACKUP_DOCKER="$T/bin/docker" DB_BACKUP_DIR="$T/dumps" DB_BACKUP_OFFSITE=0 "$@" \
    bash "$SCRIPT" > "$T/out" 2>&1
  echo $?
}

# 1. docker unreachable: a failure, named as such
rc=$(run FAKE_DOCKER=denied)
check "unreachable: exit non-zero" '[ "$rc" != 0 ]'
check "unreachable: says docker is unreachable" 'grep -q "^FAIL docker unreachable" "$T/out"'
check "unreachable: no container reads as not running" '! grep -q "not running" "$T/out"'

# 2. docker reachable, nothing running: skips, exit 0
rc=$(run FAKE_RUNNING=)
check "none running: exit 0" '[ "$rc" = 0 ]'
check "none running: mosquitto skipped" 'grep -q "^SKIP mosquitto -> not running" "$T/out"'

# 3. a running container is dumped
rc=$(run FAKE_RUNNING=mosquitto)
check "mosquitto running: exit 0" '[ "$rc" = 0 ]'
check "mosquitto running: OK line" 'grep -q "^OK   mosquitto -> " "$T/out"'
check "mosquitto running: archive written" 'ls "$T/dumps"/mosquitto-*.tar.gz >/dev/null 2>&1'

if [ "$fails" = 0 ]; then echo "PASS"; else echo "FAIL ($fails)"; cat "$T/out"; fi
exit $(( fails > 0 ))
