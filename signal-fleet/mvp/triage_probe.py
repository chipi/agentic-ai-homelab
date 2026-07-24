"""End-to-end probe of signal -> correlate -> triage (no action).

Uses the live orrery-staleness signal if firing, else a synthetic one, pulls the
real correlated evidence, and runs the triager. Prints the structured disposition.
"""
import json

import correlate
import sources
import triage

SYNTHETIC = {
    "fingerprint": "grafana:synthetic-orrery-stale",
    "source": "grafana",
    "alertname": "Orrery launch data stale (no refresh in 7h)",
    "labels": {"alertname": "Orrery launch data stale"},
    "summary": "synthetic — orrery data refresh alarm; verify against evidence",
    "startsAt": None, "raw": {},
}


def main():
    sig = sources.orrery_staleness()
    print("LIVE signal" if sig else "no live signal -> synthetic")
    sig = sig or SYNTHETIC
    ev = correlate.evidence_for_orrery_staleness(sig)
    print("evidence queries:", {k: (len(v) if isinstance(v, str) else 1)
                                 for k, v in ev["queries"].items()})
    disp = triage.triage(sig, ev)
    print("=== DISPOSITION ===")
    print(json.dumps(disp, indent=2))


if __name__ == "__main__":
    main()
