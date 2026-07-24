"""Signal sources — the trigger side. MVP: poll Grafana Alerting.

The first slice reacts to one signal: the *orrery launch-data-stale* Grafana
alert. `firing_alerts()` is the general poll; `orrery_staleness()` picks the one.
"""
import hashlib

import config
from http_util import get_json


def firing_alerts():
    """Currently-active Grafana alert instances (Alertmanager v2)."""
    data = get_json(
        f"{config.GRAFANA_URL}/api/alertmanager/grafana/api/v2/alerts",
        config.GRAFANA_USER, config.GRAFANA_PW,
    )
    return [a for a in data if a.get("status", {}).get("state") == "active"]


def _fingerprint(alert):
    """Stable id for the ledger (Grafana gives one; fall back to labels)."""
    fp = alert.get("fingerprint")
    if fp:
        return f"grafana:{fp}"
    labels = alert.get("labels", {})
    key = "|".join(f"{k}={labels[k]}" for k in sorted(labels))
    return "grafana:" + hashlib.sha1(key.encode()).hexdigest()[:16]


def to_signal(alert):
    """Normalize a Grafana alert into the fleet's signal shape."""
    labels = alert.get("labels", {})
    ann = alert.get("annotations", {})
    return {
        "fingerprint": _fingerprint(alert),
        "source": "grafana",
        "alertname": labels.get("alertname", ""),
        "labels": labels,
        "summary": ann.get("summary") or ann.get("description") or "",
        "startsAt": alert.get("startsAt"),
        "raw": alert,
    }


def orrery_staleness():
    """The one signal the first slice acts on, or None if not firing."""
    for a in firing_alerts():
        name = a.get("labels", {}).get("alertname", "").lower()
        if "launch data stale" in name or ("orrery" in name and "stale" in name):
            return to_signal(a)
    return None
