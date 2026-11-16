#!/usr/bin/env python3
"""Dev observability for the branch you are working on, read-only: GlitchTip dev
projects, VictoriaLogs, VictoriaTraces. Runs on the workstation over the tailnet (no ssh),
inside a project's git worktree. Never writes, never resolves, never files an issue.

  o11y_dev.py                                   # project + branch from git, window since the branch's first commit
  o11y_dev.py --branch tech-debt/0.9.9 --since 14d --project orrery

Ends with one line (exit 0, or 2 when a source could not be checked):
  O11Y-DEV <project> <branch>: errors=N (branch-filtered|not branch-filtered), error-logs=M, failed-traces=K
"""
import argparse
import collections
import datetime as dt
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request

GLITCHTIP = "https://glitchtip.tail6d0ed4.ts.net"
VLOGS = "https://vlogs.tail6d0ed4.ts.net"
VTRACES = "https://vtraces.tail6d0ed4.ts.net"
TOKEN_FILE = "~/.config/glitchtip/dev-agents-read.env"
CONTRACT_DOC = "docs/recipes/o11y-dev.md in chipi/agentic-ai-homelab"

# One place for what each project sends. glitchtip = dev project slugs; branch_tag = events carry
# the `worktree` tag; logs = a VictoriaLogs filter (environment:dev is always added);
# logs_branch = logs carry a `worktree` label; traces = service names (deployment.environment=dev
# is filtered on the trace's resource). None = no dev telemetry yet.
PROJECTS = {
    "chipi/orrery": {
        "glitchtip": ["orrery-dev"], "branch_tag": True,
        "logs": "app:orrery", "logs_branch": True,
        "traces": ["orrery-lab-api", "orrery-mcp"],
    },
    "chipi/podcast_scraper": {
        "glitchtip": ["podcast-pipeline-dev", "podcast-api-dev", "player-dev"], "branch_tag": False,
        "logs": "(service:podcast-pipeline OR service:podcast-api OR service:player-api OR service:pipeline)",
        "logs_branch": False,
        "traces": ["podcast-pipeline", "podcast-api", "player-api"],
    },
    "chipi/humancopilot.eu": None,
    "chipi/eval-harness": None,
    "chipi/oceancanvas": None,
}

ERR_LEVELS = '"error","ERROR","critical","CRITICAL","fatal","FATAL"'
WARN_LEVELS = '"warn","WARN","warning","WARNING"'


def http_get(url, headers=None, timeout=60):
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode()


def git(*args, cwd=None):
    r = subprocess.run(["git", *args], capture_output=True, text=True, cwd=cwd)
    return r.stdout.strip() if r.returncode == 0 else ""


def project_from_remote(url):
    m = re.search(r"[:/]([^/:]+/[^/]+?)(?:\.git)?/?$", url)
    return m.group(1).lower() if m else ""


def resolve_project(name):
    n = name.lower()
    for key in PROJECTS:
        if n == key or n == key.split("/")[1]:
            return key
    return n


def parse_since(s, now):
    m = re.fullmatch(r"(\d+)([mhdw])", s)
    if m:
        secs = int(m.group(1)) * {"m": 60, "h": 3600, "d": 86400, "w": 604800}[m.group(2)]
        return now - dt.timedelta(seconds=secs)
    try:
        d = dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        sys.exit("--since must look like 90m, 16h, 14d or an ISO time")
    return d if d.tzinfo else d.replace(tzinfo=dt.timezone.utc)


def default_window(now, cwd=None):
    base = git("merge-base", "HEAD", "origin/main", cwd=cwd)
    if base:
        first = git("log", "--reverse", "--format=%cI", f"{base}..HEAD", cwd=cwd).splitlines()
        if first:
            return dt.datetime.fromisoformat(first[0]).astimezone(dt.timezone.utc), "since the branch's first commit"
    return now - dt.timedelta(days=7), "default 7d (no commits on this branch off origin/main)"


def iso(d):
    return d.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_token():
    t = os.environ.get("GLITCHTIP_DEV_TOKEN", "").strip()
    if t:
        return t
    try:
        for line in open(os.path.expanduser(TOKEN_FILE)):
            if line.startswith("GLITCHTIP_DEV_TOKEN="):
                return line.split("=", 1)[1].strip().strip("'\"")
    except OSError:
        pass
    return ""


