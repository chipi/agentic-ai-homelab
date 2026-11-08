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
# The inbox published for other readers (the Hub), schema fleet_inbox/v1. Readers use this file and
# never the ledgers or the queue directory; flotilla will serve the same document from its API.
EXPORT_FILE = os.path.expanduser(
    os.environ.get("SF_INBOX_EXPORT", "~/signal-fleet/export/inbox.json"))


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
    """One JSON line per entry; stream keyed by (fleet, event) plus the LOG-STANDARD
    service/environment the fleet's metrics carry."""
    if not entries:
        return
    tag = {"service": config.SF_SERVICE, "environment": config.SF_ENV}
    lines = "\n".join(json.dumps({**e, **tag}, ensure_ascii=False) for e in entries)
    _post(VL_URL + "/insert/jsonline?_stream_fields=fleet,event,service,environment"
          "&_time_field=_time&_msg_field=_msg",
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


def _issue_closed(fingerprint, state_of, cache, issues=None):
    """True when the newest issue filed for this fingerprint is closed. Unfiled, or GitHub not
    answering: False, so the escalation stays counted (a failed read never hides one). With
    `issues`, records what was read per fingerprint for the export: the issue, or None if unfiled."""
    import filing
    row = filing.ledger_lookup(fingerprint)
    if not row or not row.get("repo") or not row.get("issue"):
        if issues is not None:
            issues[fingerprint] = None
        return False
    key = (row["repo"], row["issue"])
    if key not in cache:
        try:
            st = state_of(*key) or {}
            cache[key] = (st.get("state") == "closed",
                          {"state": st.get("state"), "title": st.get("title") or None})
        except Exception as ex:  # noqa: BLE001
            print(f"  inbox: issue state {key[0]}#{key[1]} unreadable, counted: {ex}")
            cache[key] = (False, {"state": None, "title": None, "error": str(ex)[:200]})
    if issues is not None:
        issues[fingerprint] = {"repo": key[0], "number": int(key[1]),
                               "url": f"https://github.com/{key[0]}/issues/{key[1]}", **cache[key][1]}
    return cache[key][0]


def _recent_escalations(days=7, state_of=None, issues=None):
    """Escalate rows of the last `days` days that still need the operator: an escalation whose
    filed issue is closed is done ("needs me" means open, operator 2026-11-04). `issues` (a dict),
    when given, collects each kept row's filed issue for the export."""
    if state_of is None:
        import filing
        state_of = filing.issue_state
    cache = {}
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
                if ts >= cutoff and not _issue_closed(c[idx["fingerprint"]], state_of, cache, issues):
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


def export_doc(items, escalations, issues, now=None):
    """The fleet_inbox/v1 document: what needs the operator, as the fleet counts it. needs_you is
    the bug-queue proposals plus the open escalations of the last 7 days."""
    bugs = [{"title": it["title"], "fingerprint": it["fingerprint"], "queued_at": it["queued_at"] or None}
            for it in items if it["kind"] == "bug"]
    by_kind = {}
    for it in items:
        by_kind[it["kind"]] = by_kind.get(it["kind"], 0) + 1
    return {
        "schema": "fleet_inbox/v1",
        "fleet": "triage",
        "generated_at": datetime.fromtimestamp(now or time.time(), timezone.utc).isoformat(),
        "needs_you": len(bugs) + len(escalations),
        "escalations_7d": [{"ts": e["ts"], "alertname": e["alertname"], "reason": e["reason"],
                            "fingerprint": e["fingerprint"], "issue": issues.get(e["fingerprint"])}
                           for e in escalations],
        "bug_queue": bugs,
        "queue_depth": by_kind,
    }


def write_export(doc, path=None):
    """Atomically, so a reader never sees half a file."""
    path = path or EXPORT_FILE
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(doc, f, ensure_ascii=False, indent=1)
    os.chmod(tmp, 0o644)
    os.replace(tmp, path)


def push_inbox():
    items = _scan_queue()
    issues = {}
    escalations = _recent_escalations(issues=issues)
    try:
        write_export(export_doc(items, escalations, issues))
    except Exception as ex:  # noqa: BLE001
        print(f"  inbox: export write failed: {ex}")

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
