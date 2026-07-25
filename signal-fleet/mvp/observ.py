"""Observability of the fleet itself (SIGNALS §11).

- Langfuse: a trace + generation per triage call (model/tokens/latency/disposition),
  mirroring bugfix-fleet's langfuse_push.py ingestion pattern.
- VictoriaMetrics: a `signal_fleet_disposition` sample per disposition, so a Grafana
  panel can count dispositions + the overturn rate (the trust metric).

Both graceful: missing creds / unreachable endpoint -> a printed note, never fatal.
"""
import base64
import datetime
import json
import os
import urllib.request
import uuid

import config


def _now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def trace_triage(signal, disp, usage=None, latency_s=0.0):
    pk = os.environ.get("LANGFUSE_PUBLIC_KEY")
    sk = os.environ.get("LANGFUSE_SECRET_KEY")
    host = os.environ.get("LANGFUSE_HOST", "http://homelab:4000").rstrip("/")
    if not (pk and sk):
        print("  langfuse: no creds — skipping")
        return
    meta = disp.get("_meta", {})
    d = disp.get("disposition")
    tid = str(uuid.uuid4())
    now = _now()
    batch = [{"id": str(uuid.uuid4()), "type": "trace-create", "timestamp": now, "body": {
        "id": tid, "name": f"{config.SF_SERVICE}/triage/{signal.get('source')}", "timestamp": now,
        "userId": signal.get("source"), "sessionId": signal.get("fingerprint"),
        "environment": config.SF_ENV,
        "tags": [config.SF_SERVICE, "triage", str(signal.get("source")), str(d),
                 f"gates:{meta.get('gates')}", f"probes:{meta.get('n_probes')}",
                 f"certainty:{meta.get('certainty')}"],
        "metadata": {"disposition": d, "alertname": signal.get("alertname"),
                     "model": meta.get("model"), "prompt_ver": meta.get("prompt_ver"),
                     "prompt_sha": meta.get("prompt_sha"), "attempt": meta.get("attempt"),
                     "latency_s": round(latency_s, 2)},
        "input": signal.get("summary"), "output": disp.get("reason")}}]
    if usage:
        batch.append({"id": str(uuid.uuid4()), "type": "generation-create", "timestamp": now, "body": {
            "id": str(uuid.uuid4()), "traceId": tid, "name": "triage-call",
            "model": meta.get("model"), "environment": "signal-fleet",
            "usage": {"input": usage.get("prompt_tokens", 0),
                      "output": usage.get("completion_tokens", 0),
                      "total": usage.get("total_tokens", 0), "unit": "TOKENS"}}})
    _ingest(host, pk, sk, batch, tid)


def _ingest(host, pk, sk, batch, tid):
    req = urllib.request.Request(host + "/api/public/ingestion",
                                 data=json.dumps({"batch": batch}).encode(), method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("Authorization", "Basic " + base64.b64encode(f"{pk}:{sk}".encode()).decode())
    try:
        r = urllib.request.urlopen(req, timeout=12)
        print(f"  langfuse: {r.status} trace={tid[:8]}")
    except Exception as ex:  # noqa: BLE001
        print(f"  langfuse push failed: {ex}")


def push_disposition_metric(signal, disp):
    """One VictoriaMetrics sample per disposition (Prometheus import, no auth).
    Panel: sum by (disposition) (count_over_time(signal_fleet_disposition[1h]))."""
    d = disp.get("disposition", "")
    src = signal.get("source", "")
    wt = (disp.get("file") or {}).get("work_type", "") if d == "file" else ""
    follow = "1" if (d == "dismiss" and disp.get("immediate_recommendation")) else "0"
    meta = disp.get("_meta", {})
    usage = meta.get("usage") or {}
    base = (f'source="{src}",service="{config.SF_SERVICE}",environment="{config.SF_ENV}"')
    lines = [
        f'signal_fleet_disposition{{disposition="{d}",work_type="{wt}",followup="{follow}",{base}}} 1',
        # workforce accounting: money + tokens per decision (dashboard fuel)
        f'signal_fleet_cost_usd{{disposition="{d}",{base}}} {meta.get("cost_usd") or 0}',
        f'signal_fleet_tokens{{kind="prompt",{base}}} {usage.get("prompt_tokens") or 0}',
        f'signal_fleet_tokens{{kind="completion",{base}}} {usage.get("completion_tokens") or 0}',
        f'signal_fleet_probes{{{base}}} {meta.get("n_probes") or 0}',
    ]
    try:
        req = urllib.request.Request(config.VM_URL + "/api/v1/import/prometheus",
                                     data=("\n".join(lines) + "\n").encode(), method="POST")
        urllib.request.urlopen(req, timeout=8)
    except Exception as ex:  # noqa: BLE001
        print(f"  vm metric push failed: {ex}")


def finalize(signal, disp, usage=None, latency_s=0.0):
    """Emit both observability outputs for one disposition."""
    if config.OBSERV_DISABLED:
        return  # eval replay — don't pollute live fleet traces/metrics
    trace_triage(signal, disp, usage=usage, latency_s=latency_s)
    push_disposition_metric(signal, disp)
