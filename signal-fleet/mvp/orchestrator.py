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
    "occurrence_id": "grafana:synthetic-orrery-stale@2026-07-24T00:00:00Z",
    "source": "grafana",
    "alertname": "Orrery launch data stale (no refresh in 7h)",
    "labels": {"alertname": "Orrery launch data stale"},
    "summary": "synthetic — orrery data refresh alarm; verify against evidence",
    "startsAt": "2026-07-24T00:00:00Z", "raw": {},
}


def run_once(use_synthetic=False, dry_run=True):
    sig = SYNTHETIC if use_synthetic else sources.orrery_staleness()
    if sig is None:
        print("no orrery-staleness alert firing — nothing to do.")
        return

    prior = actions.already_done(sig["occurrence_id"])
    if prior:
        print(f"idempotent: occurrence {sig['occurrence_id']} already -> {prior}; skipping.")
        return

    print(f"signal: {sig['alertname']} | fp: {sig['fingerprint']}")
    ev = correlate.evidence_for_orrery_staleness(sig)
    print("correlated:", {k: (len(v) if isinstance(v, str) else 1)
                          for k, v in ev["queries"].items()})
    disp = triage.triage(sig, ev)
    actions.act(sig, disp, dry_run=dry_run)
    m = disp.get("_meta", {})
    print(f"=> disposition: {disp['disposition']} "
          f"(intent_gate: {m.get('intent_gate')}, dismiss_gate: {m.get('dismiss_gate')}, "
          f"attempt: {m.get('attempt')})")


def run_glitchtip(limit=5, dry_run=True):
    """Phase B: process unresolved GlitchTip errors through the same spine."""
    issues = sources.glitchtip_unresolved(limit)
    print(f"glitchtip unresolved: {len(issues)}")
    for issue in issues:
        sig = sources.to_error_signal(issue)
        prior = actions.already_done(sig["occurrence_id"])
        if prior:
            print(f"  idempotent: {sig['occurrence_id']} -> {prior}; skip")
            continue
        print(f"--- {sig['alertname'][:60]} (fp {sig['fingerprint']}) ---")
        ev = correlate.evidence_for_glitchtip_error(sig)
        print("  correlated:", {k: (len(v) if isinstance(v, str) else "obj")
                                for k, v in ev["queries"].items()})
        disp = triage.triage(sig, ev)
        actions.act(sig, disp, dry_run=dry_run)
        m = disp.get("_meta", {})
        print(f"  => {disp['disposition']} "
              f"(intent_gate:{m.get('intent_gate')}, dismiss_gate:{m.get('dismiss_gate')})")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--synthetic", action="store_true", help="synthetic staleness signal")
    ap.add_argument("--glitchtip", action="store_true", help="process unresolved GlitchTip errors")
    ap.add_argument("--limit", type=int, default=5, help="max GlitchTip issues per run")
    ap.add_argument("--no-dry-run", action="store_true", help="really create issues (blocked)")
    args = ap.parse_args()
    if args.glitchtip:
        run_glitchtip(limit=args.limit, dry_run=not args.no_dry_run)
    else:
        run_once(use_synthetic=args.synthetic, dry_run=not args.no_dry_run)
