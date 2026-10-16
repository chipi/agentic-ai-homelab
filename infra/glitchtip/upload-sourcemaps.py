#!/usr/bin/env python3
"""Upload apps' source maps to GlitchTip from the mini (CI builds them, the mini uploads them).

    python3 upload-sourcemaps.py            # dry run: list what would be uploaded
    python3 upload-sourcemaps.py --apply    # download + upload + verify, record in the state file

CI runners cannot reach GlitchTip (the tailnet ACL gives tag:gha-deployer no path to the
glitchtip node), so each app's deploy job runs `sentry-cli sourcemaps inject` on its build,
deploys that build, and saves the injected .js + .js.map files as a run artifact named
`sourcemaps-<release>`, where <release> is the release string the app's SDK reports. This job
finds successful runs not yet handled, downloads the artifact with `gh`, uploads it to the local
GlitchTip (http://127.0.0.1:8090, relative chunk URLs) and records the run only once GlitchTip
has stored a bundle for every uploaded debug id. sentry-cli's own exit status is not that proof:
its upload exits 0 before the worker assembles, and `--wait` never sees GlitchTip report done.

Token: ~/glitchtip/orrery-sourcemaps.env (GLITCHTIP_SOURCEMAP_TOKEN, project:releases, org-wide).
State: ~/glitchtip/sourcemaps-state.json. Runs from com.homelab.glitchtip-sourcemaps.plist.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HOME = Path.home()
TOKEN_FILE = HOME / "glitchtip" / "orrery-sourcemaps.env"
STATE_FILE = Path(os.environ.get("SOURCEMAPS_STATE_FILE", HOME / "glitchtip" / "sourcemaps-state.json"))
GLITCHTIP = "http://127.0.0.1:8090"
ORG = "homelab"
SENTRY_CLI = ["npx", "--yes", "@sentry/cli@2.58.6"]
DOCKER = "/usr/local/bin/docker"
ARTIFACT_PREFIX = "sourcemaps-"
LOOKBACK_RUNS = 20

# One row per app: the repo + workflow that deploys it, and its GlitchTip project.
APPS = [
    {"repo": "chipi/orrery", "workflow": "deploy-prod.yml", "project": "orrery-prod"},
]

DEBUG_ID = re.compile(r"debugId=([0-9a-fA-F-]{36})")


def log(msg):
    print(f"{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())} {msg}", flush=True)


def token():
    for line in TOKEN_FILE.read_text().splitlines():
        if line.startswith("GLITCHTIP_SOURCEMAP_TOKEN="):
            return line.split("=", 1)[1].strip()
    raise SystemExit(f"no GLITCHTIP_SOURCEMAP_TOKEN in {TOKEN_FILE}")


def gh_json(*args):
    out = subprocess.run(["gh", *args], check=True, capture_output=True, text=True).stdout
    return json.loads(out)


def load_state():
    try:
        return json.loads(STATE_FILE.read_text())
    except (FileNotFoundError, ValueError):
        return {"done": {}}


def save_state(state):
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=1, sort_keys=True))
    os.replace(tmp, STATE_FILE)


def pending(app, state):
    """(run_id, artifact name, release) for successful runs with a sourcemaps artifact, not done."""
    runs = gh_json(
        "api",
        f"repos/{app['repo']}/actions/workflows/{app['workflow']}/runs"
        f"?status=success&per_page={LOOKBACK_RUNS}",
    )["workflow_runs"]
    done = state["done"].get(app["repo"], {})
    for run in runs:
        rid = str(run["id"])
        if rid in done:
            continue
        arts = gh_json("api", f"repos/{app['repo']}/actions/runs/{rid}/artifacts")["artifacts"]
        for art in arts:
            if art["name"].startswith(ARTIFACT_PREFIX) and not art.get("expired"):
                yield rid, art["name"], art["name"][len(ARTIFACT_PREFIX):]


def stored_bundles(debug_ids):
    """How many of `debug_ids` GlitchTip has assembled into a DebugSymbolBundle."""
    code = (
        "from apps.sourcecode.models import DebugSymbolBundle as B;"
        f"print(B.objects.filter(debug_id__in={sorted(debug_ids)!r}).values('debug_id').distinct().count())"
    )
    out = subprocess.run(
        [DOCKER, "exec", "glitchtip-web-1", "python", "manage.py", "shell", "-c", code],
        check=True, capture_output=True, text=True,
    ).stdout.strip().splitlines()
    return int(out[-1])


def upload(app, run_id, name, release, tok):
    work = Path(tempfile.mkdtemp(prefix="sourcemaps-"))
    try:
        subprocess.run(
            ["gh", "run", "download", run_id, "-R", app["repo"], "-n", name, "-D", str(work)],
            check=True, capture_output=True, text=True,
        )
        ids = set()
        for js in work.rglob("*.js"):
            ids.update(m.group(1).lower() for m in DEBUG_ID.finditer(js.read_text(errors="ignore")))
        if not ids:
            raise RuntimeError(f"{name}: no injected debugId in any .js (was `sourcemaps inject` run?)")
        env = {**os.environ, "SENTRY_URL": GLITCHTIP, "SENTRY_AUTH_TOKEN": tok,
               "SENTRY_ORG": ORG, "SENTRY_PROJECT": app["project"]}
        subprocess.run(
            [*SENTRY_CLI, "sourcemaps", "upload", "--release", release, str(work)],
            check=True, capture_output=True, text=True, env=env,
        )
        for _ in range(30):  # assembly runs in the worker
            if stored_bundles(ids) == len(ids):
                return len(ids)
            time.sleep(5)
        raise RuntimeError(f"{name}: GlitchTip stored {stored_bundles(ids)}/{len(ids)} bundles")
    finally:
        shutil.rmtree(work, ignore_errors=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    state = load_state()
    tok = token() if args.apply else None
    failed = 0
    for app in APPS:
        for run_id, name, release in pending(app, state):
            if not args.apply:
                log(f"would upload {app['repo']} run {run_id} artifact {name} -> {app['project']}")
                continue
            try:
                n = upload(app, run_id, name, release, tok)
            except (subprocess.CalledProcessError, RuntimeError) as exc:
                failed += 1
                detail = getattr(exc, "stderr", "") or str(exc)
                log(f"FAILED {app['repo']} run {run_id} {name}: {detail.strip()[-300:]}")
                continue
            state["done"].setdefault(app["repo"], {})[run_id] = {
                "release": release, "bundles": n, "at": int(time.time())}
            save_state(state)
            log(f"uploaded {app['repo']} run {run_id} release {release}: {n} bundle(s) stored")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
