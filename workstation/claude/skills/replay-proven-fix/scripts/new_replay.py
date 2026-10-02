#!/usr/bin/env python3
"""Scaffold a replay eval for a Python project: baseline (code at BASE_REV, loaded from
git) vs fix (working tree), over a frozen corpus, with the three checks every replay
needs: the baseline reproduces history, explicit pass criteria, exit 1 on failure.

  new_replay.py --out path/eval_<thing>_replay.py --module path/to/module.py \
                --base-rev <sha> --corpus path/to/corpus.json --what "one line: what changed"

The generated file runs immediately and exits 2 until you fill the three TODOs.
"""
import argparse
import os
import subprocess
import sys

TEMPLATE = '''"""Replay eval: {what}

Input: {corpus_rel} (frozen on <date>; how it was captured: <command / query>).
Each item is replayed through the REAL {module_name} of
  baseline  {module_rel} at BASE_REV ({base_rev}), loaded from git
  fix       the working-tree {module_rel}
Pass:
  - the baseline reproduces the recorded history for every item (the replay is faithful)
  - <explicit criterion 1 — e.g. "the 6 disk events become 1 alert each">
  - <explicit criterion 2 — e.g. "nothing that was not part of the bug changes">

  python3 {out_name}     # exit 0 = PASS, 1 = FAIL, 2 = scaffold not filled in
"""
import importlib.util
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = subprocess.run(["git", "-C", HERE, "rev-parse", "--show-toplevel"],
                      capture_output=True, text=True, check=True).stdout.strip()
MODULE = os.path.join(REPO, {module_rel!r})
CORPUS = os.path.join(REPO, {corpus_rel!r})
BASE_REV = {base_rev!r}   # the commit BEFORE the fix — never re-implement the old code by hand


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.path.insert(0, os.path.dirname(path))   # sibling imports resolve against the working tree
    spec.loader.exec_module(mod)
    return mod


def _baseline():
    src = subprocess.run(["git", "-C", REPO, "show", f"{{BASE_REV}}:{module_rel}"],
                         capture_output=True, text=True, check=True).stdout
    tmp = tempfile.NamedTemporaryFile("w", suffix=".py", delete=False,
                                      dir=os.path.dirname(MODULE), prefix="_replay_base_")
    tmp.write(src)
    tmp.close()
    try:
        return _load(tmp.name, "replay_baseline")
    finally:
        os.unlink(tmp.name)


def replay(mod, item):
    """Run ONE corpus item through `mod` and return a comparable outcome.
    Stub every external write (GitHub, DB, network) so nothing is ever sent; serve reads
    from the frozen corpus so the replay is reproducible after the world moves on."""
    raise NotImplementedError("TODO 1: call the real function under test and return its outcome")


def recorded(item):
    """What actually happened in production for this item (from the corpus)."""
    raise NotImplementedError("TODO 2: return the recorded outcome, for the faithfulness check")


def check(item, before, after):
    """Return None if this item passes, else a one-line failure."""
    raise NotImplementedError("TODO 3: the explicit pass criterion per item")


def main():
    corpus = json.load(open(CORPUS))
    items = corpus if isinstance(corpus, list) else corpus.get("items", [])
    if not items:
        # a replay over nothing "passes" everything — never let that read as PASS
        print(f"FAIL: no items in {{CORPUS}} (expected a JSON list, or an object with an 'items' list); adapt the loader")
        return 1
    base, fix = _baseline(), _load(MODULE, "replay_fix")
    fails, changed, faithful = [], [], 0
    try:
        for item in items:
            b, f = replay(base, item), replay(fix, item)
            faithful += b == recorded(item)
            if b != f:
                changed.append((item, b, f))
            err = check(item, b, f)
            if err:
                fails.append(err)
    except NotImplementedError as e:
        print(f"SCAFFOLD: {{e}}")
        return 2
    print(f"{{len(items)}} items | baseline reproduces history: {{faithful}}/{{len(items)}} | changed: {{len(changed)}}")
    if faithful != len(items):
        fails.append("baseline does not reproduce history — the replay is not faithful")
    for item, b, f in changed[:30]:          # READ these: totals can pass while cases are wrong
        print(f"  {{b}} -> {{f}}   {{str(item)[:90]}}")
    print("PASS" if not fails else "FAIL:\\n  " + "\\n  ".join(fails[:30]))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
'''


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--module", required=True, help="path of the module under test")
    ap.add_argument("--base-rev", required=True, help="commit before the fix")
    ap.add_argument("--corpus", required=True, help="frozen evidence (JSON)")
    ap.add_argument("--what", required=True)
    a = ap.parse_args()
    repo = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, check=True).stdout.strip()
    subprocess.run(["git", "rev-parse", "--verify", "--quiet", a.base_rev + "^{commit}"], check=True, capture_output=True)
    if os.path.exists(a.out):
        sys.exit(f"{a.out} exists — refusing to overwrite")
    rel = lambda p: os.path.relpath(os.path.abspath(p), repo)
    src = TEMPLATE.format(what=a.what, corpus_rel=rel(a.corpus), module_rel=rel(a.module),
                          module_name=os.path.basename(a.module), base_rev=a.base_rev,
                          out_name=os.path.basename(a.out))
    open(a.out, "w").write(src)
    os.chmod(a.out, 0o755)
    print(f"wrote {a.out} — fill TODO 1-3, then run it; it exits 2 until you do")


if __name__ == "__main__":
    main()
