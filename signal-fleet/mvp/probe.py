"""Live probe for the trigger + correlation halves of the first slice.

Proves: (1) the fleet can poll Grafana for firing alerts, (2) the correlation
queries return real orrery evidence. If the orrery-staleness alert isn't firing,
a synthetic signal drives the correlation test so the query surface is still
exercised.
"""
import json

import correlate
import sources


def _preview(val, n=220):
    s = val if isinstance(val, str) else json.dumps(val)
    return f"{len(s)} chars :: " + s[:n].replace("\n", " ")


def main():
    print("== firing alerts (Grafana poll) ==")
    try:
        fa = sources.firing_alerts()
        print("active_count:", len(fa))
        for a in fa[:10]:
            print("  -", a.get("labels", {}).get("alertname"))
    except Exception as e:
        print("  grafana poll ERROR:", e)

    sig = sources.orrery_staleness()
    if sig is None:
        print("== no live orrery-staleness signal -> synthetic (correlation test) ==")
        sig = {
            "fingerprint": "grafana:synthetic-orrery-stale",
            "source": "grafana",
            "alertname": "Orrery launch data stale (no refresh in 7h)",
            "labels": {"alertname": "Orrery launch data stale"},
            "summary": "synthetic — orrery data refresh has not run in 7h",
            "startsAt": None, "raw": {},
        }
    else:
        print("== LIVE orrery-staleness signal ==")
    print("signal:", sig["alertname"], "| fp:", sig["fingerprint"])

    print("== correlated evidence bundle ==")
    ev = correlate.evidence_for_orrery_staleness(sig)
    for name, val in ev["queries"].items():
        print(f"  [{name}] {_preview(val)}")


if __name__ == "__main__":
    main()
