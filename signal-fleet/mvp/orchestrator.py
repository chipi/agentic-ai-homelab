"""The deterministic orchestrator — first vertical slice (SIGNALS §13.3).

poll -> (idempotency check) -> correlate -> triage -> act -> ledger.
No LLM in the control flow; the model lives only behind triage.triage().

  python3 orchestrator.py               # act on the live orrery-staleness alert
  python3 orchestrator.py --synthetic   # drive the pipeline with a synthetic one
  python3 orchestrator.py --synthetic --no-dry-run   # (blocked: needs target repo)
"""
import argparse
import datetime

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
    disp = triage.triage(sig)   # investigation self-probes (§7.3)
    actions.act(sig, disp, dry_run=dry_run)
    m = disp.get("_meta", {})
    print(f"=> {disp['disposition']} (gates {m.get('gates')} · probes {m.get('n_probes')} · "
          f"certainty {m.get('certainty')})")


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
        disp = triage.triage(sig)   # investigation self-probes (§7.3)
        actions.act(sig, disp, dry_run=dry_run)
        m = disp.get("_meta", {})
        print(f"  => {disp['disposition']} (gates {m.get('gates')} · probes {m.get('n_probes')})")


def run_poll(limit=10, dry_run=True):
    """Propose-first daemon cycle — every live trigger in one pass (EVAL.md (i)).
    Records + queues; takes no real action. Each source pass is isolated so one
    failing source never sinks the cycle."""
    print(f"== signal-fleet poll {datetime.datetime.now(datetime.timezone.utc).isoformat()} ==")
    try:
        run_once(use_synthetic=False, dry_run=dry_run)   # Grafana alerts
    except Exception as e:  # noqa: BLE001
        print("  grafana pass error:", e)
    try:
        run_glitchtip(limit=limit, dry_run=dry_run)       # GlitchTip errors
    except Exception as e:  # noqa: BLE001
        print("  glitchtip pass error:", e)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--poll", action="store_true", help="propose-first daemon cycle (grafana + glitchtip)")
    ap.add_argument("--synthetic", action="store_true", help="synthetic staleness signal")
    ap.add_argument("--glitchtip", action="store_true", help="process unresolved GlitchTip errors")
    ap.add_argument("--limit", type=int, default=5, help="max GlitchTip issues per run")
    ap.add_argument("--no-dry-run", action="store_true", help="really create issues (gated)")
    args = ap.parse_args()
    if args.poll:
        run_poll(limit=args.limit, dry_run=not args.no_dry_run)
    elif args.glitchtip:
        run_glitchtip(limit=args.limit, dry_run=not args.no_dry_run)
    else:
        run_once(use_synthetic=args.synthetic, dry_run=not args.no_dry_run)
