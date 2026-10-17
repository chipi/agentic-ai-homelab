#!/usr/bin/env python3
"""After a branch deletes extracted code: find what still points at the deleted paths.

    dangling_refs.py [--base origin/main] [--exclude docs/history/ ...]

Deleted = what the branch deletes, merge-base(--base, HEAD)..HEAD with --no-renames.
Two sections:
  1. Kept tracked text files that mention a deleted path. The full path always counts. The bare
     file name counts only when it is distinctive: 8+ chars, not generic, no kept file has the
     same name.
  2. Test files that build a repo path (a string literal "dir/…" or ROOT / "dir" / "…") to a
     file or directory the branch deleted.
Every hit is a candidate. A history note naming a deleted file is often correct. Read each one.
Exit 1 if anything was found, else 0.
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import tempfile
from collections import defaultdict
from pathlib import Path

GENERIC = {"index.md", "README.md", "__init__.py", "config.yaml", "app.py", "deploy.py", "Makefile",
           "conftest.py", "main.py", "utils.py", "settings.py", "Dockerfile", "action.yml", "package.json"}


def git(*args: str) -> str:
    return subprocess.run(["git", *args], capture_output=True, text=True, check=True).stdout


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", default="origin/main")
    ap.add_argument("--exclude", action="append", default=[], metavar="PREFIX", help="skip kept files under PREFIX")
    ap.add_argument("--max", type=int, default=8, help="deleted paths listed per hit file")
    a = ap.parse_args()
    root = Path(git("rev-parse", "--show-toplevel").strip())
    os.chdir(root)
    mb = git("merge-base", a.base, "HEAD").strip()
    deleted = git("diff", "--name-only", "--diff-filter=D", "--no-renames", mb, "HEAD").split()
    if not deleted:
        print(f"HEAD deletes nothing since {mb[:8]}")
        return 0
    dset = set(deleted)
    kept = [p for p in git("ls-files").splitlines() if not any(p.startswith(x) for x in a.exclude)]
    kept_names = defaultdict(int)
    for p in kept:
        kept_names[os.path.basename(p)] += 1
    pats: dict[str, str] = {}
    for d in deleted:
        pats[d] = d
        b = os.path.basename(d)
        if len(b) >= 8 and b not in GENERIC and not kept_names.get(b):
            pats[b] = d
    print(f"{len(deleted)} path(s) deleted since {mb[:8]}; {len(kept)} kept file(s) scanned")

    with tempfile.NamedTemporaryFile("w", suffix=".patterns") as pf:
        pf.write("\n".join(pats) + "\n")
        pf.flush()
        r = subprocess.run(["git", "grep", "-n", "-I", "-F", "-f", pf.name], capture_output=True, text=True)
    hits: dict[str, set[str]] = defaultdict(set)
    first_line: dict[tuple[str, str], str] = {}
    kept_set = set(kept)
    for line in r.stdout.splitlines():
        f, _, rest = line.partition(":")
        if f not in kept_set:
            continue
        ln, _, text = rest.partition(":")
        for pat, d in pats.items():
            if pat in text:
                hits[f].add(d)
                first_line.setdefault((f, d), ln)
    def prose(f: str) -> bool:
        return f.endswith((".md", ".rst", ".txt")) or f.startswith("docs/")

    code_hits = sorted(f for f in hits if not prose(f))
    prose_hits = sorted(f for f in hits if prose(f))
    print(f"\n## 1. kept files that mention a deleted path: {len(code_hits)} code/config, {len(prose_hits)} prose")
    for label, group in (("code and config", code_hits), ("prose (docs, .md)", prose_hits)):
        if not group:
            continue
        print(f"\n### {label}: {len(group)}")
        for f in group:
            ds = sorted(hits[f])
            print(f)
            for d in ds[: a.max]:
                print(f"    :{first_line[(f, d)]} -> {d}")
            if len(ds) > a.max:
                print(f"    … {len(ds) - a.max} more")

    roots = sorted({p.split("/", 1)[0] for p in kept + deleted if "/" in p})
    lit = re.compile(r'["\']((?:%s)/[A-Za-z0-9_./-]+)["\']' % "|".join(map(re.escape, roots)))
    join = re.compile(r'(?:ROOT|REPO|REPO_ROOT|_REPO_ROOT|_ROOT|parents\[\d\])\s*((?:/\s*"[^"]+"\s*)+)')
    missing = []
    for p in kept:
        if not (p.startswith("tests/") or "/tests/" in p) or not p.endswith(".py"):
            continue
        text = Path(p).read_text(errors="replace")
        cands = {m.group(1) for m in lit.finditer(text)}
        for m in join.finditer(text):
            parts = re.findall(r'"([^"]+)"', m.group(1))
            if parts and parts[0] in roots:
                cands.add("/".join(parts))
        for c in sorted(cands):
            if any(ch in c for ch in "*{<$") or Path(c).exists():
                continue
            if c in dset or any(d.startswith(c.rstrip("/") + "/") for d in deleted):
                missing.append((p, c))
    print(f"\n## 2. test files building a path the branch deleted: {len(missing)}")
    for p, c in missing:
        print(f"{p}: {c}")
    total = len(hits) + len(missing)
    print(f"\nDANGLING REFS: {total} candidate file/path pair(s)" if total else "\nDANGLING REFS: none")
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main())
