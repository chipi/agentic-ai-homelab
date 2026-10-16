# storage — the Linux workstation storage layout

Why: [ADR-0011](../../docs/adr/ADR-0011-workstation-storage-subvolumes.md). In short,
`@` is the OS rollback domain, and the three paths that must never be rewound by an OS
rollback, or pinned by root snapshots, get their own top-level Btrfs subvolumes. The
paths themselves don't change.

```
LUKS2 → Btrfs (one filesystem)
  @            /                      Snapper root config: the only thing rolled back
  @home        /home
  @log         /var/log
  @pkg         /var/cache/pacman/pkg
  @factory     (Omarchy factory reset)
  @work        /work                  marko:marko 0755   developer working state
  @docker      /var/lib/docker        root:root   0710   Docker metadata, BuildKit records, logs
  @containerd  /var/lib/containerd    root:root   0700   image content, layer snapshots, build cache data
```

A root snapshot contains only the three **empty mountpoint directories**: Btrfs
snapshots stop at subvolume boundaries, and these subvolumes are not even inside `@`.
Git and GitHub are `/work`'s durability; Snapper is rollback, not backup; unique local
secrets and state go in the small encrypted off-machine backup.

## Files

| File | Installed as | How |
|---|---|---|
| `systemd/docker.service.d/50-x3-storage-mounts.conf` | `/etc/systemd/system/docker.service.d/50-x3-storage-mounts.conf` | `wb-storage install-dropins`, as root |
| `systemd/containerd.service.d/50-x3-storage-mounts.conf` | `/etc/systemd/system/containerd.service.d/50-x3-storage-mounts.conf` | `wb-storage install-dropins`, as root |
| `wb-storage` | `~/.local/bin/wb-storage` | `install.sh` (symlink) |
| fstab entries | appended to `/etc/fstab` | rendered by `wb-storage fstab`; added by hand |

The drop-ins exist because Omarchy's package-owned `docker.service.d/no-block-boot.conf`
sets `DefaultDependencies=no`, which drops Docker's implicit ordering after local
filesystems. `RequiresMountsFor=` restores it explicitly: Docker cannot start before
`/var/lib/docker` and `/var/lib/containerd` are mounted, and containerd cannot start
before `/var/lib/containerd` is. They sit next to `no-block-boot.conf`; nothing here
edits or replaces it. `RequiresMountsFor=` adds `Requires=` and `After=` on "all mount
units required to access the specified path" (`systemd.unit(5)`), so before the fstab
entries exist the only such unit is the root mount and the drop-ins change nothing.

## `wb-storage`

```
wb-storage status [--brief]        read-only: classify this machine's layout
wb-storage fstab                   read-only: print the three fstab entries for this machine
wb-storage users [path...]         read-only: processes using the paths (cwd, root, fds, maps)
wb-storage install-dropins [--dry-run]   install the two drop-ins (idempotent, needs root)
```

`sudo`'s `secure_path` does not include `~/.local/bin`, so call it by path as root:
`WBS="$(command -v wb-storage)"`, then `sudo "$WBS" status`.

- **`status`** exit codes: `0` separated (mounted from the right subvolumes, fstab
  entries and drop-ins in place), `3` fresh (paths absent or empty, no entries), `4`
  needs migration (data in an ordinary directory inside `@`), `5` incomplete or
  inconsistent, `2` cannot be determined. As a normal user, `/var/lib/docker` and
  `/var/lib/containerd` are unreadable; run it with `sudo` for a full picture.
- **`fstab`** takes the UUID from the mounted root filesystem, checks it against the
  root entry in `/etc/fstab` (which must be Btrfs with `subvol=/@`), and copies that
  entry's options, dropping `subvol=`, `subvolid=` and `nofail`, then adds
  `subvol=/@work` (and so on). It never prints `nofail`: a missing storage mount must
  stop the boot, not let Docker or development write into the empty directories inside
  `@`. Nothing machine-specific is in this repository's code.
