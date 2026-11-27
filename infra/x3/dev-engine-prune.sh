#!/bin/bash
# Weekly (dev-engine-prune.timer): keeps the X3's dev engine (the local system engine, context `dev`) from
# filling the disk. It held 474 GB on 2026-11-27: 328 GB build cache (253 GB unused 7-30 days), 169 GB images
# (52 old flotilla-worker-bugfix tags alone 22 GB). The rules (operator, 2026-11-27):
#   - build cache unused for 14 days goes (BuildKit records each entry's last use);
#   - an image no container uses goes when it is not among its repository's 2 newest and was built and
#     pulled 14 or more days ago; an untagged one when 14 days old;
#   - containers and volumes are never removed (they can hold data): the report lists the stopped
#     containers and the unused volumes, with sizes, for their owners.
#   dev-engine-prune.sh           prune and report
#   dev-engine-prune.sh --dry-run report what would go, remove nothing
# Report: ~/.local/state/dev-engine-prune/<UTC date>.txt (the last 12 kept), and the journal. A real run
# pushes homelab_maintenance_last_run_timestamp{job="dev-engine-prune"} (as the mini's docker-prune does;
# the alert docker-prune-stale and the Hub read it), docker_prune_reclaimed_bytes and the engine's sizes.
set -uo pipefail
DRY=0; [ "${1:-}" = --dry-run ] && DRY=1
HERE="$(cd "$(dirname "$0")" && pwd)"
VM="${X3_VM_IMPORT:-https://vm.tail6d0ed4.ts.net/api/v1/import/prometheus}"
D="docker --context dev"
DAYS=14 KEEP=2
OUT=~/.local/state/dev-engine-prune; mkdir -p "$OUT"
R="$OUT/$(date -u +%F)$( ((DRY)) && echo -dry-run).txt"
now=$(date +%s)
sizes() { $D system df --format '{{json .}}' | python3 "$HERE/../mini-metrics/engine-df.py" x3 dev; }
total() { awk '/^docker_engine_bytes/ { t += $2 } END { printf "%d", t }'; }
exec > >(tee "$R") 2>&1
echo "dev-engine-prune $(date -u +%FT%TZ)$( ((DRY)) && echo ' (dry run)')"
echo "== before"; $D system df
before=$(sizes | total)

echo "== build cache unused for $DAYS days"
if ((DRY)); then
  # from system df's entries (buildx du's until filter shows entries used hours ago, so it is not a preview)
  $D system df -v --format '{{json .BuildCache}}' \
    | jq -r '.[] | select(.InUse == false or .InUse == "false") | [(.LastUsedAt // .CreatedAt | sub("\\.[0-9]+"; "") | sub(" \\+0000 UTC"; "Z") | sub(" "; "T") | fromdateiso8601), .Size] | @tsv' \
    | awk -v c=$((now - DAYS * 86400)) '$1 < c { n++; v = $2; u = v; gsub(/[0-9.]/, "", u); sub(/[A-Za-z]+$/, "", v)
        t += v * (u == "GB" ? 1 : u == "MB" ? 1e-3 : u == "kB" ? 1e-6 : u == "TB" ? 1e3 : 1e-9) }
        END { printf "  would remove %d entries, %.1f GB (shared entries counted each)\n", n, t }'
else
  $D builder prune -f --filter until=$((DAYS * 24))h | tail -1
fi

echo "== images: not used by a container, beyond each repository's $KEEP newest, $DAYS+ days since built and pulled"
used=$($D ps -a --format '{{.Image}}' | xargs -r $D image inspect -f '{{.Id}}' 2>/dev/null | sort -u)
$D image ls --no-trunc --format '{{.ID}}\t{{.Repository}}\t{{.Tag}}\t{{.CreatedAt}}\t{{.Size}}' \
  | sort -t$'\t' -k2,2 -k4,4r \
  | while IFS=$'\t' read -r id repo tag created size; do
      if grep -qx "$id" <<<"$used"; then continue; fi
      if [ "$repo" = "${prev:-}" ]; then n=$((n + 1)); else n=1; prev=$repo; fi
      [ "$repo" != "<none>" ] && [ "$n" -le "$KEEP" ] && continue
      built=$(date -d "${created% [A-Z]*}" +%s 2>/dev/null || echo "$now")
      pulled=$(date -d "$($D image inspect -f '{{.Metadata.LastTagTime}}' "$id" | cut -d' ' -f1,2)" +%s 2>/dev/null || echo 0)
      last=$(( built > pulled ? built : pulled ))
      [ $(( (now - last) / 86400 )) -ge "$DAYS" ] || continue
      ref="$repo:$tag"; { [ "$repo" = "<none>" ] || [ "$tag" = "<none>" ]; } && ref=$id
      echo "  $size  $ref  ($(( (now - last) / 86400 )) days)"
      ((DRY)) || $D rmi "$ref" >/dev/null 2>&1 || echo "    kept: rmi refused"
    done

echo "== stopped containers (never removed here; their owners decide)"
$D ps -a --filter status=exited --filter status=created --format '  {{.Size}}  {{.Names}}  {{.Image}}  {{.Status}}'
echo "== volumes no container uses (never removed here)"
$D system df -v --format '{{json .Volumes}}' | jq -r '.[] | select(.Links == "0" or .Links == 0) | "\(.Size)\t\(.Name)"' | sort -h -r | head -20 | sed 's/^/  /' 
echo "== after"; $D system df
ls -1t "$OUT"/*.txt 2>/dev/null | tail -n +13 | xargs -r rm -f
((DRY)) && exit 0
after_m=$(sizes); after=$(total <<<"$after_m")
echo "freed $(( (before - after) / 1000000000 )) GB"
# last, so the timestamp marks a run that completed
code=$(printf '%s\ndocker_prune_reclaimed_bytes{box="x3",engine="dev"} %d\nhomelab_maintenance_last_run_timestamp{job="dev-engine-prune",box="x3",engine="dev"} %d\n' \
  "$after_m" "$(( before > after ? before - after : 0 ))" "$(date +%s)" \
  | curl -s -m10 -o /dev/null -w '%{http_code}' --data-binary @- "$VM")
case "$code" in 2??) echo "metrics pushed" ;; *) echo "metrics push to $VM failed: HTTP ${code:-none}" ;; esac
