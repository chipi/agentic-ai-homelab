#!/usr/bin/env python3
"""Watch every GitHub check on one commit until it settles, one line per event.

    ci_watch.py [SHA|HEAD] [--repo OWNER/NAME] [--timeout-min N] [--interval S]

Built to run under the Monitor tool: each stdout line is an event, and the script exits on its
own. Read-only: GitHub API reads through an already-authenticated `gh`.

- A short SHA is resolved to the full one first. GitHub's check-runs endpoint answers a short
  SHA with 422, and a monitor that swallowed the error saw "no checks" forever.
- Each check prints once, when it completes: `name: conclusion`.
- On the first failure, the tail of that job's log follows, so the cause is in the event.
- `cancelled` is never a pass or a fail: it prints `NOT RUN`, naming the newer commit on the
  branch that superseded it when there is one.
- The last line is the verdict, classified like podcast_scraper's ci-gate.yml: RED on
  failure/timed_out; INCOMPLETE on anything that did not run (cancelled, stale, still running at
  the deadline); else GREEN.

Exit codes: 0 GREEN, 1 RED, 2 INCOMPLETE, 3 deadline reached (re-arm), 4 usage/lookup error.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from typing import NoReturn

HARD_FAIL = {"failure", "timed_out"}
GOOD = {"success", "skipped", "neutral"}
ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


def say(line: str) -> None:
    print(line, flush=True)


def gh_json(path: str) -> object:
    out = subprocess.run(["gh", "api", path], capture_output=True, text=True)
    if out.returncode != 0:
        raise RuntimeError(f"gh api {path}: {out.stderr.strip() or out.stdout.strip()}")
    text = out.stdout.strip()
    return json.loads(text) if text else {}


def gh_items(path: str, jq: str) -> list[dict]:
    """Every item ``jq`` selects across all pages: one compact JSON object per line."""
    out = subprocess.run(
        ["gh", "api", "--paginate", path, "--jq", f"{jq} | tojson"], capture_output=True, text=True
    )
    if out.returncode != 0:
        raise RuntimeError(f"gh api {path}: {out.stderr.strip() or out.stdout.strip()}")
    return [json.loads(line) for line in out.stdout.splitlines() if line.strip()]


def die(msg: str) -> NoReturn:
    say(f"ci-watch: {msg}")
    raise SystemExit(4)


def default_repo() -> str:
    out = subprocess.run(
        ["gh", "repo", "view", "--json", "nameWithOwner", "--jq", ".nameWithOwner"],
        capture_output=True,
        text=True,
    )
    if out.returncode != 0 or not out.stdout.strip():
        die("no --repo and the current directory is not a gh repo")
    return out.stdout.strip()


def resolve_sha(repo: str, ref: str) -> str:
    if re.fullmatch(r"[0-9a-f]{40}", ref):
        return ref
    local = subprocess.run(["git", "rev-parse", "--verify", f"{ref}^{{commit}}"], capture_output=True, text=True)
    if local.returncode == 0 and re.fullmatch(r"[0-9a-f]{40}", local.stdout.strip()):
        full = local.stdout.strip()
        # A local commit GitHub has never seen has no checks: say so instead of waiting.
        try:
            gh_json(f"repos/{repo}/commits/{full}")
        except RuntimeError as exc:
            die(f"{full[:9]} is not on {repo} (not pushed?): {exc}")
        return full
    try:
        data = gh_json(f"repos/{repo}/commits/{ref}")
    except RuntimeError as exc:
        die(f"cannot resolve {ref!r} on {repo}: {exc}")
    return str(data["sha"])  # type: ignore[index]


def check_runs(repo: str, sha: str) -> list[dict]:
    return gh_items(f"repos/{repo}/commits/{sha}/check-runs?per_page=100", ".check_runs[]")


def workflow_runs(repo: str, sha: str) -> list[dict]:
    return gh_items(f"repos/{repo}/actions/runs?head_sha={sha}&per_page=100", ".workflow_runs[]")


def superseded_by(repo: str, sha: str, branch: str | None) -> tuple[str, str]:
    """(the commit right after ``sha`` on ``branch``, the branch head), or ("", "") if none."""
    if not branch:
        return "", ""
    try:
        cmp = gh_json(f"repos/{repo}/compare/{sha}...{branch}")
    except RuntimeError:
        return "", ""
    commits = cmp.get("commits") or []  # type: ignore[union-attr]
    if not commits:
        return "", ""
    return str(commits[0]["sha"]), str(commits[-1]["sha"])


def log_tail(repo: str, job_id: int, lines: int = 25) -> list[str]:
    out = subprocess.run(
        ["gh", "api", "--allow-escape-sequences", f"repos/{repo}/actions/jobs/{job_id}/logs"],
        capture_output=True,
        text=True,
    )
    if out.returncode != 0:
        return [f"(log not available yet: {out.stderr.strip()[:200]})"]
    text = ANSI.sub("", out.stdout)
    keep = [l for l in text.splitlines() if l.strip()]
    # Everything after the runner's own cleanup is git/credential housekeeping, never the cause.
    cut = next((i for i, l in enumerate(keep) if "Post job cleanup." in l), len(keep))
    keep = keep[:cut]
    errors = [l for l in keep if re.search(r"##\[error\]|FAIL|Error|error:|AssertionError|Traceback", l)]
    tail = keep[-lines:]
    # The error lines first (they can sit far above the teardown noise at the end), then the tail.
    head = [l for l in errors[-15:] if l not in tail]
    return head + (["…"] if head else []) + tail


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("ref", nargs="?", default="HEAD")
    ap.add_argument("--repo")
    ap.add_argument("--timeout-min", type=float, default=25.0, help="stop and say re-arm (Monitor caps at 30)")
    ap.add_argument("--interval", type=float, default=45.0)
    args = ap.parse_args(argv)

    repo = args.repo or default_repo()
    sha = resolve_sha(repo, args.ref)
    say(f"watching {repo}@{sha[:9]} ({sha})")

    deadline = time.monotonic() + args.timeout_min * 60
    reported: dict[int, str] = {}
    showed_failure = False
    branch: str | None = None
    while True:
        try:
            runs = check_runs(repo, sha)
            wruns = workflow_runs(repo, sha)
        except RuntimeError as exc:
            say(f"(transient: {exc}; retrying)")
            runs, wruns = [], []
        if branch is None and wruns:
            branch = wruns[0].get("head_branch")
        for r in sorted(runs, key=lambda r: r.get("completed_at") or ""):
            if r.get("status") != "completed" or r["id"] in reported:
                continue
            c = r.get("conclusion") or "none"
            reported[r["id"]] = c
            # One event per line: a matrix name can carry a newline (``INSTALL_EXTRAS=ml\nPRELOAD…``).
            r["name"] = " ".join(str(r.get("name", "")).split())
            if c == "cancelled":
                nxt, head = superseded_by(repo, sha, branch)
                why = (
                    f"cancelled; the next commit on {branch} is {nxt[:9]}"
                    + (f" (branch now at {head[:9]})" if head != nxt else "")
                    if nxt
                    else "cancelled, with no newer commit on the branch"
                )
                say(f"{r['name']}: NOT RUN — {why}")
            else:
                say(f"{r['name']}: {c}")
            if c in HARD_FAIL and not showed_failure:
                showed_failure = True
                say(f"--- first failure: {r['name']} — log tail (job {r['id']}) ---")
                for line in log_tail(repo, int(r["id"])):
                    say(f"  {line}")
                say("--- end log tail ---")
        pending = [r["name"] for r in runs if r.get("status") != "completed"]
        wf_pending = [w["name"] for w in wruns if w.get("status") != "completed"]
        settled = runs and not pending and not wf_pending
        if settled or time.monotonic() >= deadline:
            break
        time.sleep(args.interval)

    conclusions = list(reported.values())
    failed = [c for c in conclusions if c in HARD_FAIL]
    not_run = [c for c in conclusions if c not in HARD_FAIL and c not in GOOD]
    counts = ", ".join(f"{c} {conclusions.count(c)}" for c in sorted(set(conclusions)))
    if not settled:
        still = sorted(set(pending + wf_pending)) or ["(no checks reported yet)"]
        say(f"VERDICT INCOMPLETE — deadline after {args.timeout_min:g} min, still running: "
            f"{', '.join(still)}; {counts or 'nothing completed'}. RE-ARM ci-watch.")
        return 3
    if failed:
        say(f"VERDICT RED — {counts}")
        return 1
    if not_run:
        say(f"VERDICT INCOMPLETE — {counts} (cancelled/stale checks did not run; they are not a pass)")
        return 2
    say(f"VERDICT GREEN — {counts}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
