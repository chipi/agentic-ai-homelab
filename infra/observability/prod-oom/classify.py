#!/usr/bin/env python3
"""Name every kernel OOM kill on prod-podcast, and say whether it matters (chipi/infra asked,
2026-11-08: infra-oom-kill fired on every kill but could not tell a serving app from a crash-looping
eval container; one 28 h firing hid 337 kills).

  classify.py --since 2026-10-26T00:00:00Z [--until ...] [--push]     on the mini (stdlib only)

Reads the kernel's `oom-kill:constraint=...,oom_memcg=...,task_memcg=...,task=...` lines from
VictoriaLogs (prod's journal), and names the container from the docker-<id>.scope in task_memcg,
through cadvisor's container_memory_rss series in VictoriaMetrics (the id label carries the scope,
the name label the container). Each kill is classified:
  global   CONSTRAINT_NONE (the box ran out): critical, whatever the victim
  serving  a memcg kill of a serving container (SERVING below): critical
  other    any other memcg kill (evals-*, a one-off under cl-oneoff.slice, a pipeline run): warning
Without --push it prints the table (the replay). With --push it writes one sample per kill to
VictoriaMetrics at the kill's own time: prod_oom_kill{instance, container, kind, severity, constraint} 1,
which the alert rules count. A cursor file keeps --push from writing a kill twice.
"""
import argparse
import datetime
import json
import os
import re
import sys
import urllib.parse
import urllib.request

VL = os.environ.get("VL_URL", "http://127.0.0.1:9428")
VM = os.environ.get("VM_URL", "http://127.0.0.1:8428")
INSTANCE = "prod-podcast"
# serving containers (infra, 2026-11-08), by name without compose's -N suffix
SERVING = {"player-api", "operator-api", "compose-api", "player-mcp", "postgres", "litellm"}
CURSOR = os.path.expanduser("~/.prod-oom-classify.cursor")
# a memcg kill names oom_memcg; a global one has `global_oom` instead (10-31 13:05, 11-01 01:21)
LINE = re.compile(r"oom-kill:constraint=(?P<constraint>[A-Z_]+),.*?(?:oom_memcg=(?P<oom>[^,]*)|(?P<global>global_oom)),task_memcg=(?P<task>[^,]*),task=(?P<proc>[^,]*),pid=(?P<pid>\d+)")
SCOPE = re.compile(r"docker-([0-9a-f]{64})\.scope")


def vl_lines(since, until):
    q = f'_time:[{since}, {until}) instance:{INSTANCE} "oom-kill:constraint"'
    body = urllib.request.urlopen(VL + "/select/logsql/query?" + urllib.parse.urlencode({"query": q, "limit": "10000"}), timeout=120).read().decode()
    return [json.loads(l) for l in body.splitlines() if l.strip()]


_names = {}


def name_of(cid):
    """The container name cadvisor recorded for a docker id, at any time in the last 60 days."""
    if cid not in _names:
        q = f'max by (name) (last_over_time(container_memory_rss{{instance="{INSTANCE}", id=~".*docker-{cid}\\\\.scope", name!=""}}[60d]))'
        r = json.load(urllib.request.urlopen(VM + "/api/v1/query?" + urllib.parse.urlencode({"query": q}), timeout=60))["data"]["result"]
        _names[cid] = r[0]["metric"]["name"] if r else ""
    return _names[cid]


