#!/usr/bin/env python3
"""GitHub status (githubstatus.com), correlated with what of GitHub we use, every 5 minutes.

The counterpart of infra/hetzner-status (its log-and-banner model) and of cloudflare-edge's status part
(githubstatus.com is the same Statuspage product as cloudflarestatus.com). Reads
https://www.githubstatus.com/api/v2/summary.json, which carries the components, every unresolved incident
and every upcoming or in-progress scheduled maintenance. Stdlib only, read-only towards GitHub.

  - VictoriaLogs: one line per incident or maintenance update (new id, or a changed updated_at), stream
    app=github-status. Fields: kind (incident|maintenance), relevance (direct|other), name, impact, status,
    components, link, start, end, last_update, backfill (true = already there when watching started; never
    alerts). The alert rule github-status-ours reads these.
  - VictoriaMetrics, re-pushed every poll while true (read with last_over_time(...[15m])):
      github_status_indicator{indicator,description} 1
      github_status_component{name,status} 1           a component of ours that is not operational
      github_status_active{kind,relevance,phase,name,impact,status,components,start,end,link} 1
          an unresolved incident (phase=ongoing), or maintenance in progress (ongoing) or starting within
          GITHUB_UPCOMING_DAYS (upcoming)
      github_status_poll_ok, github_status_last_success_timestamp

Run once: python3 poll.py --once. Correlation: ours.json.
"""
import json
import os
import sys
import time
import urllib.request
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
SUMMARY = os.environ.get("GITHUB_STATUS_URL", "https://www.githubstatus.com/api/v2/summary.json")
VLOGS = os.environ.get("VLOGS_URL", "http://localhost:9428").rstrip("/")
VM = os.environ.get("VM_IMPORT_URL", "http://localhost:8428/api/v1/import/prometheus")
STATE_FILE = os.environ.get("STATE_FILE", os.path.join(HERE, "state.json"))
INTERVAL = int(os.environ.get("POLL_INTERVAL", "300"))
UPCOMING = timedelta(days=int(os.environ.get("GITHUB_UPCOMING_DAYS", "7")))
ONCE = "--once" in sys.argv


def load_ours(path=os.path.join(HERE, "ours.json")):
    with open(path) as f:
        return set(json.load(f)["components"])


def _ts(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00")) if s else None


def items(summary, ours, now=None):
    """Incidents and maintenance, each as a flat dict with its relevance and phase (None = not shown)."""
    now = now or datetime.now(timezone.utc)
    out = []
    for kind, key in (("incident", "incidents"), ("maintenance", "scheduled_maintenances")):
        for i in summary.get(key, []):
            comps = [c["name"] for c in i.get("components", [])]
            hit = [c for c in comps if c in ours]
            start = i.get("scheduled_for") if kind == "maintenance" else (i.get("started_at") or i.get("created_at"))
            if kind == "incident":
                phase = "ongoing"
            elif i.get("status") == "in_progress":
                phase = "ongoing"
            elif _ts(start) and _ts(start) - now <= UPCOMING:
                phase = "upcoming"
            else:
                phase = None
            updates = i.get("incident_updates") or []
            out.append({
                "id": i["id"], "updated": i.get("updated_at") or "", "kind": kind,
                "relevance": "direct" if hit else "other", "phase": phase,
                "name": i.get("name", ""), "impact": i.get("impact", ""), "status": i.get("status", ""),
                "components": ", ".join((hit or comps)[:5]), "link": i.get("shortlink") or "",
                "start": start or "", "end": i.get("scheduled_until") or "",
                "last_update": (updates[0].get("body") or "")[:400] if updates else "",
            })
    return out


def _lv(s):
    return str(s).replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")


def _m(name, labels, value):
    return "%s{%s} %s" % (name, ",".join('%s="%s"' % (k, _lv(v)) for k, v in labels.items()), value)


def metric_lines(ok, summary, ours, now=None):
    lines = ["github_status_poll_ok %d" % (1 if ok else 0)]
    if not ok:
        return lines
    lines.append("github_status_last_success_timestamp %d" % int(time.time()))
    st = summary.get("status") or {}
    lines.append(_m("github_status_indicator", {"indicator": st.get("indicator", ""), "description": st.get("description", "")}, 1))
    for c in summary.get("components", []):
        if c["name"] in ours and c.get("status") != "operational":
            lines.append(_m("github_status_component", {"name": c["name"], "status": c["status"]}, 1))
    for it in items(summary, ours, now):
        if it["phase"]:
            lines.append(_m("github_status_active", {k: it[k] for k in
                            ("kind", "relevance", "phase", "name", "impact", "status", "components", "start", "end", "link")}, 1))
    return lines


def new_events(state, its):
    """Log lines for items that are new or changed since the last poll. First run (no state) = backfill."""
    first = "seen" not in state
    seen = state.setdefault("seen", {})
    now = datetime.now(timezone.utc).isoformat()
    events = []
    for it in its:
        if seen.get(it["id"]) == it["updated"]:
            continue
        seen[it["id"]] = it["updated"]
        ev = {k: v for k, v in it.items() if k != "phase"}
        ev.update({"_time": now, "_msg": "github %s [%s] %s (%s)" % (it["kind"], it["components"] or "-", it["name"], it["status"]),
                   "app": "github-status", "service": "github-status", "environment": "operations", "instance": "homelab",
                   "backfill": "true" if first else "false"})
        events.append(ev)
    current = {it["id"] for it in its}
    state["seen"] = {k: v for k, v in seen.items() if k in current}
    return events


def _post(url, body, ctype, timeout=15):
    urllib.request.urlopen(urllib.request.Request(url, data=body, method="POST", headers={"Content-Type": ctype}), timeout=timeout).read()


def emit(events, lines):
    if events:
        _post(VLOGS + "/insert/jsonline?_stream_fields=app,service,environment,instance&_time_field=_time&_msg_field=_msg",
              "\n".join(json.dumps(e) for e in events).encode(), "application/stream+json")
    _post(VM + "?extra_label=instance=homelab&extra_label=service=github-status&extra_label=environment=operations",
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


def poll_once(state, ours, fetch=None):
    text = fetch() if fetch else urllib.request.urlopen(
        urllib.request.Request(SUMMARY, headers={"User-Agent": "homelab-github-status"}), timeout=30).read().decode()
    summary = json.loads(text)
    return new_events(state, items(summary, ours)), metric_lines(True, summary, ours), summary


def main():
    ours = load_ours()
    while True:
        state = load_state()
        try:
            events, lines, summary = poll_once(state, ours)
            emit(events, lines)
            save_state(state)
            print("[%s] %s | incidents=%d maintenance=%d new=%d %s" % (
                datetime.now(timezone.utc).isoformat(timespec="seconds"), summary["status"]["description"],
                len(summary.get("incidents", [])), len(summary.get("scheduled_maintenances", [])), len(events),
                [(e["kind"], e["relevance"], e["name"][:50]) for e in events]), flush=True)
        except Exception as e:  # keep the daemon alive; github_status_poll_ok=0 shows it
            print("poll error: %r" % e, file=sys.stderr, flush=True)
            try:
                emit([], metric_lines(False, {}, ours))
            except Exception as e2:
                print("metrics push failed: %r" % e2, file=sys.stderr, flush=True)
        if ONCE:
            break
        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()
