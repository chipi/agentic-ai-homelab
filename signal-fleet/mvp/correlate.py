"""Correlation reads — the query-time join across VM / VL / VT (SIGNALS §6).

For the first slice (orrery staleness), the correlated picture is:
- VictoriaLogs: the orrery data-refresh cron logs (did it run? fail? when last?)
- VictoriaMetrics: the staleness metric the alert fired on.
The evidence bundle is what the triager reasons over — never a single signal.
"""
import urllib.parse

import config
from http_util import get_json, post_form_text


def vl_query(logsql, timeout=12):
    """Run a LogsQL query; returns raw text (NDJSON or stats)."""
    return post_form_text(
        f"{config.VL_URL}/select/logsql/query", {"query": logsql}, timeout=timeout
    )


def vm_query(promql, timeout=12):
    """Run an instant PromQL query; returns the parsed JSON result."""
    url = f"{config.VM_URL}/api/v1/query?" + urllib.parse.urlencode({"query": promql})
    return get_json(url, timeout=timeout)


def evidence_for_orrery_staleness(signal, window="24h"):
    """Build the correlated evidence bundle. Queries are best-effort — a source
    that returns nothing is reported as empty, never fatal."""
    ev = {"queries": {}}

    def _try(name, fn):
        try:
            ev["queries"][name] = fn()
        except Exception as e:  # correlation is best-effort
            ev["queries"][name] = f"<error: {e}>"

    # orrery data-refresh logs in the window (the direct cause surface)
    _try("refresh_logs", lambda: vl_query(
        f'app:orrery AND _time:{window} | sort by (_time) desc | limit 25'))
    # narrower: the refresh job if it's labelled
    _try("refresh_job_logs", lambda: vl_query(
        f'job:orrery-data-refresh AND _time:{window} | sort by (_time) desc | limit 25'))
    # the metric the alert watches (orrery targets up?)
    _try("orrery_up", lambda: vm_query('up{job=~".*orrery.*"}'))
    return ev


# ---- Phase B: correlation for a GlitchTip error (error -> trace -> metric) ----

def _gt(path):
    return get_json(f"{config.GLITCHTIP_URL}/api/0{path}",
                    headers={"Authorization": f"Bearer {config.GLITCHTIP_TOKEN}"})


def _event_summary(issue_id):
    """Compact the latest event: culprit, env/component, trace_id, top frames."""
    e = _gt(f"/issues/{issue_id}/events/latest/")
    tags = {t.get("key"): t.get("value") for t in (e.get("tags") or []) if isinstance(t, dict)}
    trace = (e.get("contexts") or {}).get("trace", {}) or {}
    frames = []
    for entry in (e.get("entries") or []):
        if entry.get("type") == "exception":
            for val in (entry.get("data", {}) or {}).get("values", []):
                for fr in ((val.get("stacktrace") or {}).get("frames") or [])[-4:]:
                    frames.append(f"{fr.get('filename')}:{fr.get('lineNo')} {fr.get('function')}")
    return {
        "platform": e.get("platform"), "culprit": e.get("culprit"),
        "message": e.get("message"),
        "environment": tags.get("environment"), "component": tags.get("component"),
        "release": tags.get("release"), "trace_id": trace.get("trace_id"),
        "tags": tags, "frames": frames[-6:],
    }


def vt_trace(trace_id):
    return get_json(f"{config.VT_URL}/select/jaeger/api/traces/{trace_id}")


def evidence_for_glitchtip_error(signal, window="6h"):
    """error -> trace -> metric/logs. Best-effort: an empty/missing source is
    reported, never fatal. A client-side error may have no server trace."""
    ev = {"queries": {}}

    def _try(name, fn):
        try:
            ev["queries"][name] = fn()
        except Exception as e:
            ev["queries"][name] = f"<error: {e}>"

    iid = signal.get("issue_id")
    proj = signal["labels"].get("project", "")
    _try("event_summary", lambda: _event_summary(iid))

    summ = ev["queries"].get("event_summary")
    tid = summ.get("trace_id") if isinstance(summ, dict) else None
    if tid:
        _try("trace", lambda: vt_trace(tid))

    if proj:
        _try("service_logs", lambda: vl_query(
            f'app:{proj} AND _time:{window} | sort by (_time) desc | limit 15'))
        _try("http_5xx_rate", lambda: vm_query(
            f'sum(rate(http_requests_total{{job=~".*{proj}.*"}}[5m]))'))
    return ev
