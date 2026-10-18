#!/usr/bin/env python3
"""Replay rule edge-caddy-5xx-burst over Caddy history: which 5-minute windows would have fired.

Runs ON the mini (VictoriaLogs on loopback), read-only. Evaluates the rule as Grafana
does: every minute, the 5xx count per host over the last 5 minutes, firing at >= 10.
The window is fixed (2026-09-18 .. 2026-10-18) so the result is reproducible until
VictoriaLogs' 30-day retention drops its start (about 2026-11-17).

    python3 edge_5xx_replay.py             # the committed rule (threshold + window read from rules.yaml);
                                           # exit 0 when it fires exactly the expected four episodes
    python3 edge_5xx_replay.py --threshold 15   # explore another threshold (no pass/fail)
"""
import argparse
import collections
import os
import re
import datetime
import json
import sys
import urllib.parse
import urllib.request

VL = "http://127.0.0.1:9428/select/logsql/query"
START, END = "2026-09-18T12:00:00Z", "2026-10-18T12:00:00Z"
# The four real incidents of the window (checked 2026-10-18 against status codes and URIs).
EXPECTED = {("09-30 06:05", "closelistening.app"),            # 14 x 502, player static files
            ("10-03 22:40", "closelistening.app"),            # 11 x 504, player API
            ("10-07 22:54", "analytics.closelistening.app"),  # 58 x 502 on /api/send, Umami down
            ("10-17 15:05", "closelistening.app")}            # 36 x 502, prod OOM kill


RULES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend", "grafana",
                     "provisioning", "alerting", "rules.yaml")


def rule_params():
    """(threshold, window_minutes) as committed in rules.yaml: the replay tests that rule."""
    text = open(RULES).read()
    block = text[text.index("uid: edge-caddy-5xx-burst"):]
    block = block[:block.index("\n      - uid:")] if "\n      - uid:" in block else block
    gt = int(re.search(r"type: gt, params: \[(\d+)\]", block).group(1))
    window = int(re.search(r"relativeTimeRange: \{ from: (\d+)", block).group(1)) // 60
    return gt + 1, window


def query(q):
    url = VL + "?" + urllib.parse.urlencode({"query": q})
    with urllib.request.urlopen(url, timeout=120) as r:
        return [json.loads(line) for line in r.read().decode().splitlines() if line.strip()]


def episodes(threshold, window):
    rows = query(f"_time:[{START}, {END}) job:caddy status:>=500 | stats by (_time:1m, request.host) count() n")
    per = collections.defaultdict(dict)
    for r in rows:
        t = datetime.datetime.fromisoformat(r["_time"].replace("Z", "+00:00"))
        per[r["request.host"]][t] = int(r["n"])
    out, step = [], datetime.timedelta(minutes=1)
    for host, counts in per.items():
        t, end = min(counts), max(counts) + window * step
        firing = False
        while t <= end:
            n = sum(counts.get(t - k * step, 0) for k in range(window))
            if n >= threshold and not firing:
                firing, start, peak = True, t, n
            elif n >= threshold:
                peak = max(peak, n)
            elif firing:
                out.append((start.strftime("%m-%d %H:%M"), host, peak))
                firing = False
            t += step
    return sorted(out)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--threshold", type=int, help="override the committed rule's threshold (explore)")
    a = ap.parse_args()
    committed, window = rule_params()
    threshold = a.threshold or committed
    eps = episodes(threshold, window)
    print(f"edge-caddy-5xx-burst replay {START} .. {END}, threshold >= {threshold} in {window}m "
          f"(rules.yaml: >= {committed}): {len(eps)} episodes")
    for e in eps:
        print(f"  {e[0]}  {e[1]:32} peak {e[2]}")
    if a.threshold:
        return 0
    got = {(e[0], e[1]) for e in eps}
    ok = got == EXPECTED
    print("PASS" if ok else f"FAIL: missing {sorted(EXPECTED - got)}, extra {sorted(got - EXPECTED)}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
