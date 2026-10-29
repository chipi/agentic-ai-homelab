"""Per-decision probe capture: make every triage decision replayable later, exactly.

Off unless SF_CAPTURE_PROBES=1. When on, actions.act calls record() after the ledger row is
written, and one JSON file per decision lands in CAPTURE_DIR (mode 600; real production data,
so it stays on the fleet host and goes through scrub.py before it is shared). The file has
freeze.py's fixture shape, so triage.investigate(signal, probe_table=item["probes"]) replays it:

  probes         probe_key -> raw answer: what the model asked for (from the decision's own
                 trace, not re-run) plus, with SF_CAPTURE_EAGER=1, the rest of the menu at
                 default args, fetched now, so a replay that picks another probe still hits
  probes_shown   probe_key -> the exact trimmed text the model read (model-asked probes only)
  probe_source   probe_key -> "model" | "eager"

Without capture, probe answers exist nowhere once the decision is made; rebuilding them later
is limited by the stores' retention (logs and Langfuse 30 days, traces ~22).
"""
import datetime
import json
import os
import re

import config
import probes


def _safe_name(s):
    return re.sub(r"[^A-Za-z0-9_.@-]+", "_", s)[:150]


def record(signal, disp, now=None):
    """Write the decision's capture file; returns its path, or None (off, or a write failed).
    Never raises: capture must not break a triage cycle."""
    if not config.CAPTURE_PROBES:
        return None
    try:
        now = now or datetime.datetime.now(datetime.timezone.utc)
        stamp = now.strftime("%Y%m%dT%H%M%SZ")
        table, shown, source = {}, {}, {}
        for t in disp.get("_probe_trace") or []:
            k = probes.probe_key(t.get("probe"), t.get("args") or {})
            table[k], shown[k], source[k] = t.get("result"), t.get("shown"), "model"
        if config.CAPTURE_EAGER:
            for name in probes.PROBES:
                k = probes.probe_key(name, {})
                if k not in table:
                    table[k], source[k] = probes.run_probe(signal, name, {}), "eager"
        meta = disp.get("_meta") or {}
        item = {
            "id": f"{signal.get('occurrence_id') or signal.get('fingerprint')}@{stamp}",
            "source": signal.get("source"),
            "frozen_at": now.isoformat(),
            "signal": signal,
            "probes": table,
            "probes_shown": shown,
            "probe_source": source,
            "freeze_dispositions": [disp.get("disposition")],
            "ground_truth": {"disposition": None, "work_type": None, "notes": ""},
            "fleet_decision": {
                "disposition": disp.get("disposition"), "reason": disp.get("reason"),
                "certainty": disp.get("certainty"),
                "work_type": (disp.get("file") or {}).get("work_type"),
                "model": meta.get("model"), "prompt_ver": meta.get("prompt_ver"),
                "prompt_sha": meta.get("prompt_sha"), "gates": meta.get("gates"),
                "cycle_id": os.environ.get("FLEETD_CYCLE_ID", ""),
                "stage": os.environ.get("FLEETD_STAGE", ""),
            },
        }
        os.makedirs(config.CAPTURE_DIR, mode=0o700, exist_ok=True)
        path = os.path.join(config.CAPTURE_DIR, _safe_name(f"{stamp}__{signal.get('fingerprint', '')}") + ".json")
        tmp = path + ".tmp"
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            json.dump(item, f, ensure_ascii=False, default=str)
        os.replace(tmp, path)
        return path
    except Exception as e:  # noqa: BLE001
        print(f"    [capture] skipped: {e}")
        return None
