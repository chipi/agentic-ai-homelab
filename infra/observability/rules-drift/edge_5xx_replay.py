#!/usr/bin/env python3
"""Replay rule edge-caddy-5xx-burst over Caddy history: which 5-minute windows would have fired.

Offline over a frozen corpus (fixtures/edge-5xx-corpus.json: per minute and host, the count of
job:caddy status >= 500). Evaluates the rule as Grafana does: every minute, the 5xx count per
host over the last 5 minutes, firing at >= 10 (threshold and window read from rules.yaml).

The rule was set on 2026-10-18 from 2026-09-18 .. 10-18 (four real episodes: 09-30 06:05 player
static 502s, 10-03 22:40 player API 504s, 10-07 22:54 Umami down, 10-17 15:05 prod OOM kill).
That window left VictoriaLogs' 30-day retention on 2026-11-17 and was never frozen; the corpus
is the month after it.

    python3 edge_5xx_replay.py                  # exit 0 when it fires exactly the expected episodes
    python3 edge_5xx_replay.py --threshold 15   # explore another threshold (no pass/fail)
    python3 edge_5xx_replay.py --freeze         # re-freeze from VictoriaLogs (VLOGS_URL, default
                                                # the mini's loopback)
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

HERE = os.path.dirname(os.path.abspath(__file__))
VL = os.environ.get("VLOGS_URL", "http://127.0.0.1:9428") + "/select/logsql/query"
CORPUS = os.path.join(HERE, "fixtures", "edge-5xx-corpus.json")
START, END = "2026-10-18T12:00:00Z", "2026-11-17T10:00:00Z"
# Every episode of the corpus is a real 5xx burst (checked 2026-11-17 against status codes and URIs).
EXPECTED = {("10-19 06:19", "closelistening.app"),          # 25 x 502 + 6 x 504, player API
            ("10-19 08:29", "closelistening.app"),          # 23 x 502, player API
            ("10-21 19:59", "telemetry.orrerylearn.com"),   # GlitchTip ingest 502, mini caddy restart
            ("10-26 13:46", "closelistening.app"),          # 28 x 502 + 11 x 504, player API
            ("10-27 07:13", "closelistening.app"),          # 43 x 502 + 4 x 504, player API
            ("11-04 10:57", "telemetry.orrerylearn.com"),   # GlitchTip ingest 502, mini caddy restart
            ("11-14 03:11", "telemetry.orrerylearn.com")}   # GlitchTip ingest 502, mini caddy restart

RULES = os.path.join(HERE, "..", "backend", "grafana", "provisioning", "alerting", "rules.yaml")


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
    with urllib.request.urlopen(url, timeout=300) as r:
        return [json.loads(line) for line in r.read().decode().splitlines() if line.strip()]


def freeze():
    rows = query(f"_time:[{START}, {END}) job:caddy status:>=500 | stats by (_time:1m, request.host) count() n")
    per = collections.defaultdict(dict)
    for r in rows:
        per[r["request.host"]][r["_time"][:16]] = int(r["n"])
    json.dump({"start": START, "end": END, "filter": "job:caddy status:>=500",
               "frozen": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%MZ"),
               "per_host": per}, open(CORPUS, "w"), sort_keys=True)
    open(CORPUS, "a").write("\n")
    print(f"froze {sum(sum(v.values()) for v in per.values())} 5xx over {len(per)} hosts into {CORPUS}")


def episodes(per_host, threshold, window):
    out, step = [], datetime.timedelta(minutes=1)
    for host, raw in per_host.items():
        counts = {datetime.datetime.fromisoformat(k + ":00+00:00"): n for k, n in raw.items()}
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
    ap.add_argument("--freeze", action="store_true")
    a = ap.parse_args()
    if a.freeze:
        freeze()
        return 0
    c = json.load(open(CORPUS))
    committed, window = rule_params()
    threshold = a.threshold or committed
    eps = episodes(c["per_host"], threshold, window)
    print(f"edge-caddy-5xx-burst replay {c['start']} .. {c['end']}, threshold >= {threshold} in {window}m "
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