def classify(rec):
    m = LINE.search(rec.get("_msg", ""))
    if not m:
        # never dropped silently: an oom-kill line this cannot read is a critical of its own
        return {"time": rec["_time"], "pid": "?", "constraint": "UNPARSED", "container": "(unparsed oom-kill line)",
                "kind": "unparsed", "severity": "critical", "process": "?", "where": rec.get("_msg", "")[:60]}
    sc = SCOPE.search(m["task"])
    cid = sc.group(1) if sc else ""
    name = name_of(cid) if cid else ""
    base = re.sub(r"-\d+$", "", name)                    # compose replica suffix
    if m["constraint"] == "CONSTRAINT_NONE" or m["global"]:
        kind, sev = "global", "critical"
    elif base in SERVING:
        kind, sev = "serving", "critical"
    else:
        kind, sev = "other", "warning"
    where = "cl-oneoff.slice" if "/cl.slice/cl-oneoff.slice" in m["task"] else ("system.slice" if "/system.slice/" in m["task"] else m["task"][:40])
    return {"time": rec["_time"], "pid": m["pid"], "constraint": m["constraint"], "container": name or ("(docker " + cid[:12] + ", name unknown)" if cid else "(no container)"),
            "kind": kind, "severity": sev, "process": m["proc"], "where": where}


def push(events):
    lines = []
    for e in events:
        # pid makes every kill its own sample: two kills of one container in the same second would
        # otherwise be one series at one timestamp, which VictoriaMetrics keeps once
        lab = {"instance": INSTANCE, "container": e["container"], "kind": e["kind"], "severity": e["severity"],
               "constraint": e["constraint"], "pid": e["pid"], "service": "prod-oom-classify", "environment": "operations"}
        lines.append("prod_oom_kill{" + ",".join(f'{k}="{v}"' for k, v in sorted(lab.items())) + f"}} 1 {ms(e['time'])}")
    # the job's own heartbeat (rule prod-oom-classify-stale)
    lines.append(f'prod_oom_classify_last_run_timestamp_seconds{{instance="{INSTANCE}",service="prod-oom-classify",environment="operations"}} '
                 f"{int(datetime.datetime.utcnow().replace(tzinfo=datetime.timezone.utc).timestamp())}")
    req = urllib.request.Request(VM + "/api/v1/import/prometheus", data=("\n".join(lines) + "\n").encode(), method="POST")
    urllib.request.urlopen(req, timeout=30).read()


def ms(ts):
    """VictoriaLogs' RFC 3339 time (nanoseconds, Z) as epoch milliseconds."""
    head, _, frac = ts.rstrip("Z").partition(".")
    base = datetime.datetime.strptime(head, "%Y-%m-%dT%H:%M:%S").replace(tzinfo=datetime.timezone.utc)
    return int(base.timestamp() * 1000) + int((frac + "000")[:3])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--since")
    ap.add_argument("--until", default=None, help="default: now; with --push, 2 minutes ago (log lines arrive late)")
    ap.add_argument("--push", action="store_true")
    a = ap.parse_args()
    lag = datetime.timedelta(minutes=2 if a.push else 0)
    a.until = a.until or (datetime.datetime.utcnow() - lag).strftime("%Y-%m-%dT%H:%M:%SZ")
    since = a.since
    if a.push and not since:
        since = open(CURSOR).read().strip() if os.path.exists(CURSOR) else (datetime.datetime.utcnow() - datetime.timedelta(minutes=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
    if not since:
        sys.exit("--since is required without --push")
    events = [e for e in (classify(r) for r in vl_lines(since, a.until)) if e]
    events.sort(key=lambda e: e["time"])
    if a.push:
        push(events)
        open(CURSOR + ".tmp", "w").write(a.until)
        os.replace(CURSOR + ".tmp", CURSOR)
        print(f"PUSH: {len(events)} kills {since}..{a.until}")
        return
    for e in events:
        print(f"{e['time'][:19]}  {e['severity']:8} {e['kind']:7} {e['constraint']:16} {e['container']:40} {e['process']:16} {e['where']}")
    by = {}
    for e in events:
        k = (e["severity"], e["kind"], e["container"]); by[k] = by.get(k, 0) + 1
    print("\nby container:")
    for (sev, kind, c), n in sorted(by.items(), key=lambda x: (-x[1], x[0])):
        print(f"  {n:4}  {sev:8} {kind:7} {c}")
    print(f"TOTAL {len(events)} kills, critical {sum(1 for e in events if e['severity'] == 'critical')}")


if __name__ == "__main__":
    main()
