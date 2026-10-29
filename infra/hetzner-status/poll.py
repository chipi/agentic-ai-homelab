#!/usr/bin/env python3
"""Hetzner status bulletins -> VictoriaLogs (+ health metrics in VictoriaMetrics).

Hetzner publishes incidents and maintenance on https://status.hetzner.com/ with an Atom feed
(en.atom). There is no alerts API. This poller reads the feed every POLL_INTERVAL and writes
one event per new or updated bulletin to VictoriaLogs (app=hetzner-status), with the fields
an alert or a panel needs: title, category, location, relevance, kind, start, end, link.

`relevance` correlates each bulletin with where prod runs (ours.json):
  direct  — our exact datacenter (NBG1-DC3), a whole-location bulletin for the server's location
            (NBG1), or a bulletin whose text names one of our datacenters
  nearby  — same city, other or unknown datacenter (other NBG1 DCs; FSN1, the Storage Box's city)
  service — a Hetzner service we use (Cloud Server, Network, …), not tied to a place
  other   — everything else
Only `direct` alerts (rules.yaml, group hetzner-status). Every poll also publishes
hetzner_status_active{…} for direct/nearby bulletins that are ongoing or start within 7 days,
and for service bulletins while ongoing; the hub page draws its Hetzner bar from it.

Each update of a bulletin is its own Atom entry (id suffix /0, /1, …), so an update is a new
event. The first run marks the feed's current entries `backfill=true`, so rules can skip the
history instead of alerting on months-old notices.

stdlib only; runs under launchd on the mini like ci-ops-poller.
"""
import json
import os
import re
import sys
import time
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
FEED = os.environ.get("HETZNER_STATUS_FEED", "https://status.hetzner.com/en.atom")
VLOGS = os.environ.get("VLOGS_URL", "http://localhost:9428").rstrip("/")
VM = os.environ.get("VM_IMPORT_URL", "http://localhost:8428/api/v1/import/prometheus")
STATE_FILE = os.environ.get("STATE_FILE", os.path.join(HERE, "state.json"))
INTERVAL = int(os.environ.get("POLL_INTERVAL", "600"))
ONCE = "--once" in sys.argv
A = "{http://www.w3.org/2005/Atom}"
UPCOMING = timedelta(days=int(os.environ.get("HETZNER_UPCOMING_DAYS", "7")))
OPEN_ENDED = timedelta(hours=int(os.environ.get("HETZNER_OPEN_ENDED_HOURS", "72")))


def load_ours(path=os.path.join(HERE, "ours.json")):
    with open(path) as f:
        o = json.load(f)
    return {"dcs": [d.upper() for d in o["datacenters"]], "server_locs": [l.upper() for l in o["server_locations"]],
            "nearby": [l.upper() for l in o["nearby_locations"]], "services": [s.lower() for s in o["services"]]}


OURS = load_ours()


def classify(categories, title, text="", ours=None):
    """-> (relevance, matched category, kind). See the module docstring for the levels."""
    o = ours or OURS
    cats = [c.upper() for c in categories]
    blob = (title + " " + text).upper()
    loc = next((c for c in cats if c in o["dcs"] or c in o["server_locs"]), "")
    named = next((d for d in o["dcs"] if re.search(r"\b%s\b" % re.escape(d), blob)), "")
    if loc or named:
        relevance = "direct"
        loc = loc or named
    else:
        loc = next((c for c in cats for l in o["nearby"] if c == l or c.startswith(l + "-")), "")
        if loc:
            relevance = "nearby"
        elif any(c.lower() in o["services"] for c in categories):
            relevance = "service"
        else:
            relevance = "other"
    kind = "maintenance" if re.search(r"maintenance|wartung", title, re.I) else "incident"
    return relevance, loc, kind


def _ts(s):
    try:
        return datetime.fromisoformat(s) if s else None
    except ValueError:
        return None


def phase(b, now=None):
    """'ongoing' | 'upcoming' | None. Ongoing: started and not ended; a bulletin with no end
    counts as ongoing for OPEN_ENDED after its start (Hetzner rarely posts an end and leaves
    notices in the feed for months). Upcoming: starts within UPCOMING."""
    now = now or datetime.now(timezone.utc)
    start, end = _ts(b["start"]), _ts(b["end"])
    if start is None:
        return None
    if start > now:
        return "upcoming" if start - now <= UPCOMING else None
    if end is not None:
        return "ongoing" if now < end else None
    return "ongoing" if now - start <= OPEN_ENDED else None


def active(bulletins, now=None):
    """Bulletins worth a banner: direct/nearby ongoing or upcoming; service only while ongoing."""
    out = []
    for b in bulletins:
        p = phase(b, now)
        if p and (b["relevance"] in ("direct", "nearby") or (b["relevance"] == "service" and p == "ongoing")):
            out.append(dict(b, phase=p))
    return out


