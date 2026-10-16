# ADR-0011 — Workstation storage: /work and Docker leave the root rollback domain

**Status:** Accepted (2026-10-16) — the layout is codified; the one-time migration of
the X3 has not been run yet ([runbook](../recipes/x3-storage-separation.md)).
**Date:** 2026-10-16

## Context

The Linux development workstation (the X3, Omarchy on Arch) is one LUKS2 NVMe holding
one Btrfs filesystem. Omarchy lays it out as top-level subvolumes `@` (`/`), `@home`,
`@log`, `@pkg` and `@factory`, plus `@/.snapshots`, `@/swap`, `@/var/lib/portables`
and `@/var/lib/machines` nested inside `@`. Snapper's only config, `root`, snapshots
`@`; Omarchy takes a snapshot before updates, and Limine boots or restores one
(`RESTORE_METHOD=replace`: a new `@` is made from the snapshot, the old one is kept).

Three paths were ordinary directories inside `@` (verified 2026-10-16: same device
as `/`, inode not 256, no nested subvolumes):

- `/work` — every project checkout and stream (Model-B layout), about 22 GiB;
- `/var/lib/containerd` — Docker 29 runs with the containerd image store against the
  system `containerd.service`, so image content, layer snapshots and the BuildKit
  cache data live here, about 25 GiB;
- `/var/lib/docker` — Docker's own metadata, BuildKit records, networks, volumes and
  container logs, under 100 MiB today.

So a root rollback, which exists to undo a bad OS or package update, would also
rewind uncommitted project work and swap Docker's state for an older copy, and every
root snapshot pinned the churn of image layers and build cache.

Docker also has a boot-ordering hazard: Omarchy's `omarchy-settings` package installs
`docker.service.d/no-block-boot.conf` with `DefaultDependencies=no`, which removes the
implicit "after local filesystems" ordering. `docker.socket` is enabled, so any
`docker` command starts the daemon.

## Decision

1. **`@` is the OS rollback domain only.** `/work`, `/var/lib/docker` and
   `/var/lib/containerd` each get their own **top-level** subvolume, a sibling of
   `@`: `@work`, `@docker`, `@containerd` (the installation's `@name` convention).
   Application paths do not change; each subvolume is mounted at the old path.
2. **Snapshots stop at subvolume boundaries.** A Btrfs snapshot is never recursive.
   `@work` is not inside `@` at all, so a root snapshot contains only the empty
   mountpoint directory `/work`, never its contents; the same for the Docker trees.
   This is proven on the machine by the post-migration snapshot check (runbook
   step P), not assumed.
3. **Both Docker trees move together.** Moving only `/var/lib/docker` would leave the
   image store and layers in the root domain and split one consistent state.
4. **Mounts at the existing paths, not a new Docker `data-root`.** Docker, containerd
   and Omarchy keep their defaults; nothing else needs to know.
5. **fstab entries use the root filesystem's UUID and the root entry's options with
   `subvol=/@<name>`, and never `nofail`.** A missing mount must stop the boot rather
   than let Docker or development write into the empty directories inside `@`.
   `wb-storage fstab` renders them from the running machine; no UUID is hard-coded.
6. **Explicit mount dependencies in workstation-owned drop-ins**, next to (never
   instead of) Omarchy's `no-block-boot.conf`:
   `docker.service.d/50-x3-storage-mounts.conf` →
   `RequiresMountsFor=/var/lib/docker /var/lib/containerd`;
   `containerd.service.d/50-x3-storage-mounts.conf` →
   `RequiresMountsFor=/var/lib/containerd`. `RequiresMountsFor` adds both the
   requirement and the ordering, and works with `DefaultDependencies=no`.
7. **Steady state is codified; migration is not automated.** `workstation/storage/`
   holds the drop-ins and `wb-storage` (status, fstab rendering, drop-in install).
   `install.sh` only links `wb-storage` and reports the layout. Nothing creates
   subvolumes, edits fstab, mounts, or moves data automatically. A machine whose
   paths already hold data is migrated once, by hand, with the
   [runbook](../recipes/x3-storage-separation.md); the old copies are retired later by
   a [separate, approved procedure](../recipes/x3-storage-safety-copy-retirement.md).

### What protects what

| Layer | Covers | Does not cover |
|---|---|---|
| Git + GitHub (+ LFS) | source durability for `/work` | uncommitted work, ignored local files |
| Snapper root snapshots | bad OS or package update, on the same disk | disk loss, theft, `/work`, Docker, `@home` |
| `agentic-ai-homelab` | rebuilding the workstation config | data |
| Encrypted off-machine backup (small) | unique local secrets and state (project `.env` files, local overrides) | anything reproducible |

Snapper is rollback, not backup: its snapshots live on the same disk inside the same
LUKS volume.

## Consequences

**Positive.** An OS rollback no longer touches project work or Docker state. Root
snapshots no longer pin image and build-cache churn. `@work`, `@docker` and
`@containerd` can later move to a second encrypted NVMe by changing only their fstab
lines (subvolume-level `btrfs send`/`receive` or a copy), with no application path
change.

**Negative.** `/work` has no local rollback at all; Git is its only history, which
is the intended owner. Three more fstab lines that can stop a boot if wrong (checked
with `findmnt --verify` and a live mount before the first reboot).

**Legacy-snapshot caveat.** The X3's existing snapshots 1 and 2 (2026-09-30) and
`@factory` predate the new layout. They even predate `/work` and the Docker data, so
restoring one already brings back a root without them. After the migration,
restoring one of them leaves `@work`, `@docker` and `@containerd` intact as siblings,
but the restored root's `/etc/fstab` does not mount them: `/work` and Docker appear
missing until the three entries (and the empty mountpoints) are added back. The data
is not destroyed. The post-migration root snapshot (runbook step P) is the first
known-good rollback point whose fstab understands the new layout.

**Neutral.** Btrfs mount options such as `compress`, `ssd` and `space_cache` apply to
the whole filesystem; only `subvol=` differs per mount, so the new entries copy the
root entry's options. Per-subvolume tuning, if ever needed, is `btrfs property` or
`chattr`, not mount options.

## Alternatives considered

- **Change Docker's `data-root`.** Rejected: containerd's root would still need its
  own move or config, and both would leave the paths every tool and doc assumes.
- **Subvolumes nested inside `@`** (like `@/swap`). Also excluded from snapshots, but
  they hang off `@` itself, and how Limine's `replace` restore treats subvolumes
  nested in the old `@` is not documented in its README. Top-level siblings are not
  touched by a restore at all.
- **A snapper config for `@work`.** Out of scope; Git is `/work`'s history. Omarchy's
  `snapper.sh` also rewrites `SNAPPER_CONFIGS="root"`.
- **Leave it and rely on care.** Rejected: one routine rollback after a bad update
  would silently rewind every project.
- **Automatic migration in `install.sh`.** Rejected: moving tens of GiB of live data
  needs stopped writers, a stopped Docker, verification and a rollback path, which is
  an operator decision every time.

## References

- [`workstation/storage/README.md`](https://github.com/chipi/agentic-ai-homelab/blob/main/workstation/storage/README.md) — files, commands, fresh-machine steps
- [X3 storage separation runbook](../recipes/x3-storage-separation.md) (one-time migration)
- [Safety-copy retirement](../recipes/x3-storage-safety-copy-retirement.md) (later, approved)
- [`workstation/DEVELOPER-SETUP.md`](https://github.com/chipi/agentic-ai-homelab/blob/main/workstation/DEVELOPER-SETUP.md) — workspace layout and Docker model
