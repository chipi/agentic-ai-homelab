#!/usr/bin/env python3
"""Hetzner status bulletins -> VictoriaLogs (+ health metrics in VictoriaMetrics).

Hetzner publishes incidents and maintenance on https://status.hetzner.com/ with an Atom feed
(en.atom). There is no alerts API. This poller reads the feed every POLL_INTERVAL and writes
one event per new or updated bulletin to VictoriaLogs (app=hetzner-status), with the fields
an alert or a panel needs: title, category, location, affects, kind, start, end, link.

`affects` classifies each bulletin against what prod uses (config below):
  ours    — a category naming one of our locations/datacenters (e.g. NBG1-DC3, FSN1-DC22)
  service — a category naming a Hetzner service we use (Cloud Server, Network, …)
  other   — everything else (other datacenters, General notices, products we don't use)
Grafana rules (rules.yaml, group hetzner-status) alert on new `ours`/`service` events.

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
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
FEED = os.environ.get("HETZNER_STATUS_FEED", "https://status.hetzner.com/en.atom")
VLOGS = os.environ.get("VLOGS_URL", "http://localhost:9428").rstrip("/")
VM = os.environ.get("VM_IMPORT_URL", "http://localhost:8428/api/v1/import/prometheus")
STATE_FILE = os.environ.get("STATE_FILE", os.path.join(HERE, "state.json"))
INTERVAL = int(os.environ.get("POLL_INTERVAL", "600"))
ONCE = "--once" in sys.argv
# prod-podcast is in nbg1 (infra/terraform variables.tf `location`), its audio Storage Box in
# fsn1 (`audio_storage_box_location`). A category like "NBG1-DC3" or "FSN1" matches.
LOCATIONS = [x.strip().upper() for x in os.environ.get("HETZNER_LOCATIONS", "NBG1,FSN1").split(",") if x.strip()]
SERVICES = [x.strip().lower() for x in os.environ.get(
    "HETZNER_SERVICES", "Cloud Server,Network,Storage Box,Cloud Volumes,Cloud Networks,Robot,Console,DNS").split(",") if x.strip()]
A = "{http://www.w3.org/2005/Atom}"


def classify(categories, title):
    cats = [c.upper() for c in categories]
    loc = next((c for c in cats for l in LOCATIONS if c == l or c.startswith(l + "-")), "")
    if loc:
        affects = "ours"
    elif any(c.lower() in SERVICES for c in categories):
        affects = "service"
    else:
        affects = "other"
    kind = "maintenance" if re.search(r"maintenance|wartung", title, re.I) else "incident"
    return affects, loc, kind


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
        affects, loc, kind = classify(cats, title)
        out.append({
            "entry_id": (e.findtext(A + "id") or "").strip(),
            "updated": (e.findtext(A + "updated") or "").strip(),
            "title": title,
            "category": ", ".join(cats),
            "location": loc,
            "affects": affects,
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
        "_time": b["updated"] or datetime.now(timezone.utc).isoformat(),
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


def emit_metrics(ok, bulletins):
    counts = {"ours": 0, "service": 0, "other": 0}
    for b in bulletins:
        counts[b["affects"]] += 1
    lines = ["hetzner_status_poll_ok %d" % (1 if ok else 0)]
    if ok:
        lines.append("hetzner_status_last_success_timestamp %d" % int(time.time()))
        lines += ['hetzner_status_feed_entries{affects="%s"} %d' % (k, v) for k, v in counts.items()]
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
    first = "seen" not in state
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
                  len(events), [(e["affects"], e["title"][:50]) for e in events]), flush=True)
        except Exception as e:  # keep the daemon alive; hetzner_status_poll_ok=0 shows it
            print("poll error: %r" % e, file=sys.stderr, flush=True)
            emit_metrics(False, [])
        if ONCE:
            break
        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()
