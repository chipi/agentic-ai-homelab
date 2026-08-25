#!/bin/bash
# Weekly docker maintenance on the mini — the durable fix for the disk-low class.
#
# Measured 2026-08-25 (disk hit <10% free): the mini's docker bloat is TRANSIENT
# build byproducts, not data. Of ~64GB in the colima disk: build cache 42GB
# (100% reclaimable), images 61GB (~12GB unused), and the actual DATA (every
# observability-retention + DB volume) only ~4GB. Build cache regrows on every
# image build (caddy reverse-proxy etc.) and never self-clears -> it's the
# recurring culprit. This job clears it weekly and returns the space to the host.
#
# Two-part reclaim (the non-obvious bit): pruning frees blocks INSIDE the colima
# VM's ext4, but the VM disk is a sparse image on the macOS host that only grows —
# so `fstrim` is what actually returns the freed space to the host (without it the
# host free-space number, and the disk-low alert, never move).
set -o pipefail
export PATH=/usr/local/bin:$PATH
LOG=/tmp/docker-prune.log
DK="sudo -u _dockerhost env HOME=/var/_dockerhost PATH=$PATH docker"
CS="sudo -u _dockerhost env HOME=/var/_dockerhost PATH=$PATH colima ssh --"
{
  echo "=== docker-prune $(date -u +%FT%TZ) ==="
  df -h / | tail -1 | awk '{print "host / avail BEFORE:", $4}'
  $DK builder prune -af          # the recurring 40GB+ culprit — pure cache, rebuilds
  $DK image prune -af            # unused images only (running stacks' images untouched)
  $CS sudo fstrim -v / || true   # return freed blocks to the host sparse disk image
  df -h / | tail -1 | awk '{print "host / avail AFTER:", $4}'
} >> "$LOG" 2>&1
