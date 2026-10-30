#!/usr/bin/env python3
"""Put research runs on the research-bench board as Grafana annotations (tag `research-run`).

Input: a TSV (or stdin) with one run per line:
    run_id <TAB> host <TAB> model <TAB> start_utc <TAB> end_utc   (eval-harness writes this to
    /work/eval-harness/hf-v1/research-runs.tsv on the X3; a header line is skipped)
host is dgx-llm-1 | x3 | macbook; times are ISO 8601 UTC; end may be empty or "running" for a run still going,
or "stopped HH:MMZ partial (n of N)" for a run cut short (resumed later under a new run_id)
(the annotation is then a point at the start, widened to a region on a later call with the end).

Idempotent: an existing annotation is found by its run_id tag and updated, never duplicated.
Runs on the mini (Grafana on 127.0.0.1:3000; admin credentials from the backend .env), e.g.
    host-run homelab mark_runs.py runs.tsv          (dry run: prints what it would post)
    host-run homelab mark_runs.py runs.tsv --apply
"""
import base64, json, os, re, sys, urllib.request, urllib.error
from datetime import datetime, timezone

G = "http://127.0.0.1:3000"
ENV = os.path.expanduser("~/agentic-ai-homelab/infra/observability/backend/.env")
BOARD = "research-bench"


def env():
    d = {}
    for line in open(ENV):
        m = re.match(r"^([A-Z0-9_]+)=(.*)$", line.strip())
        if m:
            d[m.group(1)] = m.group(2).strip().strip('"')
    return d


def call(method, path, body=None):
    e = env()
    a = base64.b64encode(f"{e['GRAFANA_ADMIN_USER']}:{e['GRAFANA_ADMIN_PASSWORD']}".encode()).decode()
    req = urllib.request.Request(G + path, method=method, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Authorization": "Basic " + a, "Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=30))


def ms(t):
    return int(datetime.fromisoformat(t.replace("Z", "+00:00")).astimezone(timezone.utc).timestamp() * 1000)


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    apply = "--apply" in sys.argv
    lines = open(args[0]).read().splitlines() if args else sys.stdin.read().splitlines()
    dash = call("GET", f"/api/dashboards/uid/{BOARD}")["dashboard"]
    for line in lines:
        if not line.strip() or line.startswith("#"):
            continue
        run_id, host, model, start, end = [c.strip() for c in (line.split("\t") + [""] * 5)[:5]]
        if run_id == "run_id":
            continue  # header
        # end: an ISO time, empty/"running", or eval-harness's "stopped HH:MMZ partial (n of N)"
        note, end_iso = "", end
        m = re.match(r"stopped (\d{2}):(\d{2})Z(.*)", end)
        if m:
            end_iso = f"{start[:10]}T{m.group(1)}:{m.group(2)}:00Z"
            note = " — stopped" + m.group(3)
        elif end in ("", "running"):
            end_iso, note = "", " (running)"
        tags = ["research-run", f"run:{run_id}", f"host:{host}", f"model:{model}"]
        body = {"dashboardUID": BOARD, "time": ms(start), "tags": tags,
                "text": f"{run_id}<br>{model} on {host}{note}"}
        if end_iso:
            body["timeEnd"] = ms(end_iso)
        existing = call("GET", f"/api/annotations?tags=run:{run_id}&limit=5")
        verb = "UPDATE" if existing else "CREATE"
        print(f"{verb} {run_id} {host} {model} {start} -> {end or 'running'}")
        if not apply:
            continue
        if existing:
            call("PATCH", f"/api/annotations/{existing[0]['id']}", body)
        else:
            call("POST", "/api/annotations", body)
    if not apply:
        print("dry run: pass --apply to post")


if __name__ == "__main__":
    main()
