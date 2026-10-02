#!/usr/bin/env python3
"""Observability review of one project over one time window, read-only: logs
(VictoriaLogs), errors (GlitchTip), traces (VictoriaTraces), and what the triage fleet
did on the project's GitHub repo. Prints a markdown report; --handover also writes it
to a file ready to paste to the agent working on the project.

  review.py --project closelistening --since 16h
  review.py --project orrery --start 2026-10-01T18:00:00Z --end 2026-10-02T08:00:00Z --handover /tmp/h.md

The stack lives on the homelab host (loopback-only ports), so the queries run there
over ssh (--ssh or HOMELAB_SSH); `gh` runs locally.
"""
import argparse
import datetime as dt
import json
import os
import re
import shlex
import subprocess
import sys

DEFAULT_SSH = os.environ.get("HOMELAB_SSH",
                             "ssh -i ~/.ssh/homelab_mini -o IdentitiesOnly=yes markodragoljevic@homelab")

# One entry per project. logs = a VictoriaLogs filter; glitchtip = short-id prefixes;
# traces = VictoriaTraces service names; repo = where the fleet files.
PROJECTS = {
    "closelistening": {"logs": "(app:podcast OR app:player)", "glitchtip": ["PODCAST", "PLAYER", "DELIVERY"],
                       "traces": ["podcast-pipeline", "podcast-api", "player-api", "player-mcp",
                                  "delivery-worker", "operator-public-api"], "repo": "chipi/podcast_scraper"},
    "orrery": {"logs": "app:orrery", "glitchtip": ["ORRERY"], "traces": [], "repo": "chipi/orrery"},
    "homelab": {"logs": "instance:homelab", "glitchtip": ["LITELLM"], "traces": [], "repo": "chipi/agentic-ai-homelab"},
}
PROJECTS["podcast"] = PROJECTS["closelistening"]

