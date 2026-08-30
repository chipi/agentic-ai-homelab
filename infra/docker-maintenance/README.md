# docker-maintenance — weekly disk reclaim on the mini

The durable fix for the disk-low class (mini `/` hit `<10%` free, 2026-08-25).

## Why (what actually eats the disk)

Measured when the alert fired — of the ~64 GB in the colima docker disk:

| what | size | reclaimable |
|---|---|---|
| **build cache** | 42 GB | **100%** — regrows on every image build, never self-clears |
| images | 61 GB | ~12 GB unused |
| **actual DATA** (every obs-retention + DB volume) | **~4 GB** | ~0 |
| containers | 0.1 GB | ~0 |

**Your data is tiny.** The bloat is transient *build byproducts*. So the fix isn't
deleting data or containers — it's clearing build cache + unused images on a
schedule.

## The non-obvious parts — `fstrim`, and WHICH disk

Pruning frees blocks *inside* the colima VM's ext4, but the VM disks are **sparse
images on the macOS host that only grow**. Without `fstrim` the freed space never
returns to the host — the host free-space number (and the disk-low alert) don't
move. So the job prunes **and** `fstrim`s.

And it must trim **all mounts** (`fstrim -av`): docker data lives on the separate
lima data disk (`/mnt/lima-colima`, backed by `_disks/colima/datadisk`, 98G), not
the 20G boot disk. The original `fstrim /` trimmed only the boot disk — the
datadisk reached 83G allocated for 19G used before the 2026-08-30 manual trim
(reclaimed 60G) caught it.

## Install

```sh
cp com.homelab.docker-prune.plist ~/Library/LaunchAgents/
launchctl load -w ~/Library/LaunchAgents/com.homelab.docker-prune.plist
# run once now to verify:
launchctl start com.homelab.docker-prune && sleep 30 && tail /tmp/docker-prune.log
```

Runs weekly (Sunday 04:00). Script runs in-place from the checkout; log at
`/tmp/docker-prune.log`. **Installed + verified on the mini 2026-08-30** — it had
been written 2026-08-25 but never installed, ran zero times, and the disk grew
unnoticed; hence the dead-man below.

## Dead-man watch

Every completed run pushes `homelab_maintenance_last_run_timestamp{job="docker-prune"}`
to VictoriaMetrics; Grafana rule `docker-prune-stale` (backend alerting rules)
pages at >8 days without a run — or if the series is absent entirely — so a
silently-unloaded job can't recur.

## Not covered here (found in the same audit — operator's call)

Beyond docker, the `/Users` audit surfaced reclaimable space these jobs do NOT
touch (they're outside docker / personal):

- **`/Users/claude/Library/Developer` — 37 GB** (Xcode DerivedData/simulators from
  the workbench user) + `Logs` 5.5 GB + `Caches` 2.1 GB → ~45 GB reclaimable.
- **`/Users/claude/projects` — 24 GB** of repo checkouts (orrery 13 GB, podcast_scraper
  7 GB…) — the agent's working copies, reclaimable if stale.
- **`/Users/markodragoljevic/.colima` — 13 GB** — a **stale/broken** personal colima
  instance (`colima status` → "lima not found"); the homelab runs under `_dockerhost`,
  so this one is dead weight.
- `/Users/markodragoljevic/Pictures` — 72 GB personal photos (not homelab).

## Related
- Systems index: [`infra/README.md`](../README.md)
- The disk-low alert: `infra-disk-low` in the backend alerting rules.
