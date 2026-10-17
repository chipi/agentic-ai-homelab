#!/usr/bin/env python3
"""Prod deploy, bracketed: preflight a sha, dispatch + approve with the operator's go, verify the box runs it.

Config: ~/.local/state/prod-deploy/<project>.json (see SKILL.md).

  deploy.py PROJECT preflight SHA            CI of that commit + every image published as sha-<7>
  deploy.py PROJECT dispatch SHA --said ".." gated: dispatch the deploy workflow, match the run
  deploy.py PROJECT approve RUN --said ".."  gated: approve the run's pending environments (allow-list)
  deploy.py PROJECT verify SHA               the box: every listed container runs sha-<7>; health URLs

Every check prints its evidence next to it; the last line is PREFLIGHT/VERIFY PASS or FAIL.
Exit: 0 pass · 1 fail/refused · 4 usage
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(os.environ.get("PROD_DEPLOY_HOME", "~/.local/state/prod-deploy")).expanduser()


def sh(cmd: list[str], check: bool = True) -> str:
    r = subprocess.run(cmd, capture_output=True, text=True)
    if check and r.returncode != 0:
        raise RuntimeError(f"{' '.join(cmd[:4])}… exit {r.returncode}: {r.stderr.strip()[:300]}")
    return r.stdout


def load(project: str) -> dict:
    p = ROOT / f"{project}.json"
    if not p.is_file():
        sys.exit(f"no config {p} (see SKILL.md)")
    return json.loads(p.read_text())


def full_sha(c: dict, sha: str) -> str:
    sha = sha.removeprefix("sha-")
    if not re.fullmatch(r"[0-9a-f]{7,40}", sha):
        raise SystemExit(f"not a sha: {sha}")
    return sh(["gh", "api", f"repos/{c['repo']}/commits/{sha}", "-q", ".sha"]).strip()


def ghcr_code(image: str, tag: str) -> int:
    owner_pkg = image.removeprefix("ghcr.io/")
    tok = json.load(urllib.request.urlopen(f"https://ghcr.io/token?scope=repository:{owner_pkg}:pull", timeout=20))["token"]
    req = urllib.request.Request(f"https://ghcr.io/v2/{owner_pkg}/manifests/{tag}", method="HEAD", headers={
        "Authorization": f"Bearer {tok}",
        "Accept": "application/vnd.oci.image.index.v1+json,application/vnd.docker.distribution.manifest.v2+json"})
    try:
        return urllib.request.urlopen(req, timeout=20).status
    except urllib.error.HTTPError as e:
        return e.code


def cmd_preflight(c: dict, a: argparse.Namespace) -> int:
    full = full_sha(c, a.sha)
    tag = f"sha-{full[:7]}"
    fails = []
    print(f"commit {full} → image tag {tag}")
    runs = json.loads(sh(["gh", "api", f"repos/{c['repo']}/actions/runs?head_sha={full}&per_page=100",
                          "-q", "[.workflow_runs[] | {name, status, conclusion, event}]"]))
    latest: dict[str, dict] = {}
    for r in runs:  # newest first: keep the first (latest) run per workflow
        latest.setdefault(r["name"], r)
    for name in c["required_ci"]:
        r = latest.get(name)
        state = f"{r['status']} {r['conclusion']}" if r else "NOT RUN"
        ok = bool(r) and r["conclusion"] == "success"
        print(f"  {'PASS' if ok else 'FAIL'} CI {name}: {state}")
        if not ok:
            fails.append(f"CI {name}: {state}")
    others = sorted(set(latest) - set(c["required_ci"]))
    for name in others:
        r = latest[name]
        print(f"  info CI {name}: {r['status']} {r['conclusion']}")
    for image in c["images"]:
        code = ghcr_code(image, tag)
        print(f"  {'PASS' if code == 200 else 'FAIL'} {image}:{tag} HTTP {code}")
        if code != 200:
            fails.append(f"{image}:{tag} not published (HTTP {code})")
    inputs = " ".join(f"-f {k}={v}" for k, v in {**c["dispatch_inputs"], c["sha_input"]: full[:7]}.items())
    print(f"\ndispatch (needs the operator's go): gh workflow run {c['workflow']} -R {c['repo']} --ref main {inputs}")
    print("PREFLIGHT " + ("FAIL: " + "; ".join(fails) if fails else "PASS"))
    return 1 if fails else 0


def cmd_dispatch(c: dict, a: argparse.Namespace) -> int:
    if cmd_preflight(c, a) != 0 and not a.force_preflight:
        print("REFUSED: preflight failed")
        return 1
    full = full_sha(c, a.sha)
    cmd = ["gh", "workflow", "run", c["workflow"], "-R", c["repo"], "--ref", "main"]
    for k, v in {**c["dispatch_inputs"], c["sha_input"]: full[:7]}.items():
        cmd += ["-f", f"{k}={v}"]
    since = dt.datetime.now(dt.timezone.utc) - dt.timedelta(seconds=5)
    sh(cmd)
    me = sh(["gh", "api", "user", "-q", ".login"]).strip()
    for _ in range(12):
        time.sleep(10)
        runs = json.loads(sh(["gh", "api", f"repos/{c['repo']}/actions/workflows/{c['workflow']}/runs?event=workflow_dispatch&per_page=10",
                              "-q", "[.workflow_runs[] | {id, created_at, actor: .actor.login}]"]))
        mine = [r for r in runs if r["actor"] == me
                and dt.datetime.fromisoformat(r["created_at"].replace("Z", "+00:00")) >= since]
        if len(mine) == 1:
            print(f"dispatched ({a.said!r}): https://github.com/{c['repo']}/actions/runs/{mine[0]['id']}")
            return 0
        if len(mine) > 1:
            print(f"AMBIGUOUS: {len(mine)} runs by {me} since dispatch: {[r['id'] for r in mine]} — approve by id yourself")
            return 1
    print("no run appeared within 2 min")
    return 1


def cmd_approve(c: dict, a: argparse.Namespace) -> int:
    pend = json.loads(sh(["gh", "api", f"repos/{c['repo']}/actions/runs/{a.run}/pending_deployments"]) or "[]")
    envs = [p["environment"] for p in pend]
    if not envs:
        print(f"run {a.run}: nothing waiting for approval")
        return 0
    bad = [e["name"] for e in envs if e["name"] not in c["approvable_environments"]]
    if bad:
        print(f"REFUSED: run waits on {bad}, not in approvable_environments {c['approvable_environments']}")
        return 1
    args = ["gh", "api", "-X", "POST", f"repos/{c['repo']}/actions/runs/{a.run}/pending_deployments",
            "-f", "state=approved", "-f", f"comment=prod-deploy: {a.said}"]
    for e in envs:
        args += ["-F", f"environment_ids[]={e['id']}"]
    sh(args)
    got = json.loads(sh(["gh", "api", f"repos/{c['repo']}/actions/runs/{a.run}/approvals", "-q", "[.[] | .state]"]))
    print(f"approved {[e['name'] for e in envs]} for run {a.run}; approvals now: {got}")
    return 0 if "approved" in got else 1


def cmd_verify(c: dict, a: argparse.Namespace) -> int:
    full = full_sha(c, a.sha)
    tag = f"sha-{full[:7]}"
    fails = []
    ssh = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15"]
    if c.get("ssh_key"):
        ssh += ["-i", os.path.expanduser(c["ssh_key"]), "-o", "IdentitiesOnly=yes"]
    ps = sh(ssh + [c["ssh"], "docker ps --format '{{.Names}} {{.Image}} {{.Status}}'"])
    rows = [ln.split(" ", 2) for ln in ps.splitlines() if ln.strip()]
    rx = re.compile(c["sha_containers_regex"])
    matched = [r for r in rows if rx.search(r[0])]
    if not matched:
        fails.append(f"no running container matches {c['sha_containers_regex']}")
    for name, image, status in matched:
        ok = image.endswith(f":{tag}")
        print(f"  {'PASS' if ok else 'FAIL'} {name}: {image} ({status})")
        if not ok:
            fails.append(f"{name} runs {image}")
    for need in c.get("must_run", []):
        if not any(re.fullmatch(need, r[0]) for r in rows):
            print(f"  FAIL {need}: not running")
            fails.append(f"{need} not running")
    for h in c.get("health", []):
        try:
            code = urllib.request.urlopen(urllib.request.Request(h["url"], headers=h.get("headers", {})), timeout=30).status
        except urllib.error.HTTPError as e:
            code = e.code
        except OSError as e:
            code = f"error {e}"
        ok = code == h.get("expect", 200)
        print(f"  {'PASS' if ok else 'FAIL'} {h['url']}: {code} (expect {h.get('expect', 200)})")
        if not ok:
            fails.append(f"{h['url']} → {code}")
    print("\nNot checked here (do it with the tools named in SKILL.md): smokes, GlitchTip/Langfuse since the deploy, logs.")
    print("VERIFY " + ("FAIL: " + "; ".join(fails) if fails else "PASS"))
    return 1 if fails else 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("project")
    sub = p.add_subparsers(dest="cmd", required=True)
    pf = sub.add_parser("preflight"); pf.add_argument("sha")
    d = sub.add_parser("dispatch"); d.add_argument("sha"); d.add_argument("--said", required=True); d.add_argument("--force-preflight", action="store_true")
    ap = sub.add_parser("approve"); ap.add_argument("run"); ap.add_argument("--said", required=True)
    v = sub.add_parser("verify"); v.add_argument("sha")
    a = p.parse_args()
    c = load(a.project)
    try:
        return {"preflight": cmd_preflight, "dispatch": cmd_dispatch, "approve": cmd_approve, "verify": cmd_verify}[a.cmd](c, a)
    except RuntimeError as e:
        print(f"ERROR: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
