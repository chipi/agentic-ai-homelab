#!/usr/bin/env python3
"""deploy-verify: a before/after gate for a deploy's telemetry. Read-only.

Runs ON the Mac mini (via host-run): it reads VictoriaMetrics/Logs/Traces, GlitchTip, Umami and
Langfuse locally. Stdlib only (Python 3.9).

    verify.py snapshot --project closelistening --out /tmp/cl-base.json      # before the deploy
    verify.py compare  --project closelistening --baseline /tmp/cl-base.json \
                       --release sha-ded80e0 [--since 2026-10-16T19:31:00Z] [--sourcemaps]

compare ends with "DEPLOY-VERIFY: PASS|FAIL" (exit 1 on FAIL). It checks, per the project profile:
  logs      every service logged since the deploy, labelled environment=prod
  traces    every traced service has spans since the deploy, carrying service.version == --release
  metrics   every scrape job is up; every listed counter has series (count_over_time, not instant)
  errors    GlitchTip issues first seen since the deploy, per project, with status. Each one FAILs the
            gate on purpose: someone has to look. Resolved ones show as (resolved).
  langfuse  traces since the deploy carry release == --release (LiteLLM's own traces are ignored)
  umami     each site received events since the deploy
  sourcemaps (orrery, --sourcemaps) every live _app/immutable JS with a debugId matches a stored bundle
"""
import argparse, base64, json, os, re, subprocess, sys, time, urllib.parse, urllib.request
from datetime import datetime, timezone

VM, VL, VT, GT, LF = ("http://127.0.0.1:8428", "http://127.0.0.1:9428", "http://127.0.0.1:10428",
                      "http://127.0.0.1:8090", "http://127.0.0.1:4000")
DOCKER = "/usr/local/bin/docker"

PROFILES = {
    "closelistening": {
        "log_services": ["player-api", "player-mcp", "player-obs", "podcast-api"],
        "trace_services": ["player-api", "player-mcp", "player-obs", "podcast-api"],
        "scrape_jobs": ["player_mcp", "player_obs"],
        "counters": ['mcp_tool_calls_total{service="player-mcp"}', 'mcp_tool_calls_total{service="player-obs"}'],
        "glitchtip": ["player", "player-api", "player-mcp", "player-obs", "podcast-api", "podcast-pipeline"],
        "langfuse_keys": "~/podcast-langfuse-prod.env",
        "umami_sites": ["Player"],
        "live_url": None,
    },
    "orrery": {
        "log_services": ["orrery-web", "orrery-mcp", "orrery-lab-api"],
        "trace_services": ["orrery-mcp", "orrery-lab-api"],
        "scrape_jobs": [],
        "counters": [],
        "glitchtip": ["orrery-prod", "orrery-lab-api", "orrery-mcp"],
        "langfuse_keys": None,
        "umami_sites": ["Orrery"],
        "live_url": "https://www.orrerylearn.com/",
    },
}
results = []


def check(ok, what, warn=False):
    tag = "PASS" if ok else ("WARN" if warn else "FAIL")
    if not warn or ok:
        results.append(ok)
    print(f"  [{tag}] {what}")


BROWSER_UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
              "Chrome/141.0.0.0 Safari/537.36 deploy-verify/1.0")


def get(url, headers=None, timeout=60):
    h = dict(headers or {})
    if url.startswith("https://"):
        h.setdefault("User-Agent", BROWSER_UA)   # Cloudflare 403s Python's default UA
    req = urllib.request.Request(url, headers=h)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode()


def envfile(path):
    d = {}
    for line in open(os.path.expanduser(path)):
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            d[k] = v.strip().strip('"').strip("'")
    return d


def vl(q):
    out = get(VL + "/select/logsql/query?" + urllib.parse.urlencode({"query": q}))
    return [json.loads(l) for l in out.splitlines() if l.strip()]


def vm(q):
    return json.loads(get(VM + "/api/v1/query?" + urllib.parse.urlencode({"query": q})))["data"]["result"]


def gt(path):
    tok = envfile("~/signal-fleet/fleet-gateway.env")["GLITCHTIP_TOKEN"]
    return json.loads(get(GT + "/api/0" + path, {"Authorization": "Bearer " + tok}))


def gt_project_ids():
    return {p["slug"]: p["id"] for p in gt("/organizations/homelab/projects/")}


def umami_sql(sql):
    p = subprocess.run([DOCKER, "exec", "-i", "-e", "PGOPTIONS=-c timezone=UTC", "umami-db", "psql",
                        "-U", "umami", "-d", "umami", "-At", "-F", "|", "-v", "ON_ERROR_STOP=1"],
                       input=sql, capture_output=True, text=True)
    # A failed query used to come back as "" and read as "0 events" — a silent WARN.
    if p.returncode != 0:
        raise RuntimeError(f"umami query failed (exit {p.returncode}): {p.stderr.strip()[:200]}")
    return p.stdout.strip()


