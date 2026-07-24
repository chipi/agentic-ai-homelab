"""The deterministic orchestrator — first vertical slice (SIGNALS §13.3).

poll -> (idempotency check) -> correlate -> triage -> act -> ledger.
No LLM in the control flow; the model lives only behind triage.triage().

  python3 orchestrator.py               # act on the live orrery-staleness alert
  python3 orchestrator.py --synthetic   # drive the pipeline with a synthetic one
  python3 orchestrator.py --synthetic --no-dry-run   # (blocked: needs target repo)
"""
import argparse

import actions
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


def run_once(use_synthetic=False, dry_run=True):
    sig = SYNTHETIC if use_synthetic else sources.orrery_staleness()
    if sig is None:
        print("no orrery-staleness alert firing — nothing to do.")
        return

    prior = actions.already_done(sig["fingerprint"])
    if prior:
        print(f"idempotent: {sig['fingerprint']} already -> {prior}; skipping.")
        return

    print(f"signal: {sig['alertname']} | fp: {sig['fingerprint']}")
    ev = correlate.evidence_for_orrery_staleness(sig)
    print("correlated:", {k: (len(v) if isinstance(v, str) else 1)
                          for k, v in ev["queries"].items()})
    disp = triage.triage(sig, ev)
    actions.act(sig, disp, dry_run=dry_run)
    print(f"=> disposition: {disp['disposition']} "
          f"(gate: {disp['_meta'].get('gate')}, attempt: {disp['_meta'].get('attempt')})")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--synthetic", action="store_true", help="use a synthetic staleness signal")
    ap.add_argument("--no-dry-run", action="store_true", help="really create issues (blocked)")
    args = ap.parse_args()
    run_once(use_synthetic=args.synthetic, dry_run=not args.no_dry_run)
