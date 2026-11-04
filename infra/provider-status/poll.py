#!/usr/bin/env python3
"""Provider status pages (GitHub, OpenRouter, ...), correlated with what of each we use, every 5 minutes.

The family of infra/hetzner-status (its log, banner and alert model) and cloudflare-edge's status part, for
the providers whose outages look like our own failures. providers.json lists them, each with a reader type:
  statuspage  Atlassian Statuspage's summary.json (components, unresolved incidents, scheduled maintenance)
  rss         a status page's RSS history (category incident|maintenance; the newest update's state word)

Per provider, an item is an incident (outage) or maintenance (planned, upfront), with relevance direct (it
touches what we use) or other. Outputs (label provider = the providers.json key):
  - VictoriaLogs: one line per new or updated item, stream app=provider-status. Fields: provider, kind,
    relevance, name, status, impact, components, link, start, end, last_update, backfill (true = already
    there when watching started; never alerts). The alert rule provider-status-ours reads these.
  - VictoriaMetrics, re-pushed every poll while true (read with last_over_time(...[15m])):
      provider_status_active{provider,kind,relevance,phase,name,impact,status,components,start,end,link} 1
          an incident not resolved (phase=ongoing), maintenance in progress (ongoing) or announced and not
          started (upcoming; statuspage: starting within PROVIDER_UPCOMING_DAYS)
      provider_status_component{provider,name,status} 1      (statuspage) a component of ours not operational
      provider_status_indicator{provider,indicator,description} 1   (statuspage)
      provider_status_poll_ok{provider}, provider_status_last_success_timestamp{provider}

Stdlib only, read-only towards the providers. Run once: python3 poll.py --once. Tests: test_poll.py.
"""
import html
import json
import os
import re
import sys
import time
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

HERE = os.path.dirname(os.path.abspath(__file__))
VLOGS = os.environ.get("VLOGS_URL", "http://localhost:9428").rstrip("/")
VM = os.environ.get("VM_IMPORT_URL", "http://localhost:8428/api/v1/import/prometheus")
STATE_FILE = os.environ.get("STATE_FILE", os.path.join(HERE, "state.json"))
INTERVAL = int(os.environ.get("POLL_INTERVAL", "300"))
UPCOMING = timedelta(days=int(os.environ.get("PROVIDER_UPCOMING_DAYS", "7")))
ONCE = "--once" in sys.argv
ENDED = {"resolved", "completed", "postmortem"}


def load_providers(path=os.path.join(HERE, "providers.json")):
    with open(path) as f:
        return json.load(f)["providers"]


def _ts(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00")) if s else None


# ---- statuspage (summary.json) ---------------------------------------------------------------------
def statuspage_items(summary, ours, now=None):
    now = now or datetime.now(timezone.utc)
    out = []
    for kind, key in (("incident", "incidents"), ("maintenance", "scheduled_maintenances")):
        for i in summary.get(key, []):
            comps = [c["name"] for c in i.get("components", [])]
            hit = [c for c in comps if c in ours]
            start = i.get("scheduled_for") if kind == "maintenance" else (i.get("started_at") or i.get("created_at"))
            if kind == "incident" or i.get("status") == "in_progress":
                phase = "ongoing"
            elif _ts(start) and _ts(start) - now <= UPCOMING:
                phase = "upcoming"
            else:
                phase = None
            updates = i.get("incident_updates") or []
            out.append({"id": i["id"], "updated": i.get("updated_at") or "", "kind": kind,
                        "relevance": "direct" if hit else "other", "phase": phase,
                        "name": i.get("name", ""), "impact": i.get("impact", ""), "status": i.get("status", ""),
                        "components": ", ".join((hit or comps)[:5]), "link": i.get("shortlink") or "",
                        "start": start or "", "end": i.get("scheduled_until") or "",
                        "last_update": (updates[0].get("body") or "")[:400] if updates else ""})
    return out


def statuspage_lines(summary, ours):
    st = summary.get("status") or {}
    lines = [("provider_status_indicator", {"indicator": st.get("indicator", ""), "description": st.get("description", "")})]
    for c in summary.get("components", []):
        if c["name"] in ours and c.get("status") != "operational":
            lines.append(("provider_status_component", {"name": c["name"], "status": c["status"]}))
    return lines


# ---- rss (status page history) ---------------------------------------------------------------------
UPD = re.compile(r"<small>(.*?)</small>\s*<br\s*/?>\s*<strong>(.*?)</strong>\s*-\s*(.*?)</p>", re.S)


def rss_items(xml_text, cfg):
    other_title = re.compile(cfg["other_title"]) if cfg.get("other_title") else None
    other_text = re.compile(cfg["other_text"]) if cfg.get("other_text") else None
    out = []
    for it in ET.fromstring(xml_text).iter("item"):
        title, link = (it.findtext("title") or "").strip(), (it.findtext("link") or "").strip()
        kind = "maintenance" if (it.findtext("category") or "").strip().lower() == "maintenance" else "incident"
        desc = html.unescape(it.findtext("description") or "")
        ups = [(w.strip(), re.sub(r"<[^>]+>", "", s).strip(), re.sub(r"<[^>]+>", " ", t).strip()) for w, s, t in UPD.findall(desc)]
        state = ups[0][1] if ups else ""
        latest = state.lower()
        if latest in ENDED:
            phase = None
        elif kind == "maintenance":
            phase = "ongoing" if latest == "in progress" else ("upcoming" if latest == "scheduled" else None)
        else:
            phase = "ongoing"
        pub = it.findtext("pubDate") or ""
        try:
            pub_iso = parsedate_to_datetime(pub).astimezone(timezone.utc).isoformat()
        except (TypeError, ValueError):
            pub_iso = ""
        text = " ".join(u[2] for u in ups)
        mark_other = bool((other_title and other_title.search(title)) or (other_text and other_text.search(text)))
        out.append({"id": (it.findtext("guid") or link or title).strip(), "updated": pub_iso + "|" + state, "kind": kind,
                    "relevance": "other" if mark_other else "direct", "phase": phase, "name": title, "impact": "",
                    "status": state, "components": "", "link": link, "start": "", "end": "",
                    "last_update": (ups[0][2] if ups else "")[:400], "updated_at": pub_iso})
    return out


# ---- shared ----------------------------------------------------------------------------------------
def _lv(s):
    return str(s).replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")


def _m(name, labels, value):
    return "%s{%s} %s" % (name, ",".join('%s="%s"' % (k, _lv(v)) for k, v in labels.items()), value)


def fetch(url):
    return urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "homelab-provider-status"}), timeout=30).read().decode()


