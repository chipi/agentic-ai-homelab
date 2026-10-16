# X3 storage separation — one-time migration runbook

Moves `/work`, `/var/lib/docker` and `/var/lib/containerd` on the X3 out of the root
Btrfs subvolume `@` into the top-level subvolumes `@work`, `@docker` and
`@containerd`, mounted at the same paths. Why:
[ADR-0011](../adr/ADR-0011-workstation-storage-subvolumes.md). Tooling and the
steady-state files:
[`workstation/storage/`](https://github.com/chipi/agentic-ai-homelab/blob/main/workstation/storage/README.md).

**This is an operator procedure, not automation.** Nothing in the repository runs it.
Every step is run by hand, in order, and each step's check must pass before the next.
A failed check means: stop, and go to [R. Rollback](#r-rollback).

The originals are never deleted by this runbook. They stay as `/work.pre-subvol`,
`/var/lib/docker.pre-subvol` and `/var/lib/containerd.pre-subvol` until a later,
separately approved [safety-copy retirement](x3-storage-safety-copy-retirement.md).

## X3-specific evidence (2026-10-16)

Measured on the X3 during the read-only discovery. **X3-specific: these values are
evidence for this machine, not configuration for any other.** `wb-storage fstab`
derives them on the machine it runs on.

| Item | Value |
|---|---|
| LUKS2 partition | `nvme0n1p2`, unlocked as `/dev/mapper/root` via the kernel command line (`cryptdevice=PARTUUID=…:root`); `/etc/crypttab` has no active entries |
| Btrfs UUID | `3addef3c-18a8-45e3-b929-8f7f2f2cb736` |
| Top-level subvolumes | `@` (256), `@home` (257), `@log` (258), `@pkg` (259), `@factory` (264) |
| Nested in `@` | `@/var/lib/portables`, `@/var/lib/machines`, `@/swap`, `@/.snapshots` |
| Snapshots | 1 and 2 (2026-09-30, before `/work` and Docker data existed), plus `@factory` |
| `/work` | 22.5 GiB apparent, 315,927 entries, 14 hardlinked files, 195 symlinks, 0 ACLs, 0 xattrs, 1 root-owned file |
| `/var/lib/containerd` | 25.2 GiB apparent, 1,146,513 entries, 64 hardlinked, 25,798 symlinks, 58 special files (overlay whiteouts), 2 ACLs, 28,295 files with xattrs (`trusted.overlay.*`, `security.capability`), numeric owners such as 1001, 501, 503 |
| `/var/lib/docker` | 72.8 MiB, 31 entries; 0 volumes, 0 containers |
| Unallocated | 1.75 TiB |

Expected `wb-storage fstab` output on the X3 (X3-specific):

```
UUID=3addef3c-18a8-45e3-b929-8f7f2f2cb736	/work	btrfs	rw,relatime,compress=zstd:3,ssd,space_cache=v2,subvol=/@work	0 0
UUID=3addef3c-18a8-45e3-b929-8f7f2f2cb736	/var/lib/containerd	btrfs	rw,relatime,compress=zstd:3,ssd,space_cache=v2,subvol=/@containerd	0 0
UUID=3addef3c-18a8-45e3-b929-8f7f2f2cb736	/var/lib/docker	btrfs	rw,relatime,compress=zstd:3,ssd,space_cache=v2,subvol=/@docker	0 0
```

**Estimates, not measured:** the reflink copies are bounded by metadata for about
1.46 M entries (a few to about 15 minutes), the verification dry runs by walking both
trees; the whole window including one reboot is about 45–90 minutes. Extra space is
about zero for data (reflinks) plus metadata for the new inodes; the worst case, if
reflinks fall back to real copies, is about 47 GiB.

## Conventions

- `#` prompts are a **root shell on a text console** (Ctrl+Alt+F3, log in, `sudo -i`),
  with its working directory in `/root`, never under `/work`. `$` prompts are the
  workstation user (`marko`) in a normal shell.
- `WBS=/root/x3-storage-tools/wb-storage` — a copy staged in step D, because the repo
  itself lives under `/work` and is unreachable at its usual path between steps I and M.
- `B=/root/x3-storage-baseline` — where baselines go.
- `TOP=/mnt/x3-btrfs-top` — the top-level (subvolid 5) mount used for the copy.

---

## A. Prerequisites

- [ ] This repository at a commit that contains `workstation/storage/`; `install.sh`
  has linked `~/.local/bin/wb-storage`.
- [ ] `$ wb-storage status` says `needs-migration` (as a normal user the Docker trees
  show as unreadable; that is expected).
- [ ] Tools present: `command -v rsync cp getfacl getfattr btrfs findmnt` (all are on
  the X3 today: rsync 3.5.0, coreutils 9.11, btrfs-progs 7.1).
- [ ] `# btrfs filesystem usage -T /` shows more than 100 GiB unallocated.
- [ ] Time for the full window, at the console, without interruption.

## B. Emergency-access verification (blocking)

An fstab mistake stops the boot (deliberately: no `nofail`). Before the window, prove
at least one way back in, and write down which:

```
# passwd -S root                                  # "P" = root has a password: the emergency shell works
# grep -iE '^[[:space:]]*editor_enabled' /boot/limine.conf
                                                  # no line, or "yes": the boot-menu editor (E) works
```

1. Root has a password → emergency shell → [R6](#r6-boot-fails-because-of-fstab) (a).
2. Limine editor enabled → `init=/bin/bash` → R6 (b).
3. Neither → a tested Omarchy/Arch live USB on hand → R6 (d). Booting a pre-migration
   snapshot entry (R6 (c)) also works, but do not rely on it alone.

**Gate:** at least one path confirmed.

## C. Off-machine backup of unique project state (blocking)

The originals are kept, so the migration does not put these at risk, but no protected
copy exists anywhere today and the window touches every file on the machine. Never
commit these files or their contents.

| File | Why it is unique |
|---|---|
| `/work/orrery/main/.env` | secrets (currently mode **0644**: correct to 0600 separately) |
| `/work/orrery/main/.env.local` | local settings |
| `/work/orrery/main/.env.backup-2026-06-17` | old secrets |
| `/work/orrery/main/docker-compose.override.yml` | local override |
| `/work/orrery/main/mise.local.toml` | local override |
| `/work/oceancanvas/main/.env` | secrets |
| `/work/oceancanvas/main/compose/.env` | secrets |

`.env.workspace` files are generated by `wb-workspace setup`; they are not backed up.

**Gate (all three):**

- [ ] an encrypted backup of every file above exists **off the X3**;
- [ ] it has been **decrypted** somewhere else, or into a scratch directory, and each
  file compared with the original (`cmp`);
- [ ] the restored set contains every file in the table (count it).

Separately (not part of this runbook): `chmod 0600 /work/orrery/main/.env`.

## Live-state gate: active work (blocking)

On 2026-10-16 Orrery was in a live session: the primary checkout on a **detached HEAD
at `41330dd`** (a merge commit no remote has), plus a linked worktree at
`/tmp/claude-1000/-work-orrery-main/…/replay-baseline-main`. Do not touch either from
this runbook. At migration time the operator confirms, for each:

- [ ] Orrery detached HEAD `41330dd`: landed, intentionally preserved, or abandoned;
- [ ] the `/tmp/…/replay-baseline-main` worktree: removed by its owner or intentionally kept
  (it survives the migration: its `.git` file points at `/work/orrery/main/.git/…`,
  which is the same path afterwards);
- [ ] every agent session, editor and dev server working in `/work`: finished and stopped
  (step G lists what is left).

Read-only checks: `$ git -C /work/orrery/main status -sb`,
`$ git -C /work/orrery/main worktree list`.

## D. Preflight baselines (live, read-only)

Stage the tooling outside `/work`, and record the state to compare against:

```
# install -d -m 0700 /root/x3-storage-baseline
# cp -a /work/agentic-ai-homelab/workstation/storage /root/x3-storage-tools
# WBS=/root/x3-storage-tools/wb-storage; B=/root/x3-storage-baseline
# "$WBS" status | tee "$B/status.before"           # needs-migration
# "$WBS" fstab  | tee "$B/fstab.rendered"          # must equal the X3 lines above
# cp -a /etc/fstab "$B/fstab.before"
```

Docker state, as the user (the daemon is running). The same function is used again
in O, so before and after are produced identically:

```
$ dockerstate() {   # dockerstate <dir>: read-only Docker metadata snapshot
>   mkdir -p "$1"
>   docker image ls --all --no-trunc --format '{{.ID}} {{.Repository}}:{{.Tag}}' | sort > "$1/images"
>   docker image inspect --format '{{.Id}} {{with index .Config "Labels"}}{{index . "com.docker.compose.project"}} {{index . "com.docker.compose.service"}}{{end}}' \
>     $(docker image ls --all -q --no-trunc | sort -u) | sort > "$1/compose-labels"
>   docker info --format '{{.DockerRootDir}} {{.Driver}} images={{.Images}} containers={{.Containers}}' > "$1/info"
>   docker network ls --format '{{.Name}} {{.Driver}}' | sort > "$1/networks"
>   docker volume ls -q | sort > "$1/volumes"
>   docker builder du | tail -3 > "$1/builder-du"
> }
$ dockerstate /tmp/x3-docker-before && sudo cp -r /tmp/x3-docker-before /root/x3-storage-baseline/docker
$ sudo cat /var/lib/docker/engine-id | sudo tee /root/x3-storage-baseline/engine-id >/dev/null
```

Expected today: 16 images, 0 containers, 0 volumes, networks `bridge host none`.
Run the step O smoke tests now as well (`ok-alpine`, `ok-node`, `ok-layers-readable`):
they must pass **before** the migration, so a failure afterwards is attributable.

Structural fingerprint function, used again in K (define it in the root shell):

```
stats() {   # stats <dir>: path-independent structure of a tree
  ( cd "$1" && {
    echo "entries $(find . -xdev | wc -l)"
    echo "types $(find . -xdev -printf '%y\n' | sort | uniq -c | tr -s ' ' | tr '\n' ' ')"
    echo "hardlinked $(find . -xdev -type f -links +1 | wc -l)"
    echo "acl-files $(getfacl -R -s -p . 2>/dev/null | grep -c '^# file:')"
    echo "xattr-files $(getfattr -R -h -m - . 2>/dev/null | grep -c '^# file:')"
    echo "owners $(find . -xdev -printf '%U:%G\n' | sort | uniq -c | tr -s ' ' | tr '\n' ' ')"
    echo "bytes $(du -sx --apparent-size -B1 . | cut -f1)"
  } )
}
```

## E. Create `@work`, `@docker`, `@containerd`

Harmless while live: new, empty top-level subvolumes, not inside `@`, mounted nowhere.

```
# TOP=/mnt/x3-btrfs-top
# install -d -m 0700 "$TOP"
# mount -o subvolid=5 UUID="$(findmnt -no UUID --mountpoint /)" "$TOP"
# ls "$TOP"                                   # @ @factory @home @log @pkg — nothing else
# btrfs subvolume create "$TOP/@work" "$TOP/@docker" "$TOP/@containerd"
# chown marko:marko "$TOP/@work"; chmod 0755 "$TOP/@work"
# chown root:root "$TOP/@docker" "$TOP/@containerd"; chmod 0710 "$TOP/@docker"; chmod 0700 "$TOP/@containerd"
# btrfs subvolume list -a -t /                # three new rows: <FS_TREE>/@work etc., parent 5, top level 5
# stat -c '%n %U:%G %a %i' "$TOP"/@work "$TOP"/@docker "$TOP"/@containerd   # owners/modes as set, inode 256
```

If E runs before the window day: `# umount "$TOP"` now and mount it again at the
start of I.

## F. Maintenance-window gate

All true, or do not start:

- [ ] B: an emergency path is confirmed.
- [ ] C: the backup gate passed.
- [ ] Live-state gate: Orrery and all active work confirmed.
- [ ] D: baselines recorded; `$WBS` staged in `/root`.
- [ ] E: the three subvolumes exist and are empty (`ls -A "$TOP"/@work` prints nothing).
- [ ] At the text console, with time for the whole window and a reboot.

## G. Stop everything that uses `/work`

The invariant is **no live process uses `/work` or the Docker trees**, not "kill all
tmux sessions". Find what is still there:

```
# "$WBS" users /work           # read-only: cwd, root, open fds and mapped files under /work
```

For each process listed, decide and act yourself: save and quit the editor, finish
and exit the agent session, stop the dev server with its own command, `exit` or `cd ~`
in the shell, or close that tmux window. If something must be stopped by force, stop
**that PID** (`kill <pid>`), after `ps -o pid,args -p <pid>` confirms what it is. Never
`pkill`, `killall` or `pkill -f`. Repeat until `users` lists nothing (as root: exit 0).

Then the window-time Git baseline, as the user from outside `/work` (git is
short-lived and leaves nothing running):

```
$ cd ~
$ gitstate() {   # read-only state of every repository under /work
>   for r in /work/agentic-ai-homelab /work/*/main; do
>     echo "== $r"
>     git -C "$r" status --porcelain=v2 --branch
>     git -C "$r" rev-parse HEAD
>     git -C "$r" worktree list --porcelain
>     git -C "$r" log --branches --not --remotes --oneline
>     git -C "$r" stash list
>   done
> }
$ gitstate > /tmp/x3-git-baseline && sudo install -m 0600 /tmp/x3-git-baseline /root/x3-storage-baseline/git
$ find /work -xdev ! -user marko -printf '%u:%g %p\n' | sort | sudo tee /root/x3-storage-baseline/foreign-owned
```

Expected foreign-owned today: one file,
`/work/oceancanvas/main/pipeline/tests/fixtures/recipes/e2e-save-test.yaml` (root).

## H. Stop Docker and containerd

Socket first, so nothing can start the daemon again:

```
# systemctl stop docker.socket
# systemctl stop docker.service
# systemctl stop containerd.service
# systemctl is-active docker.socket docker.service containerd.service    # inactive ×3
# pgrep -a -x dockerd; pgrep -a -x containerd; pgrep -a -f containerd-shim  # no output
# "$WBS" users                  # all three paths: "no process uses …", exit 0
```

Any output from `pgrep` or `users`: stop here and find out why.

## I. Rename the originals to `*.pre-subvol`

```
# for p in /work /var/lib/docker /var/lib/containerd; do [ -e "$p.pre-subvol" ] && echo "STOP: $p.pre-subvol exists"; done
                                                    # must print nothing
# mv -T /work /work.pre-subvol
# mv -T /var/lib/docker /var/lib/docker.pre-subvol
# mv -T /var/lib/containerd /var/lib/containerd.pre-subvol
# install -d -o marko -g marko -m 0755 /work
# install -d -o root  -g root  -m 0710 /var/lib/docker
# install -d -o root  -g root  -m 0700 /var/lib/containerd
# ls -A /work /var/lib/docker /var/lib/containerd   # all empty
```

Renaming first means a missed writer fails on the missing path instead of silently
changing the source while it is copied. The originals are not modified after this.

## J. Root-preserving reflink copy

```
# mountpoint -q "$TOP" || mount -o subvolid=5 UUID="$(findmnt -no UUID --mountpoint /)" "$TOP"
# cp -a --reflink=auto /work.pre-subvol/.               "$TOP/@work/";       echo "work rc=$?"
# cp -a --reflink=auto /var/lib/containerd.pre-subvol/. "$TOP/@containerd/"; echo "containerd rc=$?"
# cp -a --reflink=auto /var/lib/docker.pre-subvol/.     "$TOP/@docker/";     echo "docker rc=$?"
```

All three `rc=0`, no error lines; otherwise [R1](#r1-copy-or-verification-fails).

Why this command: source and destination are on the same Btrfs filesystem, so
`--reflink` shares data extents instead of writing them (near-zero data space, fast);
`auto` falls back to a real copy where a reflink is impossible instead of aborting.
`cp -a` as root keeps numeric owners, modes, timestamps, hardlinks (within one call),
symlinks, special files (overlay whiteouts), ACLs and all xattrs: `/etc/xattr.conf`
skips only XFS, AFS, Beagle and `security.evm` keys, so `trusted.overlay.*` is copied.
Holes in sparse files survive the reflink.

## K. Verify the copies (before any configuration changes)

Metadata and structure; an empty dry-run diff is the pass condition:

```
# rsync -aHAXn --numeric-ids --delete --itemize-changes /work.pre-subvol/               "$TOP/@work/"       | tee "$B/diff.work"
# rsync -aHAXn --numeric-ids --delete --itemize-changes /var/lib/containerd.pre-subvol/ "$TOP/@containerd/" | tee "$B/diff.containerd"
# rsync -aHAXn --numeric-ids --delete --itemize-changes /var/lib/docker.pre-subvol/     "$TOP/@docker/"     | tee "$B/diff.docker"
# wc -l "$B"/diff.*                               # 0 0 0
# for t in work containerd docker; do
>   case $t in work) s=/work.pre-subvol ;; *) s=/var/lib/$t.pre-subvol ;; esac
>   stats "$s" > "$B/stats.$t.src"; stats "$TOP/@$t" > "$B/stats.$t.dst"
>   diff "$B/stats.$t.src" "$B/stats.$t.dst" && echo "$t: identical"
> done
```

All three `identical`; compare the numbers with the evidence table (`/work` will have
grown or shrunk with normal work since; containerd should be close to it).

Optional, `/work` only: a full content checksum (reads about 22 GiB twice), if wanted:
`# rsync -aHAXn -c --numeric-ids --delete --itemize-changes /work.pre-subvol/ "$TOP/@work/"`
(empty output). A full checksum of the containerd tree is not required.

## L. Install the fstab entries and the systemd drop-ins

```
# cp -a /etc/fstab /etc/fstab.pre-subvol
# "$WBS" fstab                                     # review: identical to $B/fstab.rendered
# "$WBS" fstab | grep -v '^#' >> /etc/fstab
# findmnt --verify --verbose                       # 0 errors, 0 warnings for the new lines
# "$WBS" install-dropins                           # INST ×2; no-block-boot.conf untouched
# systemctl daemon-reload
# systemctl show docker.service -p RequiresMountsFor -p Requires | tr ' ' '\n' | grep -E 'var-lib-(docker|containerd)\.mount|/var/lib'
# systemctl show containerd.service -p RequiresMountsFor
# systemctl cat docker.service | grep -E '^# /|DefaultDependencies|RequiresMountsFor'
                                                   # both drop-ins listed; Omarchy's unchanged
```

## M. Mount and verify

```
# umount "$TOP" && rmdir "$TOP"
# mount /work && mount /var/lib/containerd && mount /var/lib/docker
# findmnt -no TARGET,SOURCE,OPTIONS --mountpoint /work
# findmnt -no TARGET,SOURCE,OPTIONS --mountpoint /var/lib/containerd
# findmnt -no TARGET,SOURCE,OPTIONS --mountpoint /var/lib/docker
                    # SOURCE /dev/mapper/root[/@work] etc.; OPTIONS end in subvol=/@work etc.
# stat -c '%n %i %U:%G %a' /work /var/lib/docker /var/lib/containerd
                    # inode 256 (subvolume roots): marko:marko 755, root:root 710, root:root 700
# "$WBS" status     # separated (exit 0)
```

## N. `/work` and Git acceptance

As the user, in a **new** login shell (old shells may still sit in renamed paths;
define `gitstate` again as in G):

```
$ ls /work                         # abyss agentic-ai-homelab bathys chemigram oceancanvas orrery
$ gitstate > /tmp/x3-git-after
$ sudo diff /root/x3-storage-baseline/git /tmp/x3-git-after && echo "git state identical"
$ for r in /work/agentic-ai-homelab /work/*/main; do git -C "$r" fsck --connectivity-only --no-progress || echo "FSCK FAIL $r"; done
$ find /work -xdev ! -user marko -printf '%u:%g %p\n' | sort | sudo diff /root/x3-storage-baseline/foreign-owned - && echo "ownership identical"
```

Optional, read-only, slower: a full `git -C /work/orrery/main fsck` (about 9.5 GiB of
packs). If the `/tmp/…/replay-baseline-main` worktree still exists:
`$ git -C <that path> rev-parse --git-dir` resolves into `/work/orrery/main/.git/worktrees/`.

Workbench, in `bathys` (tiny, Model-B, no project workspace hooks, so setup and
teardown are no-ops):

```
$ cd /work/bathys/main
$ wt switch --create storage-accept --base @     # → /work/bathys/worktrees/storage-accept
$ cd /work/bathys/main
$ wt remove storage-accept                        # pre-remove: live-check, then teardown; worktree and branch gone
$ git worktree list; ls /work/bathys/worktrees    # only main; empty
```

tmux, a new session of its own, removed by its exact name:

```
$ tmux new-session -d -s storage-accept -c /work/bathys/main
$ tmux display-message -p -t storage-accept '#{pane_current_path}'   # /work/bathys/main
$ tmux kill-session -t storage-accept
```

No project builds or test suites are part of this acceptance.

## O. Docker acceptance

```
# systemctl start containerd.service docker.socket
$ docker info --format '{{.DockerRootDir}} {{.Driver}} images={{.Images}} containers={{.Containers}}'
                                                   # /var/lib/docker overlayfs images=16 containers=0
```

```
$ dockerstate /tmp/x3-docker-after              # the function from D
$ sudo diff -r /root/x3-storage-baseline/docker /tmp/x3-docker-after && echo "docker metadata identical"
# cmp /var/lib/docker/engine-id "$B/engine-id" && echo "engine-id identical"
```

`images`, `compose-labels`, `info`, `networks`, `volumes` and `builder-du` must all be
identical.

Smoke tests, cached images only, no network, removed afterwards:

```
$ docker run --rm --pull=never --network none alpine:3.20 true && echo ok-alpine
$ docker run --rm --pull=never --network none node:20-slim node -e 'process.exit(0)' && echo ok-node
$ ( set -o pipefail; docker save oceancanvas-main-pipeline:latest | wc -c ) && echo ok-layers-readable
                                                   # about 650 MB streamed (2026-10-16); docker save refuses -o /dev/null
# journalctl -b -u containerd -u docker --since "-15 min" | grep -iE 'error|overlay|xattr' | grep -v 'level=info'
                                                   # nothing new and unexplained
```

`node:20-slim` exercises a multi-layer overlay mount with whiteouts and the copied
`trusted.overlay.*` xattrs; `docker save` streams every layer blob of a large Compose
image out of the content store (read-only; the output goes to `wc`). No OceanCanvas build or test run.

## P. First post-layout Snapper snapshot

After M–O pass and before the reboot. Its two purposes: the first known-good rollback
point whose `/etc/fstab` knows the new layout, and proof that a root snapshot does not
contain `@work`, `@docker` or `@containerd`.

```
# N=$(snapper -c root create -c number -d "post-storage-separation" --userdata important=yes --print-number); echo "$N"
# S=/.snapshots/$N/snapshot
# stat -c '%n %i' "$S/work" "$S/var/lib/docker" "$S/var/lib/containerd"   # none is 256: plain directories
# ls -A "$S/work" "$S/var/lib/docker" "$S/var/lib/containerd"            # all three empty
# btrfs subvolume list -a / | grep -E '/@(work|docker|containerd)$'      # exactly 3 rows, top level 5
# btrfs subvolume list -a / | grep -E "snapshots/$N/snapshot/"             # nothing: no nested copy
# grep -cE 'subvol=/@(work|docker|containerd)' "$S/etc/fstab"             # 3
```

`important=yes` keeps it under `NUMBER_LIMIT_IMPORTANT`. The `*.pre-subvol`
directories do appear in this snapshot, because they are ordinary directories in
`@`: that contrast is the proof that the subvolumes are excluded and ordinary
directories are not. Limine adds a boot entry for it.

## Q. Reboot and acceptance

```
# systemctl reboot
```

Unlock LUKS at the prompt. Then:

```
# findmnt -no TARGET,SOURCE --mountpoint /work; findmnt -no TARGET,SOURCE --mountpoint /var/lib/docker; findmnt -no TARGET,SOURCE --mountpoint /var/lib/containerd
# systemctl --failed                                   # 0 units
# "$WBS" status                                        # separated
# journalctl -b -o short-monotonic -u var-lib-containerd.mount -u var-lib-docker.mount -u containerd.service -u docker.service | head -20
                                                       # the mounts come up before containerd/dockerd start
$ docker run --rm --pull=never --network none alpine:3.20 true && echo ok
$ ssh-add -l; tailscale status | head -3               # agent and tailnet as before
```

From another machine on the tailnet: `ssh <x3> true`. Open a new tmux session for a
project and work normally.

Migration accepted. The `*.pre-subvol` copies stay (S).

---

## R. Rollback

Every path returns to the original ordinary directories inside `@`, from the untouched
`*.pre-subvol` copies; nothing is restored from backup.

**Core reversal** (valid from step I onward):

```
# systemctl stop docker.socket docker.service containerd.service
# umount /var/lib/docker /var/lib/containerd /work 2>/dev/null
# mountpoint -q /mnt/x3-btrfs-top && umount /mnt/x3-btrfs-top
# [ -f /etc/fstab.pre-subvol ] && cp -a /etc/fstab.pre-subvol /etc/fstab
# rm -f /etc/systemd/system/docker.service.d/50-x3-storage-mounts.conf /etc/systemd/system/containerd.service.d/50-x3-storage-mounts.conf
# systemctl daemon-reload
# rmdir /work /var/lib/docker /var/lib/containerd       # the empty mountpoints; rmdir refuses anything else
# mv -T /work.pre-subvol /work
# mv -T /var/lib/docker.pre-subvol /var/lib/docker
# mv -T /var/lib/containerd.pre-subvol /var/lib/containerd
# systemctl start containerd.service docker.socket
# "$WBS" status                                          # needs-migration again
```

(The `rm -f` names exactly the two workstation-owned drop-in files; Omarchy's
`no-block-boot.conf` is never touched.) `@work`, `@docker` and `@containerd` stay as
they are for diagnosis; they are never the only copy, and deleting them is a separate
decision.

### R1. Copy or verification fails

Core reversal (fstab and drop-ins are not installed yet, so those lines are no-ops).

### R2. Mount fails (M)

Core reversal. Look at `dmesg | tail` and the fstab lines before retrying.

### R3. Docker will not start, or R4. Docker metadata differs (O)

`journalctl -b -u containerd -u docker`. If it is not understood within minutes: core
reversal. The originals are consistent: Docker was stopped before the rename and never
ran against them afterwards.

### R5. Git verification fails (N)

Core reversal (it can be done for `/work` alone: unmount `/work`, remove only its fstab
line, `rmdir /work`, `mv -T /work.pre-subvol /work`).

### R6. Boot fails because of fstab

(a) Root has a password: log in at the emergency prompt, run the core reversal.
(b) Limine editor: at the menu press **E** on the default entry, append
`init=/bin/bash` to the kernel command line, boot, `mount -o remount,rw /`, then
`cp /etc/fstab.pre-subvol /etc/fstab` (and the rest of the core reversal after a
normal boot).
(c) Boot snapshot 1 or 2 from the Limine menu (their fstab predates the migration),
then `mount -o subvolid=5 /dev/mapper/root /mnt` and
`cp /mnt/@/etc/fstab.pre-subvol /mnt/@/etc/fstab`; reboot normally and finish the
core reversal.
(d) Live USB: `cryptsetup open /dev/nvme0n1p2 root`, then as (c).

### R7. A problem found later (after acceptance)

The originals are stale by then. With writers and Docker stopped (G, H), first bring
the newer state back: `rsync -aHAX --numeric-ids --delete /work/ /work.pre-subvol/`
(and the same for the two Docker trees if needed), check with the K dry runs in
reverse, then the core reversal.

### After a rollback

Snapshot N (P), if it was created, has an fstab that mounts the now-stale `@work`.
Do not restore it; remove it with explicit approval
(`snapper -c root delete <N>`) or note it as unusable.

### Legacy snapshots after the migration

Restoring snapshot 1, 2 or `@factory` brings back a root whose `/etc/fstab` does not
mount the new subvolumes. `@work`, `@docker` and `@containerd` are not affected; the
fix is to add the three entries and the empty mountpoints again
(`wb-storage fstab`, step L, step I's `install -d` lines). Snapshot N is the first
rollback point that needs no fix.

## S. Safety-copy retention

`/work.pre-subvol`, `/var/lib/docker.pre-subvol` and `/var/lib/containerd.pre-subvol`
stay in `@`, unchanged, through acceptance and normal use. They share extents with the
new copies, so they cost little space, and each later root snapshot also contains
them until they are retired. Nothing reads or writes them; do not `cd` into them.
There is no automatic or age-based removal.

## T. Later: retiring the safety copies

A separate operation with its own approval and checks:
[X3 storage safety-copy retirement](x3-storage-safety-copy-retirement.md). Not part of
this runbook.
