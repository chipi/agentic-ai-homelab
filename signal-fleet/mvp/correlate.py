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
