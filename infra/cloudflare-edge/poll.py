#!/usr/bin/env python3
"""Cloudflare edge analytics + Cloudflare status -> VictoriaMetrics.

Every zone we run sits behind Cloudflare. Some failures never reach the prod Caddy, so its
logs cannot show them: Cloudflare answers 520-526/530 itself when it cannot get a valid
response from our origin. This poller reads, every POLL_INTERVAL:

1. Cloudflare's GraphQL analytics for every zone the token sees (free plan:
   httpRequestsAdaptiveGroups, firewallEventsAdaptive) and publishes, per zone and host,
   requests by class over the last 1h and 24h:
     2xx 3xx 4xx           as answered at the edge
     5xx_server            500-519: our server answered with an error
     5xx_unreachable       520-526, 530: Cloudflare could not reach / handshake / read our origin
     client_closed         499: the client gave up before an answer
   plus the 24h share of our requests per Cloudflare PoP, and security events (24h).
   The windows end 2 minutes ago: the adaptive datasets fill in with about a minute's delay.
2. https://www.cloudflarestatus.com/api/v2/summary.json, correlated with ours.json: a service
   component we use, or a PoP that is ours (listed, or carrying >= pop_share_min of our
   traffic). Its page always lists dozens of degraded PoPs worldwide; only ours count.

Metrics (instance=homelab, service=cloudflare-edge):
  cloudflare_edge_requests{zone,host,class,window}        count
  cloudflare_edge_5xx{zone,host,status,window}            count per 5xx/499 status
  cloudflare_edge_pop_share{colo}                         0..1, top PoPs over 24h
  cloudflare_security_events{zone,action,source}          count over 24h
  cloudflare_status_indicator{indicator,description}      1
  cloudflare_status_component{kind,name,status}           1 per ours that is not operational
  cloudflare_status_incident{relevance,name,impact,status,components,link}   1 per unresolved
  cloudflare_status_maintenance{name,status,start,end,components,link}       1 per ours, in
                                                          progress or starting within 24h
  cloudflare_poll_ok{part}, cloudflare_last_success_timestamp{part}   part = edge | status

Token: read-only Cloudflare API token in CF_ENV_FILE (default ~/.config/cloudflare/readonly.env,
mode 600, CLOUDFLARE_API_TOKEN=...). stdlib only; runs under launchd on the mini.
"""
import json
import os
import re
import stat
import sys
import time
import urllib.request
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
API = "https://api.cloudflare.com/client/v4"
STATUS_URL = os.environ.get("CF_STATUS_URL", "https://www.cloudflarestatus.com/api/v2/summary.json")
ENV_FILE = os.path.expanduser(os.environ.get("CF_ENV_FILE", "~/.config/cloudflare/readonly.env"))
VM = os.environ.get("VM_IMPORT_URL", "http://localhost:8428/api/v1/import/prometheus")
INTERVAL = int(os.environ.get("POLL_INTERVAL", "300"))
ONCE = "--once" in sys.argv
LAG = timedelta(minutes=2)
UA = "homelab-cloudflare-edge"


def load_ours(path=os.path.join(HERE, "ours.json")):
    with open(path) as f:
        o = json.load(f)
    return {"services": set(o["services"]), "pops": set(o["pops"]), "pop_share_min": float(o["pop_share_min"])}