HOST = r'''
import collections, json, os, re, sys, time, urllib.parse, urllib.request
cfg = json.loads(sys.argv[1]); start, end = cfg["start"], cfg["end"]; out = {}
def vl(q):
    data = urllib.parse.urlencode({"query": q}).encode()
    for l in urllib.request.urlopen("http://127.0.0.1:9428/select/logsql/query", data, timeout=180):
        if l.strip():
            yield json.loads(l)
rng = f"_time:[{start}, {end}]"
LEVEL = re.compile(r"\b(DEBUG|INFO|WARN(?:ING)?|ERROR|CRITICAL|FATAL|Traceback)\b")
def norm(m):
    m = re.sub(r"^\S+ \S+,?\d* ", "", m)                       # leading timestamp
    m = re.sub(r"\[[^\]]{0,300}\]:?", "", m)                   # [run=… feed=…] contexts
    m = re.sub(r"https?://\S+", "<url>", m)
    m = re.sub(r"(/[\w.\-]+){2,}", "<path>", m)
    m = re.sub(r"\b[0-9a-f]{8,}\b|\b[0-9a-f-]{36}\b", "<id>", m, flags=re.I)
    m = re.sub(r"\d+(\.\d+)?", "<n>", m)
    return re.sub(r"\s+", " ", m).strip()[:150]
lv, pat, first, streams = collections.Counter(), collections.Counter(), {}, collections.defaultdict(set)
for d in vl(f"{rng} {cfg['logs']} | fields _time, _msg, app, surface, container, level"):
    msg = d.get("_msg", "")
    m = LEVEL.search(msg[:200])
    level = (d.get("level") or (m.group(1) if m else "")).upper().replace("WARN", "WARNING").replace("WARNINGING", "WARNING")
    lv[(d.get("app", ""), level or "-")] += 1
    if level in ("WARNING", "ERROR", "CRITICAL", "FATAL", "TRACEBACK"):
        k = (level, norm(msg)); pat[k] += 1; first.setdefault(k, d["_time"][:16])
        streams[k].add(d.get("container") or d.get("surface") or "")
out["levels"] = [[a, l, n] for (a, l), n in lv.most_common()]
order = sorted(pat.items(), key=lambda kv: (kv[0][0] == "WARNING", -kv[1]))
out["patterns"] = [[k[0], n, len(streams[k]), first[k], k[1]] for k, n in order[:40]]
# GlitchTip: issues whose lastSeen falls in the window
env = {}
for l in open(os.path.expanduser("~/signal-fleet/fleet-gateway.env")):
    if "=" in l and not l.lstrip().startswith("#"):
        k, v = l.strip().split("=", 1); env[k] = v
req = urllib.request.Request("http://127.0.0.1:8090/api/0/organizations/homelab/issues/?query=&limit=100&sort=-last_seen",
                             headers={"Authorization": "Bearer " + env.get("GLITCHTIP_TOKEN", "")})
gt = []
for i in json.load(urllib.request.urlopen(req, timeout=30)):
    if any(i["shortId"].startswith(p) for p in cfg["glitchtip"]) and start[:16] <= i["lastSeen"][:16] <= end[:16]:
        gt.append([i["shortId"], i["count"], i["firstSeen"][:16], i["lastSeen"][:16], i["status"],
                   i["firstSeen"][:16] >= start[:16], i["title"][:120]])
out["glitchtip"] = gt
# Traces: per service, slowest operations, slowest outbound URLs, error spans
def iso_us(s):
    return int(time.mktime(time.strptime(s[:19], "%Y-%m-%dT%H:%M:%S")) - time.timezone) * 1000000
tr = {}
for svc in cfg["traces"]:
    q = urllib.parse.urlencode({"service": svc, "start": iso_us(start), "end": iso_us(end), "limit": 1000})
    try:
        data = json.load(urllib.request.urlopen(f"http://127.0.0.1:10428/select/jaeger/api/traces?{q}", timeout=60)).get("data") or []
    except Exception as e:
        tr[svc] = {"error": str(e)[:120]}; continue
    ops, urls, errs = collections.defaultdict(list), collections.defaultdict(list), collections.Counter()
    for t in data:
        for s in t["spans"]:
            tags = {x["key"]: x["value"] for x in s.get("tags", [])}
            d = s["duration"] / 1e6; ops[s["operationName"]].append(d)
            u = tags.get("http.url") or tags.get("url.full")
            if u:
                urls[str(u).split("?")[0]].append(d)
            if tags.get("error") in (True, "true") or str(tags.get("otel.status_code", "")).upper() == "ERROR":
                errs[s["operationName"]] += 1
    def summ(xs):
        xs = sorted(xs); return [len(xs), round(xs[len(xs) // 2], 1), round(xs[min(len(xs) - 1, int(.95 * len(xs)))], 1), round(xs[-1], 1)]
    tr[svc] = {"traces": len(data), "capped": len(data) >= 1000,
               "ops": sorted([[o] + summ(v) for o, v in ops.items()], key=lambda r: -r[4])[:6],
               "urls": sorted([[u] + summ(v) for u, v in urls.items()], key=lambda r: -r[4])[:6],
               "error_spans": dict(errs)}
out["traces"] = tr
print(json.dumps(out))
'''


def parse_since(s):
    m = re.fullmatch(r"(\d+)([hd])", s)
    if not m:
        sys.exit("--since must look like 16h or 3d")
    n = int(m.group(1)) * (3600 if m.group(2) == "h" else 86400)
    return dt.datetime.now(dt.timezone.utc) - dt.timedelta(seconds=n)


