#!/usr/bin/env python3
"""NoData replay: for each past NoData notification, was the host really dark?

Input: Grafana alert state history (NoData transitions) exported to JSON as
[{"rule": title, "t": unix_seconds}]. For each episode it asks VictoriaMetrics, at
that moment, whether the host's node_load1 still had samples in the last 10 min
(and, on the mini, whether the colima forward was up). That separates:
  HOST DARK         the whole host stopped reporting — a host dead-man must catch it
  FORWARD DOWN      the mini's colima forward broke — mini-forward-down catches it
  METRIC ONLY       the host was fine, only this rule's series was absent — noise
Used as the acceptance replay for setting noDataState: OK (fix #4, 2026-09-30).

  nodata_replay.py episodes.json [--vm http://localhost:8428]
"""
import collections
import datetime
import json
import sys
import urllib.parse
import urllib.request

# rule title -> the host whose data it reads
HOST = {
    "Mac mini CPU temp critical (>95°C)": "homelab",
    "Mac mini CPU temp high (>85°C)": "homelab",
    "Delivery events poller stalled (cursor age >1h)": "homelab",
    "LiteLLM gateway down (stack exporter gone)": "homelab",
    "Delivery worker down (up==0)": "homelab",
    "Langfuse trace-export down (LiteLLM keys rejected)": "homelab",
    "Delivery bounce/complaint rate high (>5%)": "homelab",
    "Delivery dead-letter in the last hour": "homelab",
    "Scrape target down (up==0)": "homelab",
    "Host disk low (<10% free)": "homelab",
    "Host disk critical (<5% free)": "homelab",
    "Podcast pipeline jobs failing": "prod-podcast",
    "Enricher failing on prod": "prod-podcast",
    "FastAPI 5xx errors elevated": "prod-podcast",
    "DGX per-process GPU metrics stale (no push in 10m)": "dgx-llm-1",
}


def query(vm, expr, t):
    url = f"{vm}/api/v1/query?" + urllib.parse.urlencode({"query": expr, "time": t})
    res = json.load(urllib.request.urlopen(url, timeout=15))["data"]["result"]
    return float(res[0]["value"][1]) if res else None


def classify(vm, rule, t):
    host = HOST.get(rule)
    if not host:
        return "UNMAPPED"
    samples = query(vm, f'sum(count_over_time(node_load1{{instance="{host}"}}[10m]))', t)
    if not samples:
        return "HOST DARK"
    if host == "homelab":
        fwd = query(vm, 'sum(count_over_time(mini_forward_up{box="mini"}[5m]))', t)
        fwd_min = query(vm, 'min(min_over_time(mini_forward_up{box="mini"}[10m]))', t)
        if not fwd or fwd_min == 0:
            return "FORWARD DOWN"
    return "METRIC ONLY"


def main():
    eps = json.load(open(sys.argv[1]))
    vm = sys.argv[sys.argv.index("--vm") + 1] if "--vm" in sys.argv else "http://localhost:8428"
    per_rule = collections.defaultdict(collections.Counter)
    detail = []
    for e in eps:
        c = classify(vm, e["rule"], e["t"])
        per_rule[e["rule"]][c] += 1
        detail.append((e["t"], e["rule"], c))
    total = collections.Counter()
    for rule, c in sorted(per_rule.items(), key=lambda kv: -sum(kv[1].values())):
        total.update(c)
        print(f"{sum(c.values()):3}  {rule[:52]:<52} " + "  ".join(f"{k}={v}" for k, v in sorted(c.items())))
    print(f"\nTOTAL {sum(total.values())}: " + "  ".join(f"{k}={v}" for k, v in sorted(total.items())))
    print("\nHOST DARK / FORWARD DOWN episodes (must stay caught by a dead-man after the fix):")
    for t, rule, c in sorted(detail):
        if c in ("HOST DARK", "FORWARD DOWN"):
            print(f"  {datetime.datetime.utcfromtimestamp(t):%m-%d %H:%M}  {c:<13} {rule}")


if __name__ == "__main__":
    main()
