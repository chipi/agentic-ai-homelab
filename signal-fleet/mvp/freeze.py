"""Freeze live signals + their evidence bundles into reference fixtures
(EVAL.md §3.1/§4). Replaying these *frozen* bundles is what makes k-runs measure
the model, not evidence drift.

Basic redaction: IPv4 addresses -> <ip>. Review fixtures before committing —
evidence contains real logs; treat them as data, not code.

  python3 freeze.py            # freeze the orrery-staleness case + unresolved GlitchTip
"""
import datetime
import json
import os
import re

import config
import correlate
import sources

IPV4 = re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}\b")


def _redact(obj):
    if isinstance(obj, str):
        return IPV4.sub("<ip>", obj)
    if isinstance(obj, dict):
        return {k: _redact(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_redact(x) for x in obj]
    return obj


def _write(fid, signal, evidence, source):
    os.makedirs(config.REFERENCE_DIR, exist_ok=True)
    fixture = {
        "id": fid,
        "source": source,
        "frozen_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "signal": _redact(signal),
        "evidence": _redact(evidence),
        # OPERATOR fills these (the human oracle — EVAL.md §4 sourcing #2):
        "ground_truth": {"disposition": None, "work_type": None, "notes": ""},
    }
    path = os.path.join(config.REFERENCE_DIR, f"{fid}.json")
    with open(path, "w") as f:
        json.dump(fixture, f, indent=2, ensure_ascii=False)
    print("froze", os.path.basename(path))


def freeze_glitchtip(limit=20):
    for issue in sources.glitchtip_unresolved(limit):
        sig = sources.to_error_signal(issue)
        ev = correlate.evidence_for_glitchtip_error(sig)
        fid = "glitchtip-" + sig["fingerprint"].split(":")[-1]
        _write(fid, sig, ev, "glitchtip")


def freeze_orrery_staleness():
    sig = {
        "fingerprint": "grafana:orrery-stale",
        "occurrence_id": "grafana:orrery-stale@frozen",
        "source": "grafana",
        "alertname": "Orrery launch data stale (no refresh in 7h)",
        "labels": {"alertname": "Orrery launch data stale"},
        "summary": "orrery data refresh alarm; verify against evidence",
        "startsAt": None,
    }
    ev = correlate.evidence_for_orrery_staleness(sig)
    _write("grafana-orrery-stale", sig, ev, "grafana")


if __name__ == "__main__":
    freeze_orrery_staleness()
    freeze_glitchtip()
    print(f"\nfixtures in {config.REFERENCE_DIR} — fill ground_truth, then score.py")
