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
    # all of these are corroborating (none is the alert restated) — R5-1
    ev["corroborating"] = ["refresh_logs", "refresh_job_logs", "orrery_up"]
    return ev


# ---- Phase B: correlation for a GlitchTip error (error -> trace -> metric) ----

def _gt(path):
    return get_json(f"{config.GLITCHTIP_URL}/api/0{path}",
                    headers={"Authorization": f"Bearer {config.GLITCHTIP_TOKEN}"})


def _exc_values(e):
    """The chained-exception list from a Sentry/GlitchTip event. The API returns it
    under entries[type==exception].data.values; some shapes nest it as
    exception.values. [] when the event carries no exception."""
    for entry in (e.get("entries") or []):
        if entry.get("type") == "exception":
            return (entry.get("data", {}) or {}).get("values") or []
    return ((e.get("exception") or {}).get("values")) or []


def _top_app_frame(stack):
    """The crash-site APP frame of a stacktrace, as 'filename function' WITHOUT the
    line number. Sentry orders frames oldest→newest (caller first, crash site last),
    so the top frame is the LAST; prefer the last in_app frame, else the last frame.
    lineNo is deliberately omitted — line numbers drift across deploys and the
    norm_key (#1) must be deploy-stable."""
    frames = (stack or {}).get("frames") or []
    app = [f for f in frames if f.get("in_app")] or frames
    if not app:
        return ""
    fr = app[-1]
    fn = fr.get("filename") or fr.get("module") or ""
    return f"{fn} {fr.get('function') or ''}".strip()


def _summarize_event(e):
    """Pure event→summary (no network — unit-testable with a frozen event dict).

    #5 (innermost __cause__): Sentry chained-exception `values` is ordered oldest→
    newest — values[0] is the INNERMOST root cause (the exception raised `from`),
    values[-1] the OUTERMOST wrapper actually logged (develop.sentry.dev Exception
    interface, "oldest to newest"). The #1854 shape ("one or more feed failures")
    is the outer wrapper; the actionable per-feed error is the inner cause. We
    surface both, distinctly, so triage reasons over the cause not the wrapper.
    ORDERING VERIFIED against the real Sentry Python SDK (sentry_sdk 2.63.0,
    event_from_exception on a `raise Outer from Inner`): values[0] is the inner
    root cause, values[-1] the outer wrapper (2026-08-28).

    #6 (code_version): the release/commit the event fired on, so stack frames
    resolve against the right revision."""
    tags = {t.get("key"): t.get("value") for t in (e.get("tags") or []) if isinstance(t, dict)}
    trace = (e.get("contexts") or {}).get("trace", {}) or {}
    values = _exc_values(e)
    inner = values[0] if values else {}
    outer = values[-1] if values else {}
    frames = []
    for val in values:
        for fr in ((val.get("stacktrace") or {}).get("frames") or [])[-4:]:
            frames.append(f"{fr.get('filename')}:{fr.get('lineNo')} {fr.get('function')}")
    code_version = tags.get("release") or e.get("release") or ""
    return {
        "platform": e.get("platform"), "culprit": e.get("culprit"),
        "message": e.get("message"),
        # #5 innermost actionable cause, kept distinct from the outer wrapper
        "cause_type": inner.get("type"), "cause_value": inner.get("value"),
        "cause_frame": _top_app_frame(inner.get("stacktrace")),
        "chain_depth": len(values),
        # the outermost raised type + crash frame — what norm_key (#1) keys on
        "exc_type": outer.get("type"), "top_frame": _top_app_frame(outer.get("stacktrace")),
        "environment": tags.get("environment"), "component": tags.get("component"),
        "release": tags.get("release"), "code_version": code_version,  # #6
        "trace_id": trace.get("trace_id"),
        "tags": tags, "frames": frames[-6:],
    }


def _event_summary(issue_id):
    """Fetch the latest event for a GlitchTip issue and summarize it (#5/#6)."""
    return _summarize_event(_gt(f"/issues/{issue_id}/events/latest/"))


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
    platform = (summ.get("platform") or "") if isinstance(summ, dict) else ""
    client_side = platform in ("javascript", "node") or "browser" in platform.lower()
    # Label the KIND of trace absence so a blank never reads as "recovered" (R5-2).
    if tid:
        def _trace():
            r = vt_trace(tid)
            data = r.get("data") if isinstance(r, dict) else None
            return r if data else f"<trace {tid[:8]} expected but not found in VictoriaTraces>"
        _try("trace", _trace)
    else:
        ev["queries"]["trace"] = ("<not expected: client-side platform, no server trace_id>"
                                  if client_side else "<no trace_id on event>")

    if proj:
        _try("service_logs", lambda: vl_query(
            f'app:{proj} AND _time:{window} | sort by (_time) desc | limit 15'))
        # 5xx rate WITH the status filter — was total traffic under a 5xx label (R5-3)
        _try("http_5xx_rate", lambda: vm_query(
            f'sum(rate(http_requests_total{{job=~".*{proj}.*",status=~"5.."}}[5m]))'))

    # corroboration = evidence beyond the error itself; event_summary excluded (R5-1)
    ev["corroborating"] = ["trace", "service_logs", "http_5xx_rate"]
    return ev
