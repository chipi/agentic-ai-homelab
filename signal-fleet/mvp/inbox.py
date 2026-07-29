"""Operator-inbox surfacing — the "what needs ME, right now" layer.

Runs at the end of every orchestrator cycle (best-effort). Two outputs:

1. VictoriaMetrics gauges (dashboard "Waiting on operator" row):
   - signal_fleet_queue_depth{kind}       items parked in ~/signal-fleet/queue
   - signal_fleet_queue_oldest_age_seconds  the "operator is the bottleneck" signal
   - signal_fleet_escalations_7d          escalate rows in the 7d window

2. VictoriaLogs content (drill-down dashboard "Triage — Operator Inbox"):
   one jsonline per NEW queue item / NEW escalation, so clicking the number
   in Grafana lands on the actual titles and reasons, not just counts.
   Idempotence via a seen-ids state file — items ship once, not per cycle.
"""
import json
import os
import time
import urllib.request
from datetime import datetime, timezone

import config

QUEUE_DIR = os.path.expanduser(os.environ.get("SF_QUEUE_DIR", "~/signal-fleet/queue"))
DISPOSITIONS = os.path.expanduser(
    os.environ.get("SF_DISPOSITIONS", "~/signal-fleet/results/dispositions.tsv"))
SEEN_FILE = os.path.expanduser(
    os.environ.get("SF_INBOX_SEEN", "~/signal-fleet/results/.inbox_seen"))
VL_URL = os.environ.get("SF_VL_URL", config.VM_URL.replace(":8428", ":9428"))


def _load_seen():
    try:
        with open(SEEN_FILE) as f:
            return set(line.strip() for line in f if line.strip())
    except OSError:
        return set()


def _append_seen(ids):
    with open(SEEN_FILE, "a") as f:
        for i in ids:
            f.write(i + "\n")


def _post(url, body, ctype):
    req = urllib.request.Request(url, data=body.encode(), method="POST")
    req.add_header("Content-Type", ctype)
    urllib.request.urlopen(req, timeout=8)


def _vl_ship(entries):
    """One JSON line per entry; stream keyed by (fleet, event)."""
    if not entries:
        return
    lines = "\n".join(json.dumps(e, ensure_ascii=False) for e in entries)
    _post(VL_URL + "/insert/jsonline?_stream_fields=fleet,event&_time_field=_time&_msg_field=_msg",
          lines + "\n", "application/stream+json")


def _scan_queue():
    items = []
    for name in sorted(os.listdir(QUEUE_DIR)) if os.path.isdir(QUEUE_DIR) else []:
        if not name.endswith(".json"):
            continue
        path = os.path.join(QUEUE_DIR, name)
        try:
            with open(path) as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError):
            continue
        items.append({
            "id": name,
            "kind": data.get("kind") or name.split("-")[0],
            "title": (data.get("issue") or {}).get("title") or
                     (data.get("signal") or {}).get("alertname", "")[:140],
            "fingerprint": (data.get("signal") or {}).get("fingerprint", ""),
            "queued_at": data.get("queued_at", ""),
            "mtime": os.path.getmtime(path),
        })
    return items


def _recent_escalations(days=7):
    cutoff = datetime.now(timezone.utc).timestamp() - days * 86400
    rows = []
    try:
        with open(DISPOSITIONS) as f:
            header = f.readline().rstrip("\n").split("\t")
            idx = {c: i for i, c in enumerate(header)}
            for line in f:
                c = line.rstrip("\n").split("\t")
                if len(c) < len(header) or c[idx["disposition"]] != "escalate":
                    continue
                try:
                    ts = datetime.fromisoformat(c[idx["ts"]]).timestamp()
                except ValueError:
                    continue
                if ts >= cutoff:
                    rows.append({
                        "id": "esc:" + c[idx["ts"]],
                        "ts": c[idx["ts"]],
                        "alertname": c[idx["alertname"]],
                        "reason": c[idx["reason"]],
                        "fingerprint": c[idx["fingerprint"]],
                    })
    except OSError:
        pass
    return rows


def push_inbox():
    items = _scan_queue()
    escalations = _recent_escalations()

    # ── gauges → VictoriaMetrics
    by_kind = {}
    for it in items:
        by_kind[it["kind"]] = by_kind.get(it["kind"], 0) + 1
    oldest_age = 0
    if items:
        oldest_age = int(time.time() - min(it["mtime"] for it in items))
    base = f'service="{config.SF_SERVICE}",environment="{config.SF_ENV}"'
    lines = [f'signal_fleet_queue_oldest_age_seconds{{{base}}} {oldest_age}',
             f'signal_fleet_escalations_7d{{{base}}} {len(escalations)}']
    for kind, n in sorted(by_kind.items()):
        lines.append(f'signal_fleet_queue_depth{{kind="{kind}",{base}}} {n}')
    if not by_kind:
        lines.append(f'signal_fleet_queue_depth{{kind="none",{base}}} 0')
    try:
        _post(config.VM_URL + "/api/v1/import/prometheus", "\n".join(lines) + "\n", "text/plain")
    except Exception as ex:  # noqa: BLE001
        print(f"  inbox: vm push failed: {ex}")

    # ── new content → VictoriaLogs (ship once)
    seen = _load_seen()
    fresh = []
    for it in items:
        if it["id"] in seen:
            continue
        fresh.append({"_time": it["queued_at"] or
                      datetime.fromtimestamp(it["mtime"], timezone.utc).isoformat(),
                      "_msg": f'[{it["kind"]}] {it["title"]}',
                      "fleet": "triage", "event": "queued", "kind": it["kind"],
                      "fingerprint": it["fingerprint"], "item_id": it["id"]})
    for esc in escalations:
        if esc["id"] in seen:
            continue
        fresh.append({"_time": esc["ts"], "_msg": f'ESCALATE {esc["alertname"]} — {esc["reason"]}',
                      "fleet": "triage", "event": "escalate",
                      "fingerprint": esc["fingerprint"], "item_id": esc["id"]})
    if fresh:
        try:
            _vl_ship(fresh)
            _append_seen([e["item_id"] for e in fresh])
            print(f"  inbox: shipped {len(fresh)} new item(s) to VictoriaLogs")
        except Exception as ex:  # noqa: BLE001
            print(f"  inbox: vl ship failed: {ex}")
    print(f"  inbox: queue={sum(by_kind.values())} by_kind={by_kind} "
          f"escalations_7d={len(escalations)} oldest_age={oldest_age}s")


if __name__ == "__main__":
    push_inbox()
