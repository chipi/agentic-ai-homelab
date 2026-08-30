"""Signal sources — the trigger side. MVP: poll Grafana Alerting.

The first slice reacts to one signal: the *orrery launch-data-stale* Grafana
alert. `firing_alerts()` is the general poll; `orrery_staleness()` picks the one.
"""
import hashlib
import re

import config
from http_util import get_json

# Test / synthetic run markers — signals carrying these are noise-at-source and
# must never reach triage (a real prod escalation of an `agentE2E…player` E2E run
# is what motivated this, 2026-08-19). Suppressed at ingestion, not via the LLM,
# so it holds even when the triager is down (fail-open would otherwise escalate
# them). camelCase run-ids (agentE2E<epoch>) are the common shape. Any e2e-*/e2e_*
# token is a test artifact by naming convention (e2e-deadletter-1, the delivery e2e
# envelope, queued two cleanup proposals in 2026-08 because the old \be2e[-_]run\b
# only matched the literal word "run"). Deliberate CANARY probes are NOT suppressed —
# they exist to prove the alert path end-to-end.
TEST_RUN_MARKER = re.compile(
    r"agente2e|synthetic|smoke[-_ ]?test|\be2e[-_]\w+|ladder[-_]verify|\btest[-_]run\b",
    re.I)


def _is_test_signal(*fields):
    return bool(TEST_RUN_MARKER.search(" ".join(str(f) for f in fields if f)))


def firing_alerts():
    """Currently-active Grafana alert instances (Alertmanager v2). Prefers the
    Viewer service-account token; falls back to basic-auth only if no token."""
    url = f"{config.GRAFANA_URL}/api/alertmanager/grafana/api/v2/alerts"
    if config.GRAFANA_TOKEN:
        data = get_json(url, headers={"Authorization": f"Bearer {config.GRAFANA_TOKEN}"})
    else:
        data = get_json(url, config.GRAFANA_USER, config.GRAFANA_PW)
    # meta=true = SUBSTRATE alerts (fleetd/VM/Grafana health): they terminate at
    # the operator, never at the fleet — a broken fleet can't triage its own
    # substrate (boundary decision 2026-08-02; enforced in policies.yaml too).
    # Plumbing states (DatasourceNoData/DatasourceError/Watchdog) are Grafana
    # meta-alerts about observability wiring, not symptoms — mechanically
    # excluded so "truthful alerts only" doesn't depend on author discipline
    # (2026-08-05: a delivery-group DatasourceNoData was live-firing).
    _PLUMBING = {"DatasourceNoData", "DatasourceError", "Watchdog"}
    return [a for a in data
            if a.get("status", {}).get("state") == "active"
            and a.get("labels", {}).get("meta") != "true"
            and a.get("labels", {}).get("alertname") not in _PLUMBING
            and not _is_test_signal(a.get("labels", {}).get("alertname"),
                                    a.get("labels", {}).get("run_id"),
                                    a.get("labels", {}).get("environment"))]


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
    out = []
    for i in issues:
        if i.get("status") != "unresolved":
            continue
        meta = i.get("metadata") or {}
        if _is_test_signal(i.get("title"), i.get("culprit"), i.get("shortId"),
                           meta.get("value"), meta.get("type")):
            print(f"  [suppress test/synthetic] {i.get('shortId')} {str(i.get('title',''))[:70]}")
            continue
        out.append(i)
    return out


def to_error_signal(issue):
    """Normalize a GlitchTip issue into an error signal. occurrence_id keys on
    firstSeen (stable per issue episode — R5-4); new-event recurrence is handled
    by the orchestrator's recurrence check, not by a fresh occurrence id."""
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
