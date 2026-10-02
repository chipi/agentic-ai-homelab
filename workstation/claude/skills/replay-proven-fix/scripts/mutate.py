#!/usr/bin/env python3
"""Mutation check for a replay or test: break the fix on purpose, run the check, and
confirm it FAILS. Then always restore the file, and verify the restore by checksum.
Language-agnostic: the mutation is a literal text replacement, the check is any command.

  mutate.py --file src/x.py --find 'if a > b:' --replace 'if True:' \
            [--precheck 'python3 -m py_compile src/x.py'] -- python3 eval_x_replay.py

Exit 0 = mutant KILLED (the check failed, as it should); exit 1 = mutant SURVIVED (the
check passed with the fix broken, so it proves nothing); exit 2 = setup error.
Always read WHY the check failed in the printed tail: a mutant can "fail" for the
wrong reason, e.g. a syntax error the mutation itself introduced. --precheck runs right
after mutating; if it fails, the mutation is invalid and nothing is concluded.
"""
import argparse
import hashlib
import shutil
import subprocess
import sys
import tempfile


def sha(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def run(cmd, shell):
    r = subprocess.run(cmd, shell=shell, capture_output=True, text=True)
    return r.returncode, (r.stdout + r.stderr).strip().splitlines()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", required=True)
    ap.add_argument("--find", required=True, help="literal text; must occur exactly --count times")
    ap.add_argument("--replace", required=True)
    ap.add_argument("--count", type=int, default=1)
    ap.add_argument("--precheck", help="shell command that must PASS on the mutated file (e.g. a compile)")
    ap.add_argument("--tail", type=int, default=8)
    ap.add_argument("cmd", nargs=argparse.REMAINDER, help="-- command to run against the mutant")
    a = ap.parse_args()
    cmd = a.cmd[1:] if a.cmd[:1] == ["--"] else a.cmd
    if not cmd:
        sys.exit("give the check command after --")
    text = open(a.file).read()
    n = text.count(a.find)
    if n != a.count:
        print(f"SETUP ERROR: --find occurs {n} times in {a.file}, expected {a.count}")
        return 2
    original = sha(a.file)
    backup = tempfile.NamedTemporaryFile(delete=False, suffix=".bak").name
    shutil.copy2(a.file, backup)
    try:
        open(a.file, "w").write(text.replace(a.find, a.replace))
        if a.precheck:
            code, out = run(a.precheck, shell=True)
            if code != 0:
                print("INVALID MUTANT: --precheck failed on the mutated file, nothing concluded:")
                print("\n".join("  " + l for l in out[-a.tail:]))
                return 2
        code, out = run(cmd, shell=False)
    finally:
        shutil.copy2(backup, a.file)
        restored = sha(a.file) == original
    print(f"restore verified (sha256 matches original): {restored}")
    if not restored:
        print(f"RESTORE FAILED — original kept at {backup}")
        return 2
    verdict = "KILLED" if code != 0 else "SURVIVED"
    print(f"MUTANT {verdict}: check exited {code}. Last lines (read WHY it failed):")
    print("\n".join("  " + l for l in out[-a.tail:]))
    return 0 if code != 0 else 1


if __name__ == "__main__":
    sys.exit(main())