def read_provider(key, cfg, get=fetch, now=None):
    """(items, extra metric (name, labels) pairs) for one provider."""
    text = get(cfg["url"])
    if cfg["type"] == "statuspage":
        summary = json.loads(text)
        ours = set(cfg.get("components", []))
        return statuspage_items(summary, ours, now), statuspage_lines(summary, ours)
    if cfg["type"] == "rss":
        return rss_items(text, cfg), []
    raise ValueError("unknown provider type %r" % cfg["type"])


def metric_lines(key, ok, its, extra):
    lines = [_m("provider_status_poll_ok", {"provider": key}, 1 if ok else 0)]
    if not ok:
        return lines
    lines.append(_m("provider_status_last_success_timestamp", {"provider": key}, int(time.time())))
    lines += [_m(n, dict({"provider": key}, **l), 1) for n, l in extra]
    for it in its:
        if it["phase"]:
            lines.append(_m("provider_status_active", dict({"provider": key}, **{k: it[k] for k in
                            ("kind", "relevance", "phase", "name", "impact", "status", "components", "start", "end", "link")}), 1))
    return lines


def new_events(state, key, its):
    """Log lines for this provider's new or changed items. A provider's first run (no state) = backfill."""
    seen_all = state.setdefault("seen", {})
    first = key not in seen_all
    seen = seen_all.setdefault(key, {})
    now = datetime.now(timezone.utc).isoformat()
    events = []
    for it in its:
        if seen.get(it["id"]) == it["updated"]:
            continue
        seen[it["id"]] = it["updated"]
        ev = {k: v for k, v in it.items() if k not in ("phase", "updated")}
        ev.update({"_time": now, "provider": key,
                   "_msg": "%s %s [%s] %s (%s)" % (key, it["kind"], it["components"] or "-", it["name"], it["status"]),
                   "app": "provider-status", "service": "provider-status", "environment": "operations", "instance": "homelab",
                   "backfill": "true" if first else "false"})
        events.append(ev)
    current = {it["id"] for it in its}
    seen_all[key] = {k: v for k, v in seen.items() if k in current}
    return events


def _post(url, body, ctype):
    urllib.request.urlopen(urllib.request.Request(url, data=body, method="POST", headers={"Content-Type": ctype}), timeout=15).read()


def emit(events, lines):
    if events:
        _post(VLOGS + "/insert/jsonline?_stream_fields=app,service,environment,instance&_time_field=_time&_msg_field=_msg",
              "\n".join(json.dumps(e) for e in events).encode(), "application/stream+json")
    _post(VM + "?extra_label=instance=homelab&extra_label=service=provider-status&extra_label=environment=operations",
          ("\n".join(lines) + "\n").encode(), "text/plain")


def load_state():
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_state(state):
    tmp = STATE_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(state, f)
    os.replace(tmp, STATE_FILE)


def main():
    providers = load_providers()
    while True:
        state = load_state()
        events, lines, report = [], [], []
        for key, cfg in providers.items():
            try:  # one provider failing never stops the others
                its, extra = read_provider(key, cfg)
                events += new_events(state, key, its)
                lines += metric_lines(key, True, its, extra)
                report.append("%s ok active=%d" % (key, sum(1 for i in its if i["phase"])))
            except Exception as e:
                print("%s error: %r" % (key, e), file=sys.stderr, flush=True)
                lines += metric_lines(key, False, [], [])
                report.append("%s FAILED" % key)
        try:
            emit(events, lines)
            save_state(state)
        except Exception as e:
            print("push error: %r" % e, file=sys.stderr, flush=True)
        print("[%s] %s | new=%d %s" % (datetime.now(timezone.utc).isoformat(timespec="seconds"), "; ".join(report), len(events),
              [(e["provider"], e["kind"], e["relevance"], e["name"][:40]) for e in events]), flush=True)
        if ONCE:
            break
        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()
