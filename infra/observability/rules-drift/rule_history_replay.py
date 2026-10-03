#!/usr/bin/env python3
"""Replay one alert rule from rules.yaml against VictoriaMetrics history: when would it
have fired? Uses the rule's own expression, threshold and `for:` at a 1-minute step (a
series fires once its condition held for `for`; a missing sample breaks the run, as
noDataState: OK does).

  rule_history_replay.py --uid delivery-queue-stuck --start 2026-09-20T00:00:00 \
      [--end now] [--expect 2026-10-02T06:00:00/2026-10-03T16:00:00 ...] [--vm http://localhost:8428]

--expect windows (UTC, start/end) are the incidents the rule must catch: PASS needs
every window covered by an episode and every episode inside some window (no noise).
"""
import argparse
import datetime as dt
import json
import subprocess
import sys
import urllib.parse
import urllib.request

RULES = "infra/observability/backend/grafana/provisioning/alerting/rules.yaml"
STEP = 60
CHUNK = 2 * 86400


def utc(s):
    return int(dt.datetime.strptime(s, "%Y-%m-%dT%H:%M:%S").replace(tzinfo=dt.timezone.utc).timestamp())


def load_rule(path, uid):
    text = open(path).read()
    try:
        import yaml
        doc = yaml.safe_load(text)
    except ImportError:                      # the mini's python3: parse with system Ruby
        doc = json.loads(subprocess.run(["/usr/bin/ruby", "-ryaml", "-rjson", "-e",
                                         "puts YAML.safe_load(STDIN.read).to_json"],
                                        input=text, capture_output=True, text=True, check=True).stdout)
    r = next(r for g in doc["groups"] for r in g["rules"] if r["uid"] == uid)
    expr = next(d["model"]["expr"] for d in r["data"] if d["refId"] == "q")
    ev = next(d["model"]["conditions"][0]["evaluator"] for d in r["data"] if d["refId"] == "threshold")
    f = r["for"]
    return r["title"], expr, ev["type"], float(ev["params"][0]), int(f[:-1]) * {"s": 1, "m": 60, "h": 3600}[f[-1]]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--uid", required=True)
    ap.add_argument("--start", required=True)
    ap.add_argument("--end", default="")
    ap.add_argument("--expect", nargs="*", default=[])
    ap.add_argument("--rules", default=RULES)
    ap.add_argument("--vm", default="http://localhost:8428")
    a = ap.parse_args()
    title, expr, op, thr, for_s = load_rule(a.rules, a.uid)
    start = utc(a.start)
    end = utc(a.end) if a.end else int(dt.datetime.now(dt.timezone.utc).timestamp())
    cmp = {"gt": lambda v: v > thr, "lt": lambda v: v < thr}[op]
    pts = {}
    t = start
    while t < end:
        q = urllib.parse.urlencode({"query": expr, "start": t, "end": min(t + CHUNK, end), "step": STEP})
        for r in json.load(urllib.request.urlopen(f"{a.vm}/api/v1/query_range?{q}", timeout=120))["data"]["result"]:
            key = tuple(sorted(r["metric"].items()))
            pts.setdefault(key, {}).update({int(float(ts)): float(v) for ts, v in r["values"]})
        t += CHUNK
    eps = []
    for key, series in pts.items():
        run, prev, fire = None, None, None
        for ts in sorted(series):
            ok = cmp(series[ts])
            run = (run if (ok and prev is not None and ts - prev == STEP and run is not None) else (ts if ok else None))
            if run is not None and ts - run >= for_s:
                fire = fire or [run + for_s, ts]
                fire[1] = ts
            elif fire:
                eps.append((key, *fire)); fire = None
            prev = ts
        if fire:
            eps.append((key, *fire))
    fmt = lambda x: dt.datetime.fromtimestamp(x, dt.timezone.utc).strftime("%m-%d %H:%M")
    print(f"{a.uid}: {title}\n  {op} {thr} for {for_s // 60}m, {fmt(start)} -> {fmt(end)} UTC\n  firing episodes: {len(eps)}")
    for key, s, e in sorted(eps, key=lambda x: x[1]):
        print(f"    {fmt(s)} -> {fmt(e)}  ({(e - s) / 3600:.1f} h)  {dict(key)}")
    fails = []
    if a.expect:
        wins = [tuple(utc(x) for x in w.split("/")) for w in a.expect]
        for ws, we in wins:
            if not any(s <= we and ws <= e for _, s, e in eps):
                fails.append(f"missed expected incident {fmt(ws)} -> {fmt(we)}")
        for key, s, e in eps:
            if not any(s <= we and ws <= e for ws, we in wins):
                fails.append(f"noise: fired {fmt(s)} -> {fmt(e)} outside every expected incident")
        print("PASS" if not fails else "FAIL:\n  " + "\n  ".join(fails))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
