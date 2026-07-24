"""Typed probe menu for the investigation loop (SIGNALS §7.3).

Each probe is a deterministic, bounded query the triager requests BY NAME — the
model never writes raw queries (safety + replayability). `run_probe` dispatches
either live or against a frozen probe->response table (the eval replay, EVAL.md /
§7.3 "freeze the probe->response table").
"""
import json

import correlate


def _event_detail(signal, args):
    iid = signal.get("issue_id")
    if not iid:
        return "<not applicable: not a GlitchTip issue>"
    return correlate._event_summary(iid)


def _occurrence_history(signal, args):
    r = signal.get("raw") or {}
    hist = {k: r.get(k) for k in
            ("count", "userCount", "firstSeen", "lastSeen", "level", "status", "culprit")}
    return hist if any(v is not None for v in hist.values()) else "<no occurrence history>"


def _service_logs(signal, args):
    svc = args.get("service") or signal.get("labels", {}).get("project", "")
    window = args.get("window", "6h")
    if not svc:
        return "<no service to query>"
    return correlate.vl_query(f"app:{svc} AND _time:{window} | sort by (_time) desc | limit 15")


def _metric(signal, args):
    svc = args.get("service") or signal.get("labels", {}).get("project", "")
    kind = args.get("kind", "5xx")
    q = {
        "5xx": f'sum(rate(http_requests_total{{job=~".*{svc}.*",status=~"5.."}}[5m]))',
        "up": f'up{{job=~".*{svc}.*"}}',
    }.get(kind, f'up{{job=~".*{svc}.*"}}')
    return correlate.vm_query(q)


def _trace(signal, args):
    tid = args.get("trace_id")
    if not tid:
        return "<no trace_id provided>"
    r = correlate.vt_trace(tid)
    return r if (isinstance(r, dict) and r.get("data")) else f"<trace {tid[:8]} not found>"


def _source_state(signal, args):
    """Orrery data-refresh state (last successful refresh) — the staleness case."""
    return correlate.vl_query(
        "job:orrery-data-refresh AND _time:24h | sort by (_time) desc | limit 10")


# name -> (one-line description for the menu, fn)
PROBES = {
    "event_detail": ("the error's latest event: culprit, stack frames, tags, trace_id, platform", _event_detail),
    "occurrence_history": ("count, first/last seen, level, status of the issue", _occurrence_history),
    "service_logs": ("recent logs for a service — args {service?, window?}", _service_logs),
    "metric": ("a metric for a service — args {service?, kind: 5xx|up}", _metric),
    "trace": ("a distributed trace by id — args {trace_id}", _trace),
    "source_state": ("orrery data-refresh state (last successful refresh)", _source_state),
}


def menu():
    return "\n".join(f"- {name}: {desc}" for name, (desc, _) in PROBES.items())


def probe_key(name, args):
    return name + ":" + json.dumps(args or {}, sort_keys=True)


def run_probe(signal, name, args, table=None):
    """Dispatch a probe. If `table` (a frozen probe->response map) is given, replay
    from it (eval); else run live. Never raises — returns a '<…>' marker on failure."""
    if table is not None:
        return table.get(probe_key(name, args), f"<not in frozen table: {probe_key(name, args)}>")
    entry = PROBES.get(name)
    if not entry:
        return f"<unknown probe: {name}>"
    try:
        return entry[1](signal, args or {})
    except Exception as e:  # noqa: BLE001
        return f"<error: {e}>"