def snapshot(prof):
    ids = gt_project_ids()
    snap = {"taken_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "glitchtip": {}}
    for slug in prof["glitchtip"]:
        issues = gt(f"/organizations/homelab/issues/?project={ids[slug]}&limit=100&query=")
        snap["glitchtip"][slug] = sorted(i["shortId"] for i in issues)
    return snap


def compare(prof, base, release, since):
    print(f"== logs since {since}")
    for s in prof["log_services"]:
        rows = vl(f'_time:>{since} service:{s} | stats by (environment, instance) count() n')
        prod = sum(int(r["n"]) for r in rows if r.get("environment") == "prod")
        check(prod > 0, f"{s}: {prod} prod lines")
        other = [(r.get("environment") or "(none)", r.get("instance") or "?", r["n"]) for r in rows
                 if r.get("environment") != "prod"]
        unlabelled = [o for o in other if o[0] == "(none)"]
        if unlabelled:
            check(False, f"{s}: lines with NO environment label: {unlabelled}")
        elif other:
            print(f"  [INFO] {s}: non-prod lines too (dev/staging runs, fine): {other}")
    print("== traces")
    end = int(time.time() * 1e6)
    start = int(datetime.strptime(since, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp() * 1e6)
    for s in prof["trace_services"]:
        q = urllib.parse.urlencode({"service": s, "start": start, "end": end, "limit": 50})
        try:
            data = json.loads(get(f"{VT}/select/jaeger/api/traces?{q}")).get("data") or []
        except Exception as e:
            check(False, f"{s}: trace query failed ({e})"); continue
        versions = set()
        for t in data:
            for p in t["processes"].values():
                if p["serviceName"] == s:
                    versions.add({x["key"]: x["value"] for x in p["tags"]}.get("service.version"))
        check(bool(data), f"{s}: {len(data)} traces since the deploy")
        if data and release:
            check(release in versions, f"{s}: service.version {sorted(v for v in versions if v)} contains {release}")
    print("== metrics")
    for job in prof["scrape_jobs"]:
        r = vm(f'up{{job="{job}"}}')
        check(bool(r) and all(x["value"][1] == "1" for x in r), f"up{{job={job}}} = {[x['value'][1] for x in r]}")
    for c in prof["counters"]:
        r = vm(f"count(count_over_time({c}[2d]))")
        n = int(float(r[0]["value"][1])) if r else 0
        check(n > 0, f"{c}: {n} series over 2d")
    print("== GlitchTip: issues first seen since the deploy")
    ids = gt_project_ids()
    for slug in prof["glitchtip"]:
        issues = gt(f"/organizations/homelab/issues/?project={ids[slug]}&limit=100&query=")
        new = [i for i in issues if i["firstSeen"][:19] >= since[:19]]
        if not new:
            check(True, f"{slug}: none")
        for i in new:
            known = i["shortId"] in (base.get("glitchtip", {}).get(slug, []) if base else [])
            check(False, f"{slug}: NEW {i['shortId']} ({i['status']}) x{i['count']} — {i['title'][:80]}"
                  + (" (in baseline)" if known else ""))
    if prof["langfuse_keys"]:
        print("== Langfuse")
        k = envfile(prof["langfuse_keys"])
        auth = "Basic " + base64.b64encode(f"{k['LANGFUSE_PUBLIC_KEY']}:{k['LANGFUSE_SECRET_KEY']}".encode()).decode()
        r = json.loads(get(f"{LF}/api/public/traces?" + urllib.parse.urlencode({"fromTimestamp": since, "limit": 100}),
                           {"Authorization": auth}))["data"]
        # LiteLLM's own callback writes litellm-* traces (pass_through_endpoint, acompletion…)
        # without the app's release; only the app's traces must carry it.
        app = [t for t in r if not (t.get("name") or "").startswith("litellm-")]
        rel = {t.get("release") for t in app}
        if app:
            check(rel == {release} if release else True, f"{len(app)} app traces, releases {sorted(map(str, rel))}")
        else:
            check(True, "no app traces since the deploy (nothing ran)", warn=True)
    print("== Umami")
    for site in prof["umami_sites"]:
        try:
            row = umami_sql(
                f"SELECT count(*) FILTER (WHERE e.created_at > '{since}'), "
                f"to_char(max(e.created_at) FILTER (WHERE e.created_at <= '{since}'), 'YYYY-MM-DD\"T\"HH24:MI:SS\"Z\"'), "
                f"to_char(max(e.created_at), 'YYYY-MM-DD\"T\"HH24:MI:SS\"Z\"') "
                f"FROM website_event e JOIN website w USING (website_id) "
                f"WHERE w.name = '{site}' AND w.deleted_at IS NULL;")
        except RuntimeError as e:
            check(False, f"{site}: {e}"); continue
        n_s, before, last = (row.split("|") + ["", "", ""])[:3]
        n = int(n_s or 0)
        if n > 0:
            check(True, f"{site}: {n} events since the deploy (latest {last})")
            continue
        # Sparse sites (the Player saw 24 h between events on 2026-10-24/25) are legitimately
        # silent for a while after a deploy: 0 is only a warning once the deploy is older
        # than the gap before it. Re-run compare later to settle an INCONCLUSIVE.
        fmt = "%Y-%m-%dT%H:%M:%SZ"
        dep = datetime.strptime(since, fmt).replace(tzinfo=timezone.utc)
        age = datetime.now(timezone.utc) - dep
        if before:
            gap = dep - datetime.strptime(before, fmt).replace(tzinfo=timezone.utc)
            if age < gap:
                print(f"  [INCONCLUSIVE] {site}: 0 events since the deploy, {age} ago; the last event before it "
                      f"was {before} ({gap} earlier) — re-run compare later")
                continue
        check(False, f"{site}: 0 events since the deploy ({age} ago; last event before it: {before or 'none'})",
              warn=True)
    return True


def sourcemaps(prof):
    print("== source maps (live JS vs stored bundles)")
    html = get(prof["live_url"])
    paths = sorted(set(re.findall(r'/_app/immutable/[A-Za-z0-9_./-]+\.js', html)))
    ids, missing, sizes = {}, [], {}
    base = prof["live_url"].rstrip("/")
    for p in paths:
        js = get(base + p, {"Cache-Control": "no-cache"})
        sizes[p] = len(js)
        m = re.findall(r"debugId=([0-9a-fA-F-]{36})", js)
        if m:
            ids[p] = m[-1].lower()
        else:
            missing.append(p)
    code = ("from apps.sourcecode.models import DebugSymbolBundle as B;"
            f"ids={sorted(set(ids.values()))!r};"
            "print(json.dumps(sorted(str(d) for d in B.objects.filter(debug_id__in=ids).values_list('debug_id', flat=True))))")
    out = subprocess.run([DOCKER, "exec", "glitchtip-web-1", "python", "manage.py", "shell", "-c", "import json;" + code],
                         capture_output=True, text=True).stdout.strip().splitlines()
    have = set(json.loads(out[-1])) if out else set()
    unmatched = [p for p, d in ids.items() if d not in have]
    # Tiny re-export stubs get a debugId from `sourcemaps inject` but ship no map (orrery, 2026-10-17:
    # 379 B and 439 B). Deployed files carry no sourceMappingURL, so size is the only signal here.
    stubs = [p for p in unmatched if sizes.get(p, 0) < 1024]
    real = [p for p in unmatched if p not in stubs]
    check(not real, f"{len(paths)} live JS files: {len(ids)} with a debugId, {len(ids) - len(unmatched)} matched to a bundle"
          + (f"; UNMATCHED: {real[:5]}" if real else ""))
    if stubs:
        print(f"  [INFO] {len(stubs)} unmatched stubs under 1 KB (no map shipped, expected): {stubs[:5]}")
    if missing:
        print(f"  [INFO] {len(missing)} without a debugId (map-less stubs/helpers are expected): {missing[:5]}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("snapshot"); s.add_argument("--project", required=True, choices=sorted(PROFILES)); s.add_argument("--out", required=True)
    c = sub.add_parser("compare"); c.add_argument("--project", required=True, choices=sorted(PROFILES))
    c.add_argument("--baseline"); c.add_argument("--release"); c.add_argument("--since")
    c.add_argument("--sourcemaps", action="store_true")
    a = ap.parse_args()
    prof = PROFILES[a.project]
    if a.cmd == "snapshot":
        snap = snapshot(prof)
        json.dump(snap, open(a.out, "w"), indent=1)
        print(f"snapshot {a.project} at {snap['taken_at']} -> {a.out} "
              f"({sum(len(v) for v in snap['glitchtip'].values())} GlitchTip issues across {len(snap['glitchtip'])} projects)")
        return
    base = json.load(open(a.baseline)) if a.baseline else None
    since = a.since or (base or {}).get("taken_at")
    if not since:
        sys.exit("compare needs --since or a --baseline with taken_at")
    print(f"deploy-verify {a.project}: since {since}, expected release {a.release or '(not checked)'}")
    compare(prof, base, a.release, since)
    if a.sourcemaps:
        if not prof["live_url"]:
            print("  [SKIP] no live_url for this project")
        else:
            sourcemaps(prof)
    ok = all(results)
    print("DEPLOY-VERIFY: PASS" if ok else "DEPLOY-VERIFY: FAIL")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
