#!/usr/bin/env python3
"""Run one `run:` step of a GitHub workflow or composite action locally, the way the runner would.

  run_step.py FILE --step NAME|ID|INDEX [--job JOB] [--env K=V ...] [--sub 'EXPR=VALUE' ...]
              [--case LABEL --expect-exit N] [--keep]

- The step's script runs under `bash --noprofile --norc -eo pipefail` (GitHub's default shell),
  never zsh, with a fresh HOME, RUNNER_TEMP, GITHUB_ENV, GITHUB_OUTPUT and GITHUB_STEP_SUMMARY.
- `${{ … }}` in the script or in the step's env must be supplied with --sub ('inputs.x=value');
  an unresolved expression refuses to run rather than run with an empty string.
- Prints exit code, stdout/stderr, and what the step wrote to GITHUB_ENV / GITHUB_OUTPUT.
- --expect-exit makes it a test case: exit 0 only if the step exited as expected. Run at least one
  case that must fail (a wrong key, an empty input); a guard proven only on the happy path is not
  proven.

Exit: 0 ran as expected · 1 unexpected exit · 4 usage/extraction error
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.exit("PyYAML missing for this python3 (macOS /usr/bin/python3 has none): use the pyenv python3 or a venv")

EXPR = re.compile(r"\$\{\{\s*(.+?)\s*\}\}")


def find_step(doc: dict, step: str, job: str | None) -> dict:
    if "runs" in doc:  # composite action
        steps = doc["runs"].get("steps", [])
    else:
        jobs = doc.get("jobs", {})
        if job is None:
            if len(jobs) != 1:
                raise SystemExit(f"--job required: {list(jobs)}")
            job = next(iter(jobs))
        steps = jobs[job].get("steps", [])
    runs = [s for s in steps if "run" in s]
    for i, s in enumerate(steps):
        if "run" in s and (s.get("id") == step or s.get("name") == step or str(i) == step):
            return s
    names = [s.get("id") or s.get("name") for s in runs]
    raise SystemExit(f"no run-step '{step}'. run-steps: {names}")


def substitute(text: str, subs: dict[str, str]) -> tuple[str, list[str]]:
    missing: list[str] = []

    def rep(m: re.Match[str]) -> str:
        key = m.group(1)
        if key in subs:
            return subs[key]
        missing.append(key)
        return m.group(0)

    return EXPR.sub(rep, text), missing


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("file")
    p.add_argument("--step", required=True)
    p.add_argument("--job")
    p.add_argument("--env", action="append", default=[])
    p.add_argument("--sub", action="append", default=[])
    p.add_argument("--case", default="case")
    p.add_argument("--expect-exit", type=int)
    p.add_argument("--keep", action="store_true", help="keep the temp HOME (inspect files the step wrote)")
    a = p.parse_args()

    doc = yaml.safe_load(Path(a.file).read_text())
    s = find_step(doc, a.step, a.job)
    subs = dict(x.split("=", 1) for x in a.sub)
    script, miss1 = substitute(s["run"], subs)
    step_env = {}
    miss2: list[str] = []
    for k, v in (s.get("env") or {}).items():
        val, m = substitute(str(v), subs)
        step_env[k] = val
        miss2 += m
    if miss1 or miss2:
        print("REFUSED: unresolved expressions (pass --sub 'EXPR=VALUE'):")
        for m in sorted(set(miss1 + miss2)):
            print(f"  ${{{{ {m} }}}}")
        return 4

    tmp = Path(tempfile.mkdtemp(prefix="ci-step-"))
    home, rt = tmp / "home", tmp / "runner_temp"
    home.mkdir()
    rt.mkdir()
    files = {n: tmp / n.lower() for n in ("GITHUB_ENV", "GITHUB_OUTPUT", "GITHUB_STEP_SUMMARY")}
    for f in files.values():
        f.touch()
    env = {"PATH": os.environ["PATH"], "HOME": str(home), "RUNNER_TEMP": str(rt), "CI": "true",
           "GITHUB_ACTIONS": "true", **{k: str(v) for k, v in files.items()}, **step_env}
    env.update(dict(x.split("=", 1) for x in a.env))
    script_path = tmp / "step.sh"
    script_path.write_text(script)
    r = subprocess.run(["bash", "--noprofile", "--norc", "-eo", "pipefail", str(script_path)],
                       env=env, cwd=os.getcwd(), capture_output=True, text=True)
    print(f"== {a.case}: step '{s.get('name') or s.get('id')}' exit {r.returncode}")
    if r.stdout.strip():
        print("-- stdout\n" + r.stdout.rstrip())
    if r.stderr.strip():
        print("-- stderr\n" + r.stderr.rstrip())
    for n, f in files.items():
        if f.read_text().strip():
            print(f"-- {n}\n" + f.read_text().rstrip())
    if a.keep:
        print(f"-- kept: {tmp} (HOME={home})")
    else:
        subprocess.run(["rm", "-rf", str(tmp)])
    if a.expect_exit is None:
        return 0 if r.returncode == 0 else 1
    ok = r.returncode == a.expect_exit
    print(f"{'PASS' if ok else 'FAIL'}: {a.case} expected exit {a.expect_exit}, got {r.returncode}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
