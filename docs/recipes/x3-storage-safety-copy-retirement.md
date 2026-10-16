# X3 storage safety-copy retirement

The [storage separation runbook](x3-storage-separation.md) leaves the original
directories inside `@` as safety copies:

- `/work.pre-subvol`
- `/var/lib/docker.pre-subvol`
- `/var/lib/containerd.pre-subvol`

This procedure retires them. It is a **separate operation**, never part of the
migration, never scheduled, and never age-based: each copy is deleted only after
every check below passes and the operator has explicitly approved that specific path.
Not retiring them is always safe; they share data extents with the new subvolumes and
cost little.

Context: [ADR-0011](../adr/ADR-0011-workstation-storage-subvolumes.md).

## 1. Readiness (all must be true)

Record the evidence for each in the retirement note (section 5).

- [ ] **The new layout is live.** `# "$WBS" status` says `separated` (exit 0), where
  `WBS` is the repo's `workstation/storage/wb-storage` (`WBS=$(readlink -f ~marko/.local/bin/wb-storage)`), and

  ```
  # for p in /work /var/lib/docker /var/lib/containerd; do
  >   printf '%s ' "$p"; findmnt -no SOURCE --mountpoint "$p"; stat -c '  inode %i' "$p"
  > done                     # SOURCE …[/@work] / [/@docker] / [/@containerd]; inode 256 each
  ```

- [ ] **Normal development happened on the new `/work`**: commits, streams and editing
  since the migration date, e.g. `$ git -C /work/<project>/main log --since=<date> --oneline`.
- [ ] **Docker was used successfully** since the migration: builds or Compose runs in
  real work, with no storage errors in `journalctl -u docker -u containerd`.
- [ ] **A Workbench stream went through its whole life** on the new `/work`: created
  (`wb-stream` or `wt switch --create`), workspace setup, used, then teardown and
  retirement (`wb-integrate`, or `wt remove` after a remote merge).
- [ ] **At least one reboot after the migration** came back with the layout:
  `# journalctl --list-boots` shows a boot after the migration date, and the status
  check above passed in that boot.
- [ ] The operator has approved this retirement, naming the paths.

## 2. Identity checks (per path, never by name alone)

A path called `*.pre-subvol` is not proof of anything. For each candidate, all of:

| Check | Command | Must be |
|---|---|---|
| a real directory, not a symlink | `test -d "$p" && ! test -L "$p"` | true |
| not a mountpoint | `mountpoint -q "$p"` | false |
| not a subvolume root | `stat -c %i "$p"` | not `256` |
| inside the root subvolume `@` | `stat -c %d "$p"` vs `stat -c %d /` | equal (each subvolume has its own device number) |
| on the root mount | `findmnt -no SOURCE -T "$p"` | `…[/@]`, same as `findmnt -no SOURCE --mountpoint /` |
| its live counterpart is the subvolume | `mountpoint -q "${p%.pre-subvol}"` and `stat -c %i` | mounted, inode 256 |
| nothing uses it | `"$WBS" users "$p"` as root | exit 0 |

Optional, informational: how far the safety copy has diverged from the live tree
(it is stale by design): `# rsync -aHAXn --numeric-ids --delete --itemize-changes "$p"/ "${p%.pre-subvol}"/ | wc -l`.

## 3. Retire one path

Only the guarded function below deletes anything, one path per call, with a typed
confirmation. Define it in a root shell on the console, working directory `/root`:

```
retire_safety_copy() {   # retire_safety_copy <path>: delete ONE verified safety copy
  local p=$1 live
  case $p in
    /work.pre-subvol|/var/lib/docker.pre-subvol|/var/lib/containerd.pre-subvol) ;;
    *) echo "REFUSE: $p is not one of the three safety-copy paths"; return 1 ;;
  esac
  live=${p%.pre-subvol}
  { [ -d "$p" ] && [ ! -L "$p" ]; }                        || { echo "REFUSE: $p is not a real directory"; return 1; }
  ! mountpoint -q "$p"                                     || { echo "REFUSE: $p is a mountpoint"; return 1; }
  [ "$(stat -c %i "$p")" != 256 ]                          || { echo "REFUSE: $p is a subvolume root"; return 1; }
  [ "$(stat -c %d "$p")" = "$(stat -c %d /)" ]             || { echo "REFUSE: $p is not inside the root subvolume"; return 1; }
  [ "$(findmnt -no SOURCE -T "$p")" = "$(findmnt -no SOURCE --mountpoint /)" ] \
                                                           || { echo "REFUSE: $p is not on the root mount"; return 1; }
  { mountpoint -q "$live" && [ "$(stat -c %i "$live")" = 256 ]; } \
                                                           || { echo "REFUSE: $live is not mounted from its subvolume"; return 1; }
  "$WBS" users "$p"                                        || { echo "REFUSE: $p is in use or the check was inconclusive"; return 1; }
  echo "All checks passed for $p (live tree: $live, $(findmnt -no SOURCE --mountpoint "$live"))."
  local answer; read -r -p "Type the full path to delete it, anything else aborts: " answer
  [ "$answer" = "$p" ] || { echo "not confirmed; nothing deleted"; return 1; }
  rm -r --one-file-system -- "$p" && echo "retired: $p"
}
```

Then, one at a time, reading each result before the next:

```
# retire_safety_copy /var/lib/docker.pre-subvol
# retire_safety_copy /var/lib/containerd.pre-subvol
# retire_safety_copy /work.pre-subvol
```

`--one-file-system` makes `rm` refuse to descend into anything mounted below the path.
A refusal is the expected outcome whenever something is not exactly as verified: stop
and investigate; never work around a refusal.

## 4. After

- `# "$WBS" status` still `separated`; `/work`, Docker and a new tmux session behave as
  before.
- Space comes back only partly and only later: the copies shared extents with the new
  subvolumes, and every root snapshot taken since the migration still contains them
  until Snapper's number cleanup rotates those snapshots out. Do not delete snapshots
  to speed this up.

## 5. Record

Add a dated note to `docs/wip/NEXT_STEPS.md` (strike the retirement item): which paths
were retired, the evidence for each readiness check, and who approved it.