def norm(m):
    m = re.sub(r"^\S+ \S+,?\d* ", "", m) if re.match(r"^\d{4}-\d\d-\d\d", m) else m
    m = re.sub(r"\[[^\]]{0,300}\]:?", "", m)
    m = re.sub(r"https?://\S+", "<url>", m)
    m = re.sub(r"(/[\w.\-]+){2,}", "<path>", m)
    m = re.sub(r"\b[0-9a-f]{8,}\b|\b[0-9a-f-]{36}\b", "<id>", m, flags=re.I)
    m = re.sub(r"\d+(\.\d+)?", "<n>", m)
    return re.sub(r"\s+", " ", m).strip()[:150]


def parse_ts(s):
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))


def check_glitchtip(cfg, branch, start, get=None):
    """Returns (lines, error_count, branch_filtered, not_checked_reason)."""
    get = get or http_get
    token = load_token()
    if not token:
        return [], 0, False, f"no GLITCHTIP_DEV_TOKEN in env or {TOKEN_FILE}"
    branch_filtered = cfg["branch_tag"]
    query = "is:unresolved" + (f" worktree:{branch}" if branch_filtered else "")
    lines, total = [], 0
    for slug in cfg["glitchtip"]:
        url = (f"{GLITCHTIP}/api/0/projects/homelab/{slug}/issues/?"
               + urllib.parse.urlencode({"query": query, "limit": 100}))
        try:
            issues = json.loads(get(url, {"Authorization": f"Bearer {token}"}))
        except Exception as e:
            return lines, total, branch_filtered, f"GlitchTip {slug}: {str(e)[:120]}"
        kept = [i for i in issues if parse_ts(i["lastSeen"]) >= start]
        lines.append(f"  {slug}: {len(kept)} unresolved in the window ({len(issues)} matched the query)")
        for i in sorted(kept, key=lambda x: x["lastSeen"], reverse=True)[:15]:
            lines.append(f"    {i['shortId']}  x{i['count']}  last {i['lastSeen'][:16]}Z  {i['title'][:100]}"
                         f"  [{i.get('culprit') or '-'}]  {i.get('permalink', '')}")
        total += len(kept)
    return lines, total, branch_filtered, ""


def vl(get, q):
    body = get(f"{VLOGS}/select/logsql/query?" + urllib.parse.urlencode({"query": q}))
    return [json.loads(x) for x in body.splitlines() if x.strip()]


def check_logs(cfg, branch, start, end, get=None):
    """Returns (lines, error_logs, not_checked_reason)."""
    get = get or http_get
    base = f"_time:[{iso(start)}, {iso(end)}] environment:dev {cfg['logs']}"
    if cfg["logs_branch"]:
        base += f' worktree:"{branch}"'
    try:
        by_level = vl(get, base + " | stats by (level) count() n")
        n_err = vl(get, base + f' (level:in({ERR_LEVELS}) OR ERROR OR Traceback) | stats count() n')
        rows = vl(get, base + f' (level:in({ERR_LEVELS}) OR level:in({WARN_LEVELS}) OR ERROR OR Traceback)'
                  " | sort by (_time) desc | limit 1000")
    except Exception as e:
        return [], 0, f"VictoriaLogs: {str(e)[:120]}"
    lines = ["  by level: " + (", ".join(f"{r.get('level') or '-'}={r['n']}"
                                         for r in sorted(by_level, key=lambda r: -int(r["n"]))) or "no dev log lines")]
    top = collections.Counter()
    for r in rows:
        lvl = (r.get("level") or "").lower()
        tag = "error" if lvl in ("error", "critical", "fatal") or not lvl else "warn"
        top[(tag, norm(r.get("_msg", "")))] += 1
    for (tag, msg), n in top.most_common(8):
        lines.append(f"    {n:>4}  {tag:5}  {msg}")
    if len(rows) >= 1000:
        lines.append("    (top patterns come from the newest 1000 error/warn lines)")
    return lines, int(n_err[0]["n"]) if n_err else 0, ""


def trace_failed(spans):
    for s in spans:
        tags = {x["key"]: x["value"] for x in s.get("tags", [])}
        code = tags.get("http.status_code") or tags.get("http.response.status_code")
        if tags.get("error") in (True, "true") or str(tags.get("otel.status_code", "")).upper() == "ERROR":
            return True
        try:
            if code is not None and int(code) >= 500:
                return True
        except (TypeError, ValueError):
            pass
    return False