def parse(xml_text):
    """Atom text -> list of bulletin dicts (feed order)."""
    root = ET.fromstring(xml_text)
    out = []
    for e in root.findall(A + "entry"):
        title = (e.findtext(A + "title") or "").strip()
        cats = [c.get("term", "") for c in e.findall(A + "category") if c.get("term")]
        link = next((l.get("href") for l in e.findall(A + "link") if l.get("href")), "")
        content = e.find(A + "content")
        # join element texts with a space: adjacent <p>s would otherwise run "…+00:00End: …" together
        text = " ".join(" ".join(content.itertext()).split()) if content is not None else ""
        start = re.search(r"Start:\s*(\S+)", text)
        end = re.search(r"End:\s*(\S+)", text)
        relevance, loc, kind = classify(cats, title, text)
        out.append({
            "entry_id": (e.findtext(A + "id") or "").strip(),
            "updated": (e.findtext(A + "updated") or "").strip(),
            "title": title,
            "category": ", ".join(cats),
            "location": loc,
            "relevance": relevance,
            "kind": kind,
            "start": start.group(1) if start else "",
            "end": end.group(1) if end else "",
            "link": link,
            "summary": re.sub(r"\b(Start|End):\s*\S+\s*", "", text).strip()[:600],
        })
    return out


def to_event(b, backfill):
    ev = dict(b)
    ev.update({
        # observation time, not b["updated"]: bulletins stay in the feed for months, and VictoriaLogs
        # drops rows older than its retention, so an old notice that is still current would vanish.
        "_time": datetime.now(timezone.utc).isoformat(),
        "_msg": "hetzner %s [%s] %s" % (b["kind"], b["category"] or "-", b["title"]),
        "app": "hetzner-status", "service": "hetzner-status",
        "environment": "operations", "instance": "homelab",
        "backfill": "true" if backfill else "false",
    })
    return ev


def emit_logs(events):
    if not events:
        return
    body = "\n".join(json.dumps(e) for e in events).encode()
    url = VLOGS + "/insert/jsonline?_stream_fields=app,service,environment,instance&_time_field=_time&_msg_field=_msg"
    req = urllib.request.Request(url, data=body, method="POST", headers={"Content-Type": "application/stream+json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        r.read()


def _lv(s):
    return str(s).replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")


def metric_lines(ok, bulletins, now=None):
    counts = {"direct": 0, "nearby": 0, "service": 0, "other": 0}
    for b in bulletins:
        counts[b["relevance"]] += 1
    lines = ["hetzner_status_poll_ok %d" % (1 if ok else 0)]
    if ok:
        lines.append("hetzner_status_last_success_timestamp %d" % int(time.time()))
        lines += ['hetzner_status_feed_entries{relevance="%s"} %d' % (k, v) for k, v in counts.items()]
        for b in active(bulletins, now):
            labels = ",".join('%s="%s"' % (k, _lv(b[k])) for k in ("relevance", "phase", "kind", "category", "title", "start", "end", "link"))
            lines.append("hetzner_status_active{%s} 1" % labels)
    return lines


def emit_metrics(ok, bulletins):
    lines = metric_lines(ok, bulletins)
    url = VM + "?extra_label=instance=homelab&extra_label=service=hetzner-status&extra_label=environment=operations"
    try:
        urllib.request.urlopen(urllib.request.Request(url, data=("\n".join(lines) + "\n").encode(), method="POST"), timeout=10).read()
    except Exception as e:  # metrics are best effort; the poll result is in the log line
        print("metrics push failed: %r" % e, file=sys.stderr, flush=True)


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


def poll_once(state, fetch=None):
    """Returns (new_events, bulletins). `seen` maps entry_id -> updated; an entry is emitted
    when its id is new or its `updated` changed. First run (no state) = backfill."""
    text = fetch() if fetch else urllib.request.urlopen(
        urllib.request.Request(FEED, headers={"User-Agent": "homelab-hetzner-status"}), timeout=30).read().decode()
    bulletins = parse(text)
    # HETZNER_BACKFILL=1 forces a backfill run (re-adding rows without alerting)
    first = "seen" not in state or os.environ.get("HETZNER_BACKFILL") == "1"
    seen = state.setdefault("seen", {})
    events = []
    for b in bulletins:
        if seen.get(b["entry_id"]) != b["updated"]:
            events.append(to_event(b, backfill=first))
            seen[b["entry_id"]] = b["updated"]
    # keep only ids still in the feed, so the state cannot grow without bound
    current = {b["entry_id"] for b in bulletins}
    state["seen"] = {k: v for k, v in seen.items() if k in current}
    return events, bulletins


def main():
    while True:
        state = load_state()
        try:
            events, bulletins = poll_once(state)
            emit_logs(events)
            save_state(state)
            emit_metrics(True, bulletins)
            print("[%s] feed=%d new=%d %s" % (datetime.now(timezone.utc).isoformat(timespec="seconds"), len(bulletins),
                  len(events), [(e["relevance"], e["title"][:50]) for e in events]), flush=True)
        except Exception as e:  # keep the daemon alive; hetzner_status_poll_ok=0 shows it
            print("poll error: %r" % e, file=sys.stderr, flush=True)
            emit_metrics(False, [])
        if ONCE:
            break
        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()
