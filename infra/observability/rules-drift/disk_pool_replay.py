#!/usr/bin/env python3
"""Disk-alert replay: per-mountpoint grouping vs per-disk grouping, on real history.

The mini mounts one APFS container as six volumes that all report the container's
free space, so `min by (instance, mountpoint)` turned one full disk into six alerts,
and the triage fleet into six issues (#42-#47, 2026-08-25 and 2026-10-01). The fix
groups by `disk`: the APFS container (disk1) on macOS, the device elsewhere.

Both rule versions are evaluated against VictoriaMetrics over a fixed window, with
each rule's own threshold and `for:` duration (a series fires once its condition has
held for `for` at a 1-minute step, the way Grafana evaluates), giving firing
episodes per alert series. Pass:
  - no lost detection: every old episode on an instance overlaps a new one there;
  - no new noise: every new episode overlaps an old one on the same instance;
  - no fan-out: never two firing series on one instance reporting the identical free
    ratio at the same moment (one disk counted twice). The old rule must show it;
    the new rule must have none.

  disk_pool_replay.py OLD_RULES.yaml NEW_RULES.yaml [--vm http://localhost:8428]
                      [--start 2026-08-15T00:00:00] [--end now]
"""
import argparse
import datetime
import json
import subprocess
import sys
import urllib.parse
import urllib.request

UIDS = ("infra-disk-low", "infra-disk-crit")
STEP = 60
CHUNK = 7 * 86400


def load_rules(path):
    text = open(path).read()
    try:
        import yaml
        doc = yaml.safe_load(text)
    except ImportError:                      # the mini's python3: parse with system Ruby
        out = subprocess.run(["/usr/bin/ruby", "-ryaml", "-rjson", "-e",
                              "puts YAML.safe_load(STDIN.read).to_json"],
                             input=text, capture_output=True, text=True, check=True).stdout
        doc = json.loads(out)
    rules = {r["uid"]: r for g in doc["groups"] for r in g["rules"]}
    out = {}
    for uid in UIDS:
        r = rules[uid]
        expr = next(d["model"]["expr"] for d in r["data"] if d["refId"] == "q")
        thr = next(d["model"]["conditions"][0]["evaluator"]["params"][0]
                   for d in r["data"] if d["refId"] == "threshold")
        out[uid] = (expr, float(thr), _seconds(r["for"]))
    return out


def _seconds(s):
    return int(s[:-1]) * {"s": 1, "m": 60, "h": 3600}[s[-1]]


def series(vm, expr, start, end):
    """{label-key: {t: value}} over [start, end] at STEP, fetched in CHUNK pieces."""
    res = {}
    t = start
    while t < end:
        q = urllib.parse.urlencode({"query": expr, "start": t, "end": min(t + CHUNK, end), "step": STEP})
        for r in json.load(urllib.request.urlopen(f"{vm}/api/v1/query_range?{q}", timeout=120))["data"]["result"]:
            key = tuple(sorted(r["metric"].items()))
            res.setdefault(key, {}).update({int(float(ts)): float(v) for ts, v in r["values"]})
        t += CHUNK
    return res


def episodes(data, thr, for_s):
    """[(key, instance, fire_start, fire_end)]: the condition held for for_s at STEP; a
    missing sample breaks the run (noDataState: OK)."""
    eps = []
    for key, pts in data.items():
        inst = dict(key).get("instance", "")
        run_start, prev, firing = None, None, None
        for t in sorted(pts):
            below = pts[t] < thr
            if below and prev is not None and t - prev == STEP and run_start is not None:
                pass
            elif below:
                run_start = t
            else:
                run_start = None
            if run_start is not None and t - run_start >= for_s:
                if firing is None:
                    firing = [run_start + for_s, t]
                firing[1] = t
            elif firing is not None:
                eps.append((key, inst, firing[0], firing[1]))
                firing = None
            prev = t
        if firing is not None:
            eps.append((key, inst, firing[0], firing[1]))
    return eps


def fanout(data, thr):
    """Instance-minutes where 2+ series below the threshold carry the same value: one
    disk reported as several alert series."""
    by = {}
    for key, pts in data.items():
        inst = dict(key).get("instance", "")
        for t, v in pts.items():
            if v < thr:
                by.setdefault((inst, t), []).append(round(v, 9))
    return sum(1 for vals in by.values() if len(vals) != len(set(vals)))


def _overlaps(a, others):
    return any(o[1] == a[1] and o[2] <= a[3] and a[2] <= o[3] for o in others)


def _ts(t):
    return datetime.datetime.utcfromtimestamp(t).strftime("%m-%d %H:%M")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("old_rules")
    ap.add_argument("new_rules")
    ap.add_argument("--vm", default="http://localhost:8428")
    ap.add_argument("--start", default="2026-08-15T00:00:00")
    ap.add_argument("--end", default="")
    a = ap.parse_args()
    start = int(datetime.datetime.strptime(a.start, "%Y-%m-%dT%H:%M:%S")
                .replace(tzinfo=datetime.timezone.utc).timestamp())
    end = int(datetime.datetime.strptime(a.end, "%Y-%m-%dT%H:%M:%S")
              .replace(tzinfo=datetime.timezone.utc).timestamp()) if a.end else int(datetime.datetime.now().timestamp())
    old, new = load_rules(a.old_rules), load_rules(a.new_rules)
    fails = []
    print(f"Disk-alert replay {_ts(start)} -> {_ts(end)} UTC, {STEP}s step\n")
    for uid in UIDS:
        (oe, othr, ofor), (ne, nthr, nfor) = old[uid], new[uid]
        od, nd = series(a.vm, oe, start, end), series(a.vm, ne, start, end)
        oep, nep = episodes(od, othr, ofor), episodes(nd, nthr, nfor)
        print(f"{uid}  (<{nthr:.0%} for {nfor // 60}m)")
        print(f"  alert series   old {len(od):3d}   new {len(nd):3d}")
        print(f"  firing series  old {len(oep):3d}   new {len(nep):3d}")
        ofan, nfan = fanout(od, othr), fanout(nd, nthr)
        print(f"  fan-out minutes (one disk, several series)  old {ofan}   new {nfan}")
        if nfan:
            fails.append(f"{uid}: new rule still reports one disk as several series ({nfan} min)")
        for e in sorted(nep, key=lambda e: e[2]):
            same = [o for o in oep if o[1] == e[1] and o[2] <= e[3] and e[2] <= o[3]]
            print(f"    {e[1]:<13} {dict(e[0]).get('disk', '?'):<16} {_ts(e[2])} -> {_ts(e[3])}"
                  f"   old fired as {len(same)} series")
        lost = [o for o in oep if not _overlaps(o, nep)]
        noise = [n for n in nep if not _overlaps(n, oep)]
        for o in lost:
            fails.append(f"{uid}: lost detection {o[1]} {dict(o[0]).get('mountpoint')} {_ts(o[2])}")
        for n in noise:
            fails.append(f"{uid}: new-only firing {n[1]} {dict(n[0]).get('disk')} {_ts(n[2])}")
        print()
    print("PASS" if not fails else "FAIL:\n  " + "\n  ".join(fails))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
