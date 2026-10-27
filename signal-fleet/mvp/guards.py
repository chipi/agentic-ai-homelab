"""Deterministic container facts the triager cannot argue past (2026-10-27).

Two misses on prod-podcast, 2026-10-26/27:
- "Kernel OOM killer fired" is one alert per host. While evals-inspector was OOM-killed
  every ~5 min the alert never stopped firing, so player-api's kills (10-26 13:46:07,
  13:46:31; 10-27 07:13:37) never produced a new occurrence. `oom_killed_containers`
  names the containers so the alert splits into one signal per container.
- An edge-5xx burst caused by those kills was dismissed on probes run after the api had
  restarted. `restarts_near` finds container starts and OOM kills around a burst so the
  dismiss gate can refuse.

Both take a `data` object (live by default, frozen in the replay) so the decisions
replay without network.
"""
import calendar
import json
import re
import time

import correlate

OOM_ALERT = "Kernel OOM killer fired"
EDGE_5XX_PREFIX = "Edge 5xx burst"
_CID = re.compile(r"task_memcg=/system\.slice/docker-([0-9a-f]{64})\.scope")
_FMT = "%Y-%m-%dT%H:%M:%SZ"


def _ts(s):
    return calendar.timegm(time.strptime(s[:19], "%Y-%m-%dT%H:%M:%S"))


class Live:
    """Reads VictoriaLogs (kernel lines) and VictoriaMetrics (cadvisor) through correlate."""

    def oom_kills(self, instance, start, end):
        txt = correlate.vl_query(
            f'_time:[{start}, {end}] instance:"{instance}" "oom-kill:" | fields _time, _msg')
        out = []
        for line in (txt or "").splitlines():
            try:
                r = json.loads(line)
            except ValueError:
                continue
            m = _CID.search(r.get("_msg", ""))
            out.append({"t": r.get("_time", "")[:19] + "Z", "cid": m.group(1) if m else None})
        return out

    def container_name(self, instance, cid):
        r = correlate.vm_query(
            f'max by (name) (last_over_time(container_start_time_seconds'
            f'{{instance="{instance}",id=~".*docker-{cid}.scope"}}[2d]))')
        res = (r.get("data") or {}).get("result") or []
        return res[0]["metric"].get("name") if res else None

    def container_starts(self, instance, start, end):
        r = correlate.vm_query(
            f'last_over_time(container_start_time_seconds{{instance="{instance}",name!=""}}[2d])')
        lo, hi = _ts(start), _ts(end)
        out = []
        for s in (r.get("data") or {}).get("result") or []:
            v = int(float(s["value"][1]))
            if lo <= v <= hi:
                out.append({"name": s["metric"].get("name"), "start": time.strftime(_FMT, time.gmtime(v))})
        return out


def oom_killed_containers(instance, start, end, data=None):
    """Sorted names of containers the kernel OOM-killed on `instance` in [start, end].
    A kill outside any docker cgroup is reported as 'host'; an unmapped id as 'cid:<12>'."""
    data = data or Live()
    names = set()
    for k in data.oom_kills(instance, start, end):
        if not k.get("cid"):
            names.add("host")
            continue
        names.add(data.container_name(instance, k["cid"]) or f"cid:{k['cid'][:12]}")
    return sorted(names)


EPISODE_GAP_S = 1800      # kills of one container closer than this are one episode
EPISODE_LOOKBACK_S = 6 * 3600


def oom_episodes(instance, now, recent_s=900, data=None):
    """{container: episode_start} for containers OOM-killed on `instance` in the last
    `recent_s` seconds. An episode is a run of kills less than EPISODE_GAP_S apart; its
    start is the occurrence key, so a crash loop stays ONE occurrence (no row per cycle)
    while the same container dying again after a quiet gap is a new one. A chain that
    reaches the lookback edge returns None: the caller keys it on the alert's own start."""
    data = data or Live()
    lo = now - EPISODE_LOOKBACK_S
    kills = {}
    for k in data.oom_kills(instance, time.strftime(_FMT, time.gmtime(lo)), time.strftime(_FMT, time.gmtime(now))):
        name = "host" if not k.get("cid") else (data.container_name(instance, k["cid"]) or f"cid:{k['cid'][:12]}")
        kills.setdefault(name, []).append(_ts(k["t"]))
    out = {}
    for name, ts in kills.items():
        ts.sort()
        if ts[-1] < now - recent_s:
            continue
        i = len(ts) - 1
        while i > 0 and ts[i] - ts[i - 1] < EPISODE_GAP_S:
            i -= 1
        start = ts[i]
        out[name] = None if start - lo < EPISODE_GAP_S else time.strftime(_FMT, time.gmtime(start))
    return out


def restarts_near(instance, at, before_s=600, after_s=300, data=None):
    """Containers that started or were OOM-killed on `instance` within
    [at - before_s, at + after_s]: the burst's likely cause, whatever later probes say."""
    data = data or Live()
    t = _ts(at)
    start = time.strftime(_FMT, time.gmtime(t - before_s))
    end = time.strftime(_FMT, time.gmtime(t + after_s))
    found = set(oom_killed_containers(instance, start, end, data))
    found |= {s["name"] for s in data.container_starts(instance, start, end)}
    return sorted(found)
