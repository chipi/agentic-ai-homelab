#!/usr/bin/env bash
# verify_units.sh — check systemd unit files on the host they are for, without installing them.
#
#   verify_units.sh [-i KEY] USER@HOST UNIT_FILE [UNIT_FILE ...]
#
# Copies the files to a private temp dir on the host, runs `systemd-analyze verify` on them there
# (the host's systemd version, its existing units and drop-ins), prints each timer's next run, and
# removes the copies. Read-only for the host's systemd: nothing is installed, enabled or reloaded.
# The host's own drop-ins are loaded too, so their warnings show up as well. On 2026-10-17 this
# surfaced Caddy's unquoted CADDY_BIND_ADDRS while checking an unrelated timer; read every line.
#
# Exit: systemd-analyze's exit code (non-zero = a unit has an error).
set -euo pipefail
KEY=()
if [ "${1:-}" = "-i" ]; then KEY=(-i "$2" -o IdentitiesOnly=yes); shift 2; fi
HOST="${1:?USER@HOST}"; shift
[ $# -gt 0 ] || { echo "usage: $0 [-i KEY] USER@HOST UNIT_FILE..." >&2; exit 4; }
D=$(ssh -o BatchMode=yes "${KEY[@]}" "$HOST" 'mktemp -d /tmp/verify-units.XXXXXX')
trap 'ssh -o BatchMode=yes "${KEY[@]}" "$HOST" "rm -rf $D"' EXIT
scp -q "${KEY[@]}" "$@" "$HOST:$D/"
names=()
for f in "$@"; do names+=("./$(basename "$f")"); done
set +e
ssh -o BatchMode=yes "${KEY[@]}" "$HOST" "cd $D && systemd-analyze verify ${names[*]}; rc=\$?; \
  for t in ${names[*]}; do case \$t in *.timer) c=\$(sed -n 's/^OnCalendar=//p' \$t | head -1); \
  [ -n \"\$c\" ] && echo \"\$t next: \$(systemd-analyze calendar \"\$c\" | sed -n 's/.*Next elapse: //p')\";; esac; done; exit \$rc"
rc=$?
echo "VERIFY_EXIT=$rc"
exit $rc
