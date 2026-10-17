#!/usr/bin/env python3
"""Run the same make targets on a branch and on its trunk base; report which failures are the branch's.

    baseline_diff.py --base origin/main type test-unit     # from the branch's repo root
    baseline_diff.py --remove                              # drop the base worktree

The base tree is a detached worktree at merge-base(--base, HEAD), so the comparison is against
what the branch started from, never a stash. Each tree runs with PYTHONPATH=<tree>/src when src/
exists, so its own code wins over an editable install shared between worktrees. Every target runs
in both trees even after a failure. Logs go to files; one line per finished run on stdout.

Exit 0: no branch-caused failure. 1: a target fails only on the branch, or fails in both trees
with error lines the base does not have. 2: usage/git error.
A target failing in BOTH trees with the same errors is FAIL BOTH: not the branch's, not a pass.
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ERR = re.compile(r"error|Error|ERROR|FAILED|FAIL\b|Traceback|failed|\bE\s{2,}")
# Numbers differ between trees for reasons that are not new errors: timings, file counts
# ("checked 2356 source files" when the branch deletes files), line numbers shifted by edits.
NOISE = [
    (re.compile(r"0x[0-9a-fA-F]+"), "<addr>"),
    (re.compile(r"\d+"), "<n>"),
]


def git(*args: str, cwd: Path) -> str:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True).stdout.strip()


def base_dir(root: Path) -> Path:
    return Path(tempfile.gettempdir()) / f"baseline-diff-{root.name}"


def ensure_base(root: Path, rev: str) -> Path:
    d = base_dir(root)
    if d.exists():
        try:
            if git("rev-parse", "HEAD", cwd=d) == rev:
                return d
        except subprocess.CalledProcessError:
            pass
        subprocess.run(["git", "worktree", "remove", "--force", str(d)], cwd=root, capture_output=True)
    git("worktree", "add", "--detach", "--quiet", str(d), rev, cwd=root)
    venv = root / ".venv"
    if venv.exists() and not (d / ".venv").exists():
        (d / ".venv").symlink_to(venv.resolve())
    return d


def normalize(line: str, tree: Path) -> str:
    line = line.replace(str(tree), "<tree>")
    for pat, rep in NOISE:
        line = pat.sub(rep, line)
    return line.strip()


def run(tree: Path, target: str, log: Path, extra_env: dict[str, str]) -> tuple[int, float]:
    env = dict(os.environ, **extra_env)
    if (tree / "src").is_dir():
        env["PYTHONPATH"] = str(tree / "src") + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    start = time.time()
    with log.open("w") as fh:
        rc = subprocess.run(["make", target], cwd=tree, stdout=fh, stderr=subprocess.STDOUT, env=env).returncode
    return rc, time.time() - start


def err_lines(log: Path, tree: Path) -> dict[str, str]:
    """normalized -> first original line, for every line that looks like an error."""
    out: dict[str, str] = {}
    for line in log.read_text(errors="replace").splitlines():
        if ERR.search(line):
            out.setdefault(normalize(line, tree), line.strip())
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("targets", nargs="*", help="make targets, run in order")
    ap.add_argument("--base", default="origin/main", help="trunk ref; the base tree is merge-base(BASE, HEAD)")
    ap.add_argument("--logs", help="log dir (default: a new temp dir)")
    ap.add_argument("--env", action="append", default=[], metavar="K=V", help="extra env for both trees")
    ap.add_argument("--max-lines", type=int, default=40, help="branch-only error lines shown per target")
    ap.add_argument("--remove", action="store_true", help="remove the base worktree and exit")
    a = ap.parse_args()

    try:
        root = Path(git("rev-parse", "--show-toplevel", cwd=Path.cwd()))
    except subprocess.CalledProcessError:
        print("not inside a git repository", file=sys.stderr)
        return 2
    if a.remove:
        subprocess.run(["git", "worktree", "remove", "--force", str(base_dir(root))], cwd=root, capture_output=True)
        print(f"removed {base_dir(root)}")
        return 0
    if not a.targets:
        ap.error("give at least one make target")
    try:
        mb = git("merge-base", a.base, "HEAD", cwd=root)
    except subprocess.CalledProcessError:
        print(f"no merge base between {a.base} and HEAD", file=sys.stderr)
        return 2
    base = ensure_base(root, mb)
    extra = dict(kv.split("=", 1) for kv in a.env)
    logs = Path(a.logs) if a.logs else Path(tempfile.mkdtemp(prefix="baseline-diff-logs-"))
    logs.mkdir(parents=True, exist_ok=True)
    head = git("rev-parse", "--short", "HEAD", cwd=root)
    print(f"branch {head} at {root}", flush=True)
    print(f"base   {mb[:8]} at {base} (merge-base of {a.base} and HEAD)", flush=True)
    print(f"logs   {logs}", flush=True)

    rows = []
    for t in a.targets:
        res = {}
        for side, tree in (("base", base), ("branch", root)):
            log = logs / f"{side}-{t}.log"
            print(f"run    {side:6} make {t}  (tail -f {log})", flush=True)
            rc, secs = run(tree, t, log, extra)
            res[side] = (rc, log, tree)
            print(f"done   {side:6} make {t}: {'PASS' if rc == 0 else f'FAIL exit {rc}'} in {secs:.0f}s", flush=True)
        rows.append((t, res))

    print("\n| target | base | branch | verdict |\n| --- | --- | --- | --- |")
    branch_only = 0
    details = []
    for t, res in rows:
        b, h = res["base"][0], res["branch"][0]
        if h == 0:
            verdict = "PASS" if b == 0 else "FIXED ON BRANCH"
        elif b == 0:
            verdict, branch_only = "FAIL BRANCH ONLY", branch_only + 1
        else:
            verdict = "FAIL BOTH"
        new = []
        if h != 0:
            seen = err_lines(res["base"][1], res["base"][2])
            new = [orig for norm, orig in err_lines(res["branch"][1], root).items() if norm not in seen]
            if verdict == "FAIL BOTH" and new:
                verdict, branch_only = "FAIL BOTH + NEW ON BRANCH", branch_only + 1
            details.append((t, verdict, new))
        print(f"| {t} | {'PASS' if b == 0 else 'FAIL'} | {'PASS' if h == 0 else 'FAIL'} | {verdict} |")
    for t, verdict, new in details:
        print(f"\n## {t} ({verdict}): {len(new)} error line(s) only on the branch")
        for l in new[: a.max_lines]:
            print(f"  {l}")
        if len(new) > a.max_lines:
            print(f"  … {len(new) - a.max_lines} more in {logs}/branch-{t}.log")
        if verdict == "FAIL BOTH" and not new:
            print("  same error lines in both trees: the branch did not add this failure, and it is still not a pass")
    print(f"\nBASELINE DIFF: {'FAIL' if branch_only else 'NO BRANCH-ONLY FAILURES'} ({branch_only} branch-only)")
    return 1 if branch_only else 0


if __name__ == "__main__":
    sys.exit(main())