def check_traces(cfg, branch, start, end, get=None):
    """Returns (lines, failed_traces, not_checked_reason)."""
    get = get or http_get
    lines, failed_total = [], 0
    for svc in cfg["traces"]:
        q = urllib.parse.urlencode({
            "service": svc, "start": int(start.timestamp() * 1e6), "end": int(end.timestamp() * 1e6),
            "limit": 200, "tags": json.dumps({"deployment.environment": "dev"})})
        try:
            data = json.loads(get(f"{VTRACES}/select/jaeger/api/traces?{q}")).get("data") or []
        except Exception as e:
            return lines, failed_total, f"VictoriaTraces {svc}: {str(e)[:120]}"
        dev, failed, unlabelled = [], [], 0
        for t in data:
            res = {}
            for p in t.get("processes", {}).values():
                res.update({x["key"]: x["value"] for x in p.get("tags", [])})
            if res.get("deployment.environment") != "dev":
                continue
            if res.get("worktree") not in (None, branch):
                continue
            unlabelled += "worktree" not in res
            sp = t["spans"]
            dur = (max(s["startTime"] + s["duration"] for s in sp) - min(s["startTime"] for s in sp)) / 1e6
            dev.append((dur, t["traceID"], sp[0]["operationName"]))
            if trace_failed(sp):
                failed.append((dur, t["traceID"], sp[0]["operationName"]))
        lines.append(f"  {svc}: {len(dev)} dev traces, {len(failed)} failed"
                     + (f" ({unlabelled} without a `worktree` label, not branch-filtered)" if unlabelled else ""))
        for dur, tid, op in sorted(failed, reverse=True)[:3]:
            lines.append(f"    failed  {dur:.2f}s  {op}  {VTRACES}/select/jaeger/api/traces/{tid}")
        for dur, tid, op in sorted(dev, reverse=True)[:2]:
            lines.append(f"    slow    {dur:.2f}s  {op}  {tid}")
        failed_total += len(failed)
    return lines, failed_total, ""


def main(argv=None, get=None, now=None, cwd=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project", help="orrery, podcast_scraper, or chipi/<repo>; default from git remote origin")
    ap.add_argument("--branch", help="default: the current git branch")
    ap.add_argument("--since", help="90m, 16h, 14d or an ISO time; default: the branch's first commit, else 7d")
    a = ap.parse_args(argv)
    now = now or dt.datetime.now(dt.timezone.utc)

    project = resolve_project(a.project) if a.project else project_from_remote(git("remote", "get-url", "origin", cwd=cwd))
    branch = a.branch or git("rev-parse", "--abbrev-ref", "HEAD", cwd=cwd)
    if not project or not branch:
        print("NOT CHECKED all: no project or branch (run inside a git worktree, or pass --project and --branch)")
        return 2
    if a.since:
        start, why = parse_since(a.since, now), f"--since {a.since}"
    else:
        start, why = default_window(now, cwd) if not a.branch else (now - dt.timedelta(days=7), "default 7d (--branch given)")
    print(f"o11y-dev  project={project}  branch={branch}  window={iso(start)} .. {iso(now)} ({why})")

    if project not in PROJECTS:
        print(f"NOT CHECKED all: {project} is not in the project map of this script (see PROJECTS)")
        return 2
    cfg = PROJECTS[project]
    if cfg is None:
        print(f"{project} sends no dev telemetry yet and has no dev GlitchTip project; nothing to read.")
        print(f"The contract it has to follow is in {CONTRACT_DOC}.")
        print(f"NOT CHECKED all: {project} has no dev telemetry")
        return 2

    unchecked = []
    print("\nGlitchTip (read-only, unresolved):")
    g_lines, errors, filtered, bad = check_glitchtip(cfg, branch, start, get)
    print("\n".join(g_lines))
    if bad:
        print(f"NOT CHECKED glitchtip: {bad}")
        unchecked.append("glitchtip")
    if not filtered:
        print(f"  not branch-filtered: this project's dev events carry no `worktree` tag yet, so these are every dev "
              f"error in the window, not only {branch}'s")

    print("\nLogs (VictoriaLogs, environment:dev):")
    l_lines, error_logs, bad = check_logs(cfg, branch, start, now, get)
    print("\n".join(l_lines))
    if bad:
        print(f"NOT CHECKED logs: {bad}")
        unchecked.append("logs")
    elif cfg["logs_branch"]:
        print(f"  branch-filtered (worktree:{branch}): older dev runs without the `worktree` label are not included")
    else:
        print("  not branch-filtered: dev logs carry no `worktree` label yet")

    print("\nTraces (VictoriaTraces, deployment.environment=dev):")
    t_lines, failed, bad = check_traces(cfg, branch, start, now, get)
    print("\n".join(t_lines))
    if bad:
        print(f"NOT CHECKED traces: {bad}")
        unchecked.append("traces")

    print(f"\nO11Y-DEV {project} {branch}: errors={errors} ({'branch-filtered' if filtered else 'not branch-filtered'}), "
          f"error-logs={error_logs}, failed-traces={failed}")
    return 2 if unchecked else 0


if __name__ == "__main__":
    sys.exit(main())