- **`users`** is the live-process check the migration and retirement procedures gate
  on. It never stops anything; stop what it lists yourself, by PID (never `pkill`,
  `killall` or `pkill -f`). As a normal user it can only see your own processes, so
  "none" is inconclusive (exit 2) until run as root.
- **`install-dropins`** copies the two files, `0644`. If an installed copy differs, it is
  backed up as `*.bak.<ts>` (systemd ignores those) and replaced. Re-running changes
  nothing. It prints `NEXT  systemctl daemon-reload` and never reloads, starts or stops
  a unit itself.

`wb-storage` never creates or deletes subvolumes, edits fstab, mounts, moves, copies
or deletes data, or touches Docker.

## Fresh machine vs. existing machine

`install.sh` links `wb-storage` and prints one line, `INFO  storage: <verdict>`. It
never changes the layout, on any machine.

- **Existing machine with data** (`status` → `needs-migration`, e.g. the X3 today):
  nothing is changed automatically. Follow the one-time operator runbook,
  [`docs/recipes/x3-storage-separation.md`](../../docs/recipes/x3-storage-separation.md),
  and later the separate
  [safety-copy retirement](../../docs/recipes/x3-storage-safety-copy-retirement.md).
- **Fresh machine** (`status` → `fresh`): the layout can be established directly,
  before the first project clone and before Docker first starts (Omarchy enables
  `docker.socket`, so any `docker` command creates `/var/lib/docker`; once it holds
  data, the machine is an existing machine). By hand, as root:

  ```bash
  WBS="$(command -v wb-storage)"
  sudo "$WBS" status                       # must say "fresh"; stop otherwise
  sudo systemctl stop docker.socket docker.service containerd.service
  sudo mkdir /mnt/btrfs-top
  sudo mount -o subvolid=5 UUID="$(findmnt -no UUID --mountpoint /)" /mnt/btrfs-top
  sudo btrfs subvolume create /mnt/btrfs-top/@work /mnt/btrfs-top/@docker /mnt/btrfs-top/@containerd
  sudo chown marko:marko /mnt/btrfs-top/@work && sudo chmod 0755 /mnt/btrfs-top/@work
  sudo chmod 0710 /mnt/btrfs-top/@docker && sudo chmod 0700 /mnt/btrfs-top/@containerd
  sudo umount /mnt/btrfs-top && sudo rmdir /mnt/btrfs-top
  sudo install -d -o marko -g marko -m 0755 /work
  sudo install -d -m 0710 /var/lib/docker && sudo install -d -m 0700 /var/lib/containerd
  sudo cp -a /etc/fstab /etc/fstab.pre-storage
  wb-storage fstab                             # review the three lines
  wb-storage fstab | grep -v '^#' | sudo tee -a /etc/fstab >/dev/null
  sudo findmnt --verify --verbose              # 0 errors
  sudo "$WBS" install-dropins && sudo systemctl daemon-reload
  sudo mount /work && sudo mount /var/lib/containerd && sudo mount /var/lib/docker
  sudo "$WBS" status                       # must say "separated"
  sudo systemctl start docker.socket
  ```

  Then reboot once and check `sudo "$WBS" status` again. (Replace `marko` with the
  workstation user.) Automating this in the installer is deliberately not done: it
  would have to prove the paths are empty and Docker never ran, and refusal is cheaper
  than a clever migration.

## Tests

`bash workstation/storage/wb-storage.test.sh` — scratch roots and a fake `findmnt`
only; the live `/etc`, mounts, Docker and `/work` are never touched. It covers the
drop-in contents, fstab rendering (derived, never `nofail`, never the X3 UUID),
`status` classification, `install-dropins` idempotence next to an untouched
`no-block-boot.conf`, the `users` check (cwd, open fd, mapped file), and static guards,
mutation-tested, that `wb-storage` and `install.sh` contain no subvolume, mount,
move/copy, delete, unit or Docker command. `bash workstation/install.test.sh` proves a
populated scratch `/work` and Docker trees are reported and left byte-identical by a
real installer run.