def load_token(path=ENV_FILE):
    mode = stat.S_IMODE(os.stat(path).st_mode)
    if mode & 0o077:
        raise SystemExit("%s must be mode 600 (is %o)" % (path, mode))
    with open(path) as f:
        for line in f:
            if line.startswith("CLOUDFLARE_API_TOKEN="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise SystemExit("CLOUDFLARE_API_TOKEN missing in %s" % path)


def status_class(s):
    s = int(s)
    if s == 499:
        return "client_closed"
    if 520 <= s <= 526 or s == 530:
        return "5xx_unreachable"
    if s >= 500:
        return "5xx_server"
    if s >= 400:
        return "4xx"
    if s >= 300:
        return "3xx"
    return "2xx"


def pop_code(name):
    m = re.search(r"\(([A-Z]{3})\)\s*$", name)
    return m.group(1) if m else None


ZONE_QUERY = """query($z:String!,$h:Time!,$d:Time!,$u:Time!){viewer{zones(filter:{zoneTag:$z}){
  h1: httpRequestsAdaptiveGroups(limit:5000, filter:{datetime_geq:$h, datetime_lt:$u}){count dimensions{clientRequestHTTPHost edgeResponseStatus}}
  d1: httpRequestsAdaptiveGroups(limit:5000, filter:{datetime_geq:$d, datetime_lt:$u}){count dimensions{clientRequestHTTPHost edgeResponseStatus}}
  colo: httpRequestsAdaptiveGroups(limit:500, filter:{datetime_geq:$d, datetime_lt:$u}){count dimensions{coloCode}}
  fw: firewallEventsAdaptive(limit:5000, filter:{datetime_geq:$d, datetime_lt:$u}, orderBy:[datetime_DESC]){action source}
}}}"""


def _call(token, url, body=None):
    req = urllib.request.Request(url, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Authorization": "Bearer " + token, "Content-Type": "application/json",
                                          "User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def fetch_edge(token, now=None):
    """Returns {zone_name: {"h1": [...], "d1": [...], "colo": [...], "fw": [...]}}."""
    now = now or datetime.now(timezone.utc)
    u = now - LAG
    f = lambda t: t.strftime("%Y-%m-%dT%H:%M:%SZ")
    zones = _call(token, API + "/zones?per_page=50")["result"]
    out = {}
    for z in zones:
        r = _call(token, API + "/graphql", {"query": ZONE_QUERY, "variables": {
            "z": z["id"], "h": f(u - timedelta(hours=1)), "d": f(u - timedelta(hours=24)), "u": f(u)}})
        if r.get("errors"):
            raise RuntimeError("%s: %s" % (z["name"], r["errors"][0].get("message", "")[:200]))
        out[z["name"]] = r["data"]["viewer"]["zones"][0]
    return out


def _lv(s):
    return str(s).replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")


def _m(name, labels, value):
    return "%s{%s} %s" % (name, ",".join('%s="%s"' % (k, _lv(v)) for k, v in labels.items()), value)


def edge_lines(edge):
    lines, colos = [], {}
    for zone, d in sorted(edge.items()):
        for window in ("h1", "d1"):
            wl = "1h" if window == "h1" else "24h"
            by_class, by_5xx = {}, {}
            for g in d[window]:
                host, st = g["dimensions"]["clientRequestHTTPHost"], g["dimensions"]["edgeResponseStatus"]
                k = (host, status_class(st))
                by_class[k] = by_class.get(k, 0) + g["count"]
                if int(st) >= 499 and int(st) != 0:
                    by_5xx[(host, st)] = by_5xx.get((host, st), 0) + g["count"]
            for (host, cls), n in sorted(by_class.items()):
                lines.append(_m("cloudflare_edge_requests", {"zone": zone, "host": host, "class": cls, "window": wl}, n))
            for (host, st), n in sorted(by_5xx.items()):
                lines.append(_m("cloudflare_edge_5xx", {"zone": zone, "host": host, "status": st, "window": wl}, n))
        for g in d["colo"]:
            c = g["dimensions"]["coloCode"]
            colos[c] = colos.get(c, 0) + g["count"]
        sec = {}
        for e in d["fw"]:
            k = (e["action"], e["source"])
            sec[k] = sec.get(k, 0) + 1
        for (action, source), n in sorted(sec.items()):
            lines.append(_m("cloudflare_security_events", {"zone": zone, "action": action, "source": source}, n))
    total = sum(colos.values())
    share = {c: n / total for c, n in colos.items()} if total else {}
    for c, s in sorted(share.items(), key=lambda x: -x[1])[:20]:
        lines.append(_m("cloudflare_edge_pop_share", {"colo": c}, "%.4f" % s))
    return lines, share


def our_pops(share, ours):
    return set(ours["pops"]) | {c for c, s in share.items() if s >= ours["pop_share_min"]}


def status_lines(summary, ours, pops, now=None):
    now = now or datetime.now(timezone.utc)
    lines = [_m("cloudflare_status_indicator", {"indicator": summary["status"]["indicator"],
                                                "description": summary["status"]["description"]}, 1)]
    groups = {c["id"]: c["name"] for c in summary["components"] if c.get("group")}

    def mine(c):
        if c.get("group"):
            return None
        if groups.get(c.get("group_id")) == "Cloudflare Sites and Services":
            return "service" if c["name"] in ours["services"] else None
        return "pop" if pop_code(c["name"]) in pops else None

    by_id = {c["id"]: c for c in summary["components"]}
    for c in summary["components"]:
        kind = mine(c)
        if kind and c["status"] != "operational":
            lines.append(_m("cloudflare_status_component", {"kind": kind, "name": c["name"], "status": c["status"]}, 1))
    for i in summary.get("incidents", []):
        comps = [by_id.get(c["id"], c) for c in i.get("components", [])]
        hit = [c["name"] for c in comps if mine(c)]
        lines.append(_m("cloudflare_status_incident", {
            "relevance": "direct" if hit else "other", "name": i["name"], "impact": i["impact"], "status": i["status"],
            "components": ", ".join((hit or [c["name"] for c in comps])[:4]), "link": i.get("shortlink", "")}, 1))
    for mt in summary.get("scheduled_maintenances", []):
        hit = [c["name"] for c in (by_id.get(c["id"], c) for c in mt.get("components", [])) if mine(c)]
        if not hit:
            continue
        start = datetime.fromisoformat(mt["scheduled_for"].replace("Z", "+00:00"))
        if mt["status"] != "in_progress" and start - now > timedelta(hours=24):
            continue
        lines.append(_m("cloudflare_status_maintenance", {
            "name": mt["name"], "status": mt["status"], "start": mt["scheduled_for"], "end": mt.get("scheduled_until") or "",
            "components": ", ".join(hit[:4]), "link": mt.get("shortlink", "")}, 1))
    return lines


def push(lines):
    url = VM + "?extra_label=instance=homelab&extra_label=service=cloudflare-edge&extra_label=environment=operations"
    urllib.request.urlopen(urllib.request.Request(url, data=("\n".join(lines) + "\n").encode(), method="POST"),
                           timeout=15).read()


def poll_once(token, ours):
    lines, share, ok = [], {}, {}
    try:
        el, share = edge_lines(fetch_edge(token))
        lines += el
        ok["edge"] = True
    except Exception as e:  # a failed part shows as cloudflare_poll_ok{part}=0; the other still publishes
        print("edge error: %r" % e, file=sys.stderr, flush=True)
        ok["edge"] = False
    try:
        req = urllib.request.Request(STATUS_URL, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=30) as r:
            summary = json.load(r)
        lines += status_lines(summary, ours, our_pops(share, ours))
        ok["status"] = True
    except Exception as e:
        print("status error: %r" % e, file=sys.stderr, flush=True)
        ok["status"] = False
    now = int(time.time())
    for part, good in ok.items():
        lines.append(_m("cloudflare_poll_ok", {"part": part}, 1 if good else 0))
        if good:
            lines.append(_m("cloudflare_last_success_timestamp", {"part": part}, now))
    return lines, ok


def main():
    ours = load_ours()
    token = load_token()
    while True:
        lines, ok = poll_once(token, ours)
        try:
            push(lines)
        except Exception as e:
            print("push error: %r" % e, file=sys.stderr, flush=True)
        print("[%s] ok=%s series=%d" % (datetime.now(timezone.utc).isoformat(timespec="seconds"), ok, len(lines)), flush=True)
        if ONCE:
            break
        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()
