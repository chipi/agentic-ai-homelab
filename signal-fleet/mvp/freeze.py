"""Freeze live signals + their PROBE->RESPONSE tables into reference fixtures
(EVAL.md §3.1/§4, SIGNALS §7.3).

The investigation loop self-probes, so what must be frozen is no longer a single
evidence bundle — it's the probe->response table: every typed probe the triager
might request, mapped to its live response. Replaying against that frozen table is
what makes k-runs measure the MODEL's judgement, not live evidence drift.

Because the model is NOT perfectly deterministic in which probe it picks (deepseek
MoE drifts even at temp 0), freezing only the model's one observed path leaves the
table thin: a replay that requests an unfrozen probe gets a sentinel, which degrades
the disposition (usually -> escalate) and CONFOUNDS model-judgement variance with
table-coverage gaps. So freeze eagerly runs the WHOLE probe menu at default args
(only 6 probes) PLUS the exact args the model actually used — the union covers every
probe NAME the model can request at replay, so a table miss is rare (novel args only)
and the scorer measures judgement, not coverage. Probe responses are deterministic
functions of (signal, args), so the union is well-defined.

Basic redaction: IPv4 -> <ip>. Fixtures land in REFERENCE_DIR (mini-local, NOT the
repo) — they contain real logs; review before ever committing (data-hygiene rule).

  SF_OBSERV_DISABLED=1 python3 freeze.py        # freeze orrery-staleness + GlitchTip
"""
import datetime
import json
import os
import re

import config
import probes
import scrub as _scrub
import sources
import triage

FREEZE_K = int(config.env("SF_FREEZE_K", "2"))  # model passes to capture arg variance


def _redact(obj):
    # full scrub (secrets + identifiers -> synthetic), so frozen fixtures are safe to
    # commit to the PUBLIC repo. Supersedes the old IPv4-only redaction. See scrub.py.
    return _scrub.scrub(obj)


class _RecordingTable:
    """A probe table that runs LIVE on a miss and records the response, so an
    investigation pass captures the probe->response map. Duck-typed to what
    probes.run_probe needs (`.get(key, default)`), so triage/probes stay untouched.
    Accumulates across passes -> union of every probe the model requested."""

    def __init__(self, signal):
        self.signal = signal
        self.table = {}

    def __contains__(self, key):
        # run_probe's replay path membership-tests and iterates the table; a
        # recording table "contains" every key (it records on demand)
        return True

    def __iter__(self):
        return iter(self.table)

    def __getitem__(self, key):
        return self.get(key)

    def get(self, key, default=None):
        if key in self.table:
            return self.table[key]
        name, _, argstr = key.partition(":")
        args = json.loads(argstr) if argstr else {}
        val = probes.run_probe(self.signal, name, args, table=None)  # live
        self.table[key] = val
        return val


def _record_probe_table(signal):
    rt = _RecordingTable(signal)
    # eager menu pass — cover every probe NAME at default args so a replay can't miss
    # on probe SELECTION (the dominant source of model nondeterminism).
    for name in probes.PROBES:
        rt.get(probes.probe_key(name, {}))
    # model pass(es) — capture the exact (often non-default) args the model chooses.
    dispositions = []
    for _ in range(max(1, FREEZE_K)):
        d = triage.investigate(signal, probe_table=rt)
        dispositions.append(d.get("disposition"))
    return rt.table, dispositions


def _existing_ground_truth(path):
    """Carry a set ground_truth forward across a re-freeze — a re-freeze must never
    wipe an operator label."""
    if os.path.exists(path):
        try:
            prev = (json.load(open(path)).get("ground_truth") or {})
            if prev.get("disposition"):
                return prev
        except Exception:  # noqa: BLE001
            pass
    return {"disposition": None, "work_type": None, "notes": ""}


def _write(fid, signal, probe_table, source, seen_dispositions):
    os.makedirs(config.REFERENCE_DIR, exist_ok=True)
    path = os.path.join(config.REFERENCE_DIR, f"{fid}.json")
    fixture = {
        "id": fid,
        "source": source,
        "frozen_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "signal": _redact(signal),
        # the frozen probe->response table the scorer replays against. Scrub keys AND
        # values with the SAME deterministic rules (scrub.py): a probe key can embed a
        # trace_id, and scrubbing both sides identically keeps the frozen key matching
        # the key the scorer rebuilds from the scrubbed signal at replay.
        "probes": _redact(probe_table),
        # what the model actually did during freeze (a hint for labeling, NOT truth):
        "freeze_dispositions": seen_dispositions,
        # OPERATOR fills this (the human oracle — EVAL.md §4 sourcing #2). Preserved
        # across re-freezes so relabelling and re-freezing are independent steps.
        "ground_truth": _existing_ground_truth(path),
    }
    with open(path, "w") as f:
        json.dump(fixture, f, indent=2, ensure_ascii=False)
    print(f"froze {os.path.basename(path)}  ({len(probe_table)} probes, "
          f"freeze-runs -> {seen_dispositions})")


def freeze_glitchtip(limit=20):
    for issue in sources.glitchtip_unresolved(limit):
        sig = sources.to_error_signal(issue)
        table, disps = _record_probe_table(sig)
        fid = "glitchtip-" + sig["fingerprint"].split(":")[-1]
        _write(fid, sig, table, "glitchtip", disps)


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
    table, disps = _record_probe_table(sig)
    _write("grafana-orrery-stale", sig, table, "grafana", disps)


def refreeze_existing():
    """Re-record the probe table for every already-captured fixture, reading its
    STORED signal (no live source re-fetch). Migrates legacy evidence-schema fixtures
    to the probe-table schema; skips fixtures already on the new schema. Labels are
    preserved by _write, so this is safe to run after relabelling."""
    for fn in sorted(os.listdir(config.REFERENCE_DIR)):
        if not fn.endswith(".json"):
            continue
        d = json.load(open(os.path.join(config.REFERENCE_DIR, fn)))
        if "probes" in d:
            print(f"skip {fn} (already probe-schema)")
            continue
        sig = d.get("signal")
        if not sig:
            print(f"skip {fn} (no stored signal)")
            continue
        table, disps = _record_probe_table(sig)
        _write(d["id"], sig, table, d.get("source", ""), disps)


if __name__ == "__main__":
    import sys
    if "--refreeze" in sys.argv:
        refreeze_existing()
        raise SystemExit(0)
    if not config.OBSERV_DISABLED:
        print("note: SF_OBSERV_DISABLED not set — freeze passes will emit fleet "
              "traces/metrics. Set SF_OBSERV_DISABLED=1 to suppress.")
    freeze_orrery_staleness()
    freeze_glitchtip()
    print(f"\nfixtures in {config.REFERENCE_DIR} — fill ground_truth, then score.py")