def fleet_actions(repo, start):
    r = subprocess.run(["gh", "api", "--paginate", f"repos/{repo}/issues/comments?since={start}&per_page=100"],
                       capture_output=True, text=True, timeout=120)
    if r.returncode != 0:
        return [f"(gh failed: {r.stderr.strip()[:120]})"]
    out = []
    for c in json.loads(r.stdout.strip().replace("][", ",") or "[]"):
        b = c["body"]
        if b.startswith(("Recurred ", "Low-signal occurrence", "**Looks resolved?**")):
            n = c["issue_url"].rsplit("/", 1)[1]
            out.append(f"{c['created_at'][:16]} #{n} {re.sub(chr(10), ' ', b)[:150]}")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True, choices=sorted(PROJECTS))
    ap.add_argument("--since", help="e.g. 16h, 2d")
    ap.add_argument("--start")
    ap.add_argument("--end")
    ap.add_argument("--ssh", default=DEFAULT_SSH)
    ap.add_argument("--handover", help="also write the report to this file")
    a = ap.parse_args()
    now = dt.datetime.now(dt.timezone.utc)
    start = a.start or (parse_since(a.since or "16h")).strftime("%Y-%m-%dT%H:%M:%SZ")
    end = a.end or now.strftime("%Y-%m-%dT%H:%M:%SZ")
    p = PROJECTS[a.project]
    cfg = dict(p, start=start, end=end)
    cmd = shlex.split(os.path.expanduser(a.ssh)) + ["python3", "-", shlex.quote(json.dumps(cfg))]
    r = subprocess.run(cmd, input=HOST, capture_output=True, text=True, timeout=900)
    if r.returncode != 0:
        sys.exit(f"host query failed: {r.stderr.strip()[-600:]}")
    h = json.loads(r.stdout)
    L = []
    w = L.append
    w(f"# Observability review: {a.project}, {start} → {end}\n")
    w("Read-only queries against the homelab stack (VictoriaLogs, GlitchTip, VictoriaTraces) and GitHub.\n")
    w("## Log volume by app and level")
    for app, lvl, n in h["levels"][:20]:
        w(f"- {app or '-':<10} {lvl:<9} {n}")
    w("\n## Warning and error patterns (normalized; count, streams, first seen)")
    for lvl, n, ns, first, msg in h["patterns"]:
        w(f"- {lvl:<8} {n:>5} in {ns:>2} streams, first {first}: `{msg}`")
    w("\n## Errors (GlitchTip issues seen in the window)")
    for sid, n, f, l, st, new, title in h["glitchtip"]:
        w(f"- {'NEW ' if new else ''}{sid} count={n} first={f} last={l} {st}: {title}")
    if not h["glitchtip"]:
        w("- none")
    w("\n## Traces")
    for svc, t in h["traces"].items():
        if "error" in t:
            w(f"- {svc}: query failed ({t['error']})")
            continue
        w(f"- **{svc}**: {t['traces']} traces{' (API cap 1000 hit — partial)' if t['capped'] else ''}, error spans {t['error_spans'] or 0}")
        for o, n, p50, p95, mx in t["ops"][:4]:
            w(f"  - op `{o}` n={n} p50={p50}s p95={p95}s max={mx}s")
        for u, n, p50, p95, mx in t["urls"][:4]:
            w(f"  - call `{u}` n={n} p50={p50}s p95={p95}s max={mx}s")
    if not h["traces"]:
        w("- no trace services configured for this project")
    w(f"\n## Triage fleet actions on {p['repo']}")
    acts = fleet_actions(p["repo"], start)
    for x in acts[:30]:
        w(f"- {x}")
    if not acts:
        w("- none")
    w("\n## Not covered by this report")
    w("- metrics and alerts (Grafana); whether each pattern is a bug: read the examples in VictoriaLogs")
    w("- warnings never reach the triage fleet: anything systematic above is invisible to it")
    w("- traces are capped at 1000 per service by the API; error-span counts depend on instrumentation")
    report = "\n".join(L)
    print(report)
    if a.handover:
        open(a.handover, "w").write(report + "\n")
        print(f"\n(handover written to {a.handover})")


if __name__ == "__main__":
    main()
