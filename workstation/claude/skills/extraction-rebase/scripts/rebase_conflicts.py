#!/usr/bin/env python3
"""Sort the conflicts of a stopped rebase whose branch deletes extracted code.

    rebase_conflicts.py                  # classify; changes nothing
    rebase_conflicts.py --apply          # resolve only the safe kinds (see below)
    rebase_conflicts.py --show PATH      # print PATH's conflict hunks with line numbers

The delete set is what the branch itself deletes: diff --diff-filter=D --no-renames from
merge-base(onto, orig-head) to orig-head. In a rebase "ours" is the trunk being rebased onto and
"theirs" is the branch commit being replayed.

  UD  trunk modified, branch deleted. In the delete set -> resolve by deleting. The trunk commits
      that touched it are listed: their change has to reach wherever the code was extracted to.
  DD  both deleted -> resolve by deleting.
  DU  trunk deleted, branch modified -> decide by hand.
  UU/AA/AU/UA  content conflict -> decide by hand, hunk by hunk (--show). Never take a side blindly.

Exit 0: nothing left for a human. 3: something is. 2: not in a stopped rebase.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def git(*args: str, check: bool = True) -> str:
    return subprocess.run(["git", *args], capture_output=True, text=True, check=check).stdout.strip()


def rebase_state() -> tuple[str, str] | None:
    for d in ("rebase-merge", "rebase-apply"):
        p = Path(git("rev-parse", "--git-path", d))
        if (p / "onto").exists() and (p / "orig-head").exists():
            return (p / "onto").read_text().strip(), (p / "orig-head").read_text().strip()
    return None


def unmerged() -> list[tuple[str, str]]:
    raw = subprocess.run(["git", "status", "--porcelain=v1", "-z"], capture_output=True, text=True, check=True).stdout
    out = []
    for entry in raw.split("\0"):
        if len(entry) > 3:
            xy, path = entry[:2], entry[3:]
            if xy in {"DD", "AU", "UD", "UA", "DU", "AA", "UU"}:
                out.append((xy, path))
    return out


def show(path: str) -> None:
    lines = Path(path).read_text(errors="replace").splitlines()
    n, inside = 0, False
    for i, line in enumerate(lines, 1):
        if line.startswith("<<<<<<<"):
            n, inside = n + 1, True
            print(f"--- hunk {n} at line {i}")
        if inside:
            print(f"{i:6}  {line}")
        if line.startswith(">>>>>>>"):
            inside = False
    print(f"{n} hunk(s) in {path}" if n else f"no conflict markers in {path}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true", help="delete the UD-in-delete-set and DD paths")
    ap.add_argument("--show", metavar="PATH", help="print PATH's conflict hunks and exit")
    ap.add_argument("--delete-set", metavar="FILE", help="paths the branch deletes, one per line (default: computed)")
    a = ap.parse_args()
    if a.show:
        show(a.show)
        return 0
    st = rebase_state()
    if not st:
        print("not in a stopped rebase (no rebase-merge/ or rebase-apply/ state)", file=sys.stderr)
        return 2
    onto, orig = st
    old_base = git("merge-base", onto, orig)
    if a.delete_set:
        dset = {l.strip() for l in Path(a.delete_set).read_text().splitlines() if l.strip()}
    else:
        dset = set(git("diff", "--name-only", "--diff-filter=D", "--no-renames", old_base, orig).splitlines())
    print(f"rebasing {orig[:8]} onto {onto[:8]} (old base {old_base[:8]}); the branch deletes {len(dset)} path(s)")

    rows = unmerged()
    if not rows:
        print("no unmerged paths")
        return 0
    auto, manual = [], []
    for xy, p in rows:
        if xy == "DD" or (xy == "UD" and p in dset):
            auto.append((xy, p))
        else:
            manual.append((xy, p))

    for xy, p in auto:
        trunk = git("log", "--oneline", f"{old_base}..{onto}", "--", p).splitlines()
        print(f"DELETE  {xy}  {p}")
        for c in trunk[:5]:
            print(f"          trunk changed it: {c}")
        if len(trunk) > 5:
            print(f"          … {len(trunk) - 5} more")
        if a.apply:
            git("rm", "-q", "--", p)
    for xy, p in manual:
        why = {"DU": "trunk deleted it, the branch modified it"}.get(xy, "content conflict")
        if xy == "UD":
            why = "trunk modified it, the branch deleted it, but it is NOT in the branch's delete set"
        hunks = ""
        if Path(p).is_file() and xy in {"UU", "AA", "AU", "UA"}:
            hunks = f", {sum(1 for l in Path(p).read_text(errors='replace').splitlines() if l.startswith('<<<<<<<'))} hunk(s)"
        print(f"MANUAL  {xy}  {p}  ({why}{hunks})")

    trunk_touched = [p for xy, p in auto if xy == "UD"]
    print(f"\n{len(auto)} deletable{' (deleted)' if a.apply else ''}, {len(manual)} for a human")
    if trunk_touched:
        print(f"{len(trunk_touched)} deleted path(s) changed on the trunk since the old base: port those changes to the extracted repo")
    if not a.apply and auto:
        print("re-run with --apply to delete them")
    return 3 if manual else 0


if __name__ == "__main__":
    sys.exit(main())
