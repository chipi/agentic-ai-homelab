"""Signal sources — the trigger side. MVP: poll Grafana Alerting.

The first slice reacts to one signal: the *orrery launch-data-stale* Grafana
alert. `firing_alerts()` is the general poll; `orrery_staleness()` picks the one.
"""
import hashlib

import config
from http_util import get_json


def firing_alerts():
    """Currently-active Grafana alert instances (Alertmanager v2). Prefers the
    Viewer service-account token; falls back to basic-auth only if no token."""
    url = f"{config.GRAFANA_URL}/api/alertmanager/grafana/api/v2/alerts"
    if config.GRAFANA_TOKEN:
        data = get_json(url, headers={"Authorization": f"Bearer {config.GRAFANA_TOKEN}"})
    else:
        data = get_json(url, config.GRAFANA_USER, config.GRAFANA_PW)
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
    """Normalize a Grafana alert into the fleet's signal shape.

    `fingerprint` is stable across occurrences (tracks recurrence — the R2-2
    implicit-overturn signal). `occurrence_id` = fingerprint + startsAt is the
    *idempotency* key, so re-litigating the same occurrence is skipped without
    silencing a future firing of the same alertname (review R3-1)."""
    labels = alert.get("labels", {})
    ann = alert.get("annotations", {})
    fp = _fingerprint(alert)
    starts = alert.get("startsAt") or ""
    return {
        "fingerprint": fp,
        "occurrence_id": f"{fp}@{starts}",
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


# ---- Phase B: GlitchTip errors (Sentry-compat REST API, poll) ----

def _gt(path):
    return get_json(f"{config.GLITCHTIP_URL}/api/0{path}",
                    headers={"Authorization": f"Bearer {config.GLITCHTIP_TOKEN}"})


def glitchtip_unresolved(limit=10):
    """Unresolved GlitchTip issues, most-recently-seen first."""
    issues = _gt(f"/organizations/homelab/issues/?limit={limit}&sort=-last_seen")
    if not isinstance(issues, list):
        raise RuntimeError(f"glitchtip issues error: {str(issues)[:160]}")
    return [i for i in issues if i.get("status") == "unresolved"]


def to_error_signal(issue):
    """Normalize a GlitchTip issue into an error signal. occurrence_id keys on
    lastSeen so a re-firing after resolve is a fresh occurrence (review R3-1)."""
    proj = (issue.get("project") or {}).get("slug", "")
    sid = issue.get("shortId") or str(issue.get("id"))
    fp = f"glitchtip:{sid}"
    # occurrence = one unresolved episode, keyed on firstSeen (STABLE across the
    # issue's events) — NOT lastSeen, which advances on every new event and would
    # re-triage a hot error every poll (review R5-4). Regression re-triage of a
    # resolved->reopened issue is a follow-up (needs status-transition tracking).
    first = issue.get("firstSeen") or ""
    return {
        "fingerprint": fp,
        "occurrence_id": f"{fp}@{first}",
        "source": "glitchtip",
        "alertname": issue.get("title", ""),
        "labels": {"project": proj, "level": issue.get("level", ""),
                   "culprit": issue.get("culprit", ""), "count": issue.get("count")},
        "summary": f"{issue.get('title', '')} (count={issue.get('count')}, "
                   f"level={issue.get('level')}, culprit={issue.get('culprit', '')})",
        "startsAt": issue.get("firstSeen"),
        "issue_id": issue.get("id"),
        "raw": issue,
    }
