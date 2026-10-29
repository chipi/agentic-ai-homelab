#!/bin/bash
# Off-mini copy of one backup run: every file the run wrote is encrypted with age to the
# operator's public key (offsite.recipients) and uploaded to a private GitHub repo as one
# Release per night, with a manifest of plaintext sha256s. Retention: the newest 7 nightly
# releases plus the newest 4 Sunday releases older than those. On success it pushes
# homelab_backup_offsite_* to VictoriaMetrics (alert: homelab-backup-offsite-stale).
#
# The decryption key exists only with the operator; nothing on the mini can read an upload.
# Restore: gh release download <tag> --repo chipi/homelab-backup; age -d -i <key> f.age > f
#
# Called by dump-observability-dbs.sh (root, launchd) after the local dumps:
#   offsite.sh <backup-dir> <stamp>
# gh runs as OFFSITE_GH_USER (whose gh login holds the repo-scoped token); the encrypted
# files are staged in a directory that user owns, so it never needs to read a plaintext dump.
set -uo pipefail
DIR="$1"; STAMP="$2"
HERE="$(cd "$(dirname "$0")" && pwd)"
PATH=/usr/local/bin:/usr/bin:/bin:$PATH
REPO="${OFFSITE_REPO:-chipi/homelab-backup}"
RECIPIENTS="${OFFSITE_RECIPIENTS_FILE:-$HERE/offsite.recipients}"
PREFIX="${OFFSITE_TAG_PREFIX:-homelab-}"
KEEP_DAILY="${OFFSITE_KEEP_DAILY:-7}"
KEEP_WEEKLY="${OFFSITE_KEEP_WEEKLY:-4}"
GH_USER="${OFFSITE_GH_USER:-markodragoljevic}"
VM="${OFFSITE_VM_URL:-http://localhost:8428/api/v1/import/prometheus}"
TAG="${PREFIX}${STAMP%%-*}"                       # one release per calendar day
if [ "$(id -u)" = 0 ]; then
  GH=(sudo -u "$GH_USER" env HOME="/Users/$GH_USER" PATH="$PATH" gh)
else
  GH=(gh)
fi

files=$(ls -1 "$DIR"/*-"$STAMP".* 2>/dev/null)
[ -n "$files" ] || { echo "OFFSITE FAIL: no files for stamp $STAMP in $DIR"; exit 1; }
grep -q '^age1' "$RECIPIENTS" || { echo "OFFSITE FAIL: no age1 recipient in $RECIPIENTS"; exit 1; }

STAGE=$(mktemp -d /tmp/offsite.XXXXXX)
trap 'rm -rf "$STAGE"' EXIT
[ "$(id -u)" = 0 ] && chown "$GH_USER" "$STAGE"
manifest="$STAGE/manifest-$STAMP.txt"
{ echo "# homelab backup $STAMP — plaintext sha256, plaintext bytes, file (each uploaded as <file>.age)"; } > "$manifest"
n=0; bytes=0
for f in $files; do
  b=$(basename "$f")
  if ! age -R "$RECIPIENTS" -o "$STAGE/$b.age" "$f"; then echo "OFFSITE FAIL: age $b"; exit 1; fi
  sz=$(wc -c < "$f" | tr -d ' ')
  echo "$(shasum -a 256 "$f" | cut -d' ' -f1)  $sz  $b" >> "$manifest"
  n=$((n + 1)); bytes=$((bytes + sz))
done
[ "$(id -u)" = 0 ] && chown -R "$GH_USER" "$STAGE"

if "${GH[@]}" release view "$TAG" --repo "$REPO" >/dev/null 2>&1; then
  "${GH[@]}" release upload "$TAG" "$STAGE"/*.age "$manifest" --repo "$REPO" --clobber || { echo "OFFSITE FAIL: upload to $TAG"; exit 1; }
else
  "${GH[@]}" release create "$TAG" "$STAGE"/*.age "$manifest" --repo "$REPO" \
    --title "homelab backup ${STAMP%%-*}" \
    --notes "Nightly backup of the homelab Mac mini (agentic-ai-homelab infra/backup), age-encrypted to the operator's key. Retention ${KEEP_DAILY} nightly + ${KEEP_WEEKLY} Sunday." \
    || { echo "OFFSITE FAIL: create $TAG"; exit 1; }
fi
up=$("${GH[@]}" release view "$TAG" --repo "$REPO" --json assets --jq '[.assets[].name | select(endswith(".age"))] | length')
echo "OFFSITE OK $TAG: $n file(s), $bytes plaintext bytes, $up .age asset(s) on the release"

# Retention: newest KEEP_DAILY tags, plus the newest KEEP_WEEKLY Sunday tags among the rest.
# (no mapfile: launchd runs this under macOS /bin/bash 3.2)
tags=()
while IFS= read -r t; do tags+=("$t"); done < <("${GH[@]}" release list --repo "$REPO" --limit 200 --json tagName --jq '.[].tagName' | grep "^${PREFIX}[0-9]\{8\}$" | sort -r)
keep=("${tags[@]:0:$KEEP_DAILY}")
w=0
for t in "${tags[@]:$KEEP_DAILY}"; do
  d=${t#"$PREFIX"}
  if [ "$w" -lt "$KEEP_WEEKLY" ] && [ "$(date -j -f %Y%m%d "$d" +%u 2>/dev/null || date -d "$d" +%u)" = 7 ]; then keep+=("$t"); w=$((w + 1)); fi
done
for t in "${tags[@]}"; do
  case " ${keep[*]} " in *" $t "*) ;; *) "${GH[@]}" release delete "$t" --repo "$REPO" --yes --cleanup-tag && echo "OFFSITE pruned $t" ;; esac
done

printf 'homelab_backup_offsite_last_success_timestamp %s\nhomelab_backup_offsite_files %s\nhomelab_backup_offsite_bytes %s\n' \
  "$(date +%s)" "$n" "$bytes" | curl -s -m 10 --data-binary @- "$VM?extra_label=instance=homelab&extra_label=service=db-backup&extra_label=environment=operations" || true
