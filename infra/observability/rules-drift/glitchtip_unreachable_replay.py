#!/usr/bin/env python3
"""Replay rule glitchtip-unreachable-from-prod over a frozen month of prod edge history.

The corpus (fixtures/glitchtip-unreachable-corpus.json) holds, per minute, the count the rule's
own filter matched (502/503/504 on GlitchTip ingest paths) and the count of all GlitchTip ingest
requests. The replay evaluates the rule as Grafana does: every minute, the sum over the last
`window` minutes, firing once the threshold has held for `for`.

Pass criteria:
  1. history: no episode fires (every 502 episode in the corpus was a restart of the mini's caddy,
     1-8 min, checked 2026-11-17 against container:caddy start-up lines);
  2. outage: a full outage (every ingest request a 502) injected at each of the 10 quietest hours
     fires within 25 minutes of its start;
  3. the rule's filter in rules.yaml is the one the corpus was frozen with.

    python3 glitchtip_unreachable_replay.py            # replay the committed rule; exit 0 = PASS
    python3 glitchtip_unreachable_replay.py --freeze   # re-freeze the corpus from VictoriaLogs
"""
import argparse
import datetime as dt
import json
import os
import re
import sys
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
RULES = os.path.join(HERE, "..", "backend", "grafana", "provisioning", "alerting", "rules.yaml")
CORPUS = os.path.join(HERE, "fixtures", "glitchtip-unreachable-corpus.json")
UID = "glitchtip-unreachable-from-prod"
VL = os.environ.get("VLOGS_URL", "https://vlogs.tail6d0ed4.ts.net") + "/select/logsql/query"
START, END = "2026-10-18T12:00:00Z", "2026-11-17T10:00:00Z"
DETECT_MIN = 25


def rule():
    """(filter, threshold, window_min, for_min) as committed in rules.yaml."""
    text = open(RULES).read()
    block = text[text.index(f"uid: {UID}"):]
    block = block[:block.index("\n      - uid:")]
    expr = re.search(r"expr: '(.*)'", block).group(1)
    filt = expr.split(" | stats")[0]
    gt = int(re.search(r"type: gt, params: \[(\d+)\]", block).group(1))
    window = int(re.search(r"relativeTimeRange: \{ from: (\d+)", block).group(1)) // 60
    m = re.search(r"\n        for: (\d+)([sm])", block)
    for_min = int(m.group(1)) // (60 if m.group(2) == "s" else 1)
    return filt, gt + 1, window, for_min


def per_minute(q):
    url = VL + "?" + urllib.parse.urlencode({"query": q})
    with urllib.request.urlopen(url, timeout=300) as r:
        rows = [json.loads(line) for line in r.read().decode().splitlines() if line.strip()]
    return {row["_time"][:16]: int(row["n"]) for row in rows}


def freeze():
    filt = rule()[0]
    traffic_filt = re.sub(r" status:in\([^)]*\)", "", filt)
    rng = f"_time:[{START}, {END})"
    bad = per_minute(f"{rng} {filt} | stats by (_time:1m) count() n")
    total = per_minute(f"{rng} {traffic_filt} | stats by (_time:1m) count() n")
    json.dump({"start": START, "end": END, "filter": filt, "traffic_filter": traffic_filt,
               "frozen": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%MZ"),
               "bad": bad, "total": [total.get(m, 0) for m in minutes(START, END)]},
              open(CORPUS, "w"), sort_keys=True)
    open(CORPUS, "a").write("\n")
    print(f"froze {sum(bad.values())} bad / {sum(total.values())} total requests "
          f"({len(total)} of {len(minutes(START, END))} minutes with traffic) into {CORPUS}")


def minutes(start, end):
    t = dt.datetime.fromisoformat(start.replace("Z", "+00:00"))
    stop = dt.datetime.fromisoformat(end.replace("Z", "+00:00"))
    out = []
    while t < stop:
        out.append(t.strftime("%Y-%m-%dT%H:%M"))
        t += dt.timedelta(minutes=1)
    return out


def fires(series, threshold, window, for_min):
    """Start minutes (index) at which the rule would fire; series is a list of per-minute counts."""
    out, run, firing = [], None, False
    for i in range(len(series)):
        ok = sum(series[max(0, i - window + 1):i + 1]) >= threshold
        run = (run if run is not None else i) if ok else None
        if run is not None and i - run >= for_min and not firing:
            out.append(i)
            firing = True
        if run is None:
            firing = False
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--freeze", action="store_true")
    if ap.parse_args().freeze:
        freeze()
        return 0
    c = json.load(open(CORPUS))
    filt, threshold, window, for_min = rule()
    mins = minutes(c["start"], c["end"])
    bad = [c["bad"].get(m, 0) for m in mins]
    total = c["total"]
    if len(total) != len(mins):
        failures_early = f"corpus has {len(total)} traffic minutes, the window {len(mins)}"
        print(f"FAIL: {failures_early}")
        return 1
    print(f"{UID}: >= {threshold} in {window}m for {for_min}m; corpus {c['start']} .. {c['end']}, "
          f"{sum(bad)} bad of {sum(total)} ingest requests")
    failures = []

    if filt != c["filter"]:
        failures.append(f"rules.yaml filter differs from the corpus's (re-freeze): {filt!r}")

    hist = fires(bad, threshold, window, for_min)
    print(f"history: {len(hist)} firing(s)")
    for i in hist:
        print(f"  fires {mins[i]}Z")
    if hist:
        failures.append(f"history fired {len(hist)} time(s); every episode in it was a caddy restart")

    hours = sorted(range(0, len(mins) - 60, 60), key=lambda i: sum(total[i:i + 60]))
    hours = [i for i in hours if sum(total[i:i + 60]) > 0][:10]
    for i in hours:
        series = bad[:i] + total[i:i + 60] + bad[i + 60:]
        hit = [f for f in fires(series, threshold, window, for_min) if i <= f < i + 60]
        took = hit[0] - i if hit else None
        print(f"outage at {mins[i]}Z ({sum(total[i:i + 60])} requests in the hour): "
              + (f"fires after {took} min" if hit else "NOT fired"))
        if took is None or took > DETECT_MIN:
            failures.append(f"outage at {mins[i]}Z not caught within {DETECT_MIN} min")

    for f in failures:
        print(f"FAIL: {f}")
    print("PASS" if not failures else "FAIL")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
