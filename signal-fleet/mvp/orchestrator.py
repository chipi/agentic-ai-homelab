"""The deterministic orchestrator — first vertical slice (SIGNALS §13.3).

poll -> (idempotency check) -> correlate -> triage -> act -> ledger.
No LLM in the control flow; the model lives only behind triage.triage().

  python3 orchestrator.py               # act on the live orrery-staleness alert
  python3 orchestrator.py --synthetic   # drive the pipeline with a synthetic one
  python3 orchestrator.py --synthetic --no-dry-run   # (blocked: needs target repo)
"""
import argparse
import datetime
import sys

import actions
import config
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


def _spent(disps):
    return sum((d.get("_meta", {}).get("cost_usd") or 0) for d in disps)


def run_once(use_synthetic=False, dry_run=True):
    sig = SYNTHETIC if use_synthetic else sources.orrery_staleness()
    if sig is None:
        print("no orrery-staleness alert firing — nothing to do.")
        return []

    prior = actions.already_done(sig["occurrence_id"])
    if prior:
        print(f"idempotent: occurrence {sig['occurrence_id']} already -> {prior}; skipping.")
        return []

    print(f"signal: {sig['alertname']} | fp: {sig['fingerprint']}")
    disp = triage.triage(sig)   # investigation self-probes (§7.3)
    actions.act(sig, disp, dry_run=dry_run)
    m = disp.get("_meta", {})
    print(f"=> {disp['disposition']} (gates {m.get('gates')} · probes {m.get('n_probes')} · "
          f"certainty {m.get('certainty')})")
    return [disp]


def run_grafana(limit=5, dry_run=True):
    """Generalized Grafana-alert pass (2026-08-05, delivery forcing function):
    EVERY firing non-meta, non-plumbing alert is fleet food — default-in,
    opt-out via meta="true" (substrate boundary). Same spine as the GlitchTip
    pass: occurrence idempotency + fingerprint recurrence with a RETRIAGE_HOURS
    window. kind= stays a probe hint for the triager, never a routing gate."""
    alerts = sources.firing_alerts()
    print(f"grafana firing (non-meta): {len(alerts)}")
    disps = []
    for a in alerts[:limit]:
        sig = sources.to_signal(a)
        prior_occ = actions.already_done(sig["occurrence_id"])
        if prior_occ:
            print(f"  idempotent: {sig['occurrence_id']} -> {prior_occ}; skip")
            continue
        base = actions.last_for_fingerprint(sig["fingerprint"])
        if base and _hours_since(base["ts"]) < config.RETRIAGE_HOURS:
            # same alert, new firing, inside the window: recurrence row, no re-triage
            actions.record_recurrence(sig, base)
            continue
        print(f"--- {sig['alertname'][:60]} (fp {sig['fingerprint']}) ---")
        disp = triage.triage(sig)   # investigation self-probes (§7.3)
        actions.act(sig, disp, dry_run=dry_run)
        disps.append(disp)
        m = disp.get("_meta", {})
        print(f"  => {disp['disposition']} (gates {m.get('gates')} · probes {m.get('n_probes')})")
    return disps


def _hours_since(ts_iso):
    try:
        t = datetime.datetime.fromisoformat(ts_iso.replace("Z", "+00:00"))
        return (datetime.datetime.now(datetime.timezone.utc) - t).total_seconds() / 3600
    except ValueError:
        return 1e9


def run_glitchtip(limit=5, dry_run=True):
    """Phase B: process unresolved GlitchTip errors through the same spine.

    Recurrence handling (R5-4 follow-up + R2-2): a fingerprint that already has
    a disposition and shows NEW events is a `recurrence` ledger row (the
    implicit-overturn signal), not a fresh full-cost triage — unless the last
    triage is older than RETRIAGE_HOURS, in which case one re-triage is due."""
    issues = sources.glitchtip_unresolved(limit)
    print(f"glitchtip unresolved: {len(issues)}")
    disps = []
    for issue in issues:
        sig = sources.to_error_signal(issue)
        prior_occ = actions.already_done(sig["occurrence_id"])
        base = actions.last_for_fingerprint(sig["fingerprint"])
        cur_count = int(sig.get("labels", {}).get("count") or 0)
        if prior_occ:
            if base and cur_count > base["count"] > 0:
                if _hours_since(base["ts"]) < config.RETRIAGE_HOURS:
                    actions.record_recurrence(sig, base)
                    continue
                print(f"  re-triage due (recurred, last look {base['ts']})")
            else:
                print(f"  idempotent: {sig['occurrence_id']} -> {prior_occ}; skip")
                continue
        print(f"--- {sig['alertname'][:60]} (fp {sig['fingerprint']}) ---")
        disp = triage.triage(sig)   # investigation self-probes (§7.3)
        actions.act(sig, disp, dry_run=dry_run)
        disps.append(disp)
        m = disp.get("_meta", {})
        print(f"  => {disp['disposition']} (gates {m.get('gates')} · probes {m.get('n_probes')})")
    return disps


def _file_triager_down(reason, dry_run):
    """Fail-closed handler (#2): the triager is persistently down, so file/update
    ONE aggregate 'triager unavailable' issue on the ops repo — deduped by a fixed
    fingerprint — instead of escalating every signal. Turns an auth outage into one
    ticket, not ~90 (the 2026-08 flood)."""
    sig = {
        "fingerprint": "grafana:fleet-triager-down",
        "occurrence_id": "grafana:fleet-triager-down",
        "source": "grafana",
        "alertname": "signal-fleet triager unavailable",
        "labels": {"meta": "true"},
        "summary": reason,
    }
    issue = {
        "title": "[fleet] triager unavailable — signals unclassified (fail-closed)",
        "labels": ["triage-fleet/substrate"],
        "body": "\n".join([
            "The signal-fleet triager LLM call is failing persistently:", "",
            f"`{reason}`", "",
            "The fleet is failing **CLOSED** — ONE issue for the whole outage, not one "
            "escalation per signal (the 2026-08-13→19 flood was ~90 of those). Signals "
            "this cycle go unclassified until the triager is restored.", "",
            "**Fix:** recreate the litellm virtual key — see `infra/litellm/README.md` "
            "→ *Recreate after a DB wipe*. The fleet then resumes automatically.", "",
            "_signal-fleet fail-closed._"]),
    }
    if dry_run:
        print(f"[TRIAGER-DOWN dry-run] would file/update ONE ops issue: {reason[:120]}")
        return
    import filing
    print(f"[TRIAGER-DOWN fail-closed] {filing.file_or_update(sig, issue, 'substrate')}")


def run_poll(limit=10, dry_run=True):
    """One daemon cycle — every live trigger in one pass (EVAL.md (i)). Each
    source pass is isolated so one failing source never sinks the cycle.

    fleetd cycle contract (RFC-0004): honors FLEETD_STAGE (shadow/propose force
    dry-run regardless of flags — shadow takes NO actions by construction),
    FLEETD_CYCLE_ID lands on every ledger row (actions.py), and total cycle
    spend is written to SPEND_FILE for the daemon's budget guard. Returns the
    number of source passes that crashed (cycle exit code)."""
    import os
    stage = os.environ.get("FLEETD_STAGE", "shadow")
    # Stage semantics (RFC-0004, propose-readiness 2026-07-29): shadow = no
    # external writes (queue drafts only). propose = GH issues/comments ARE the
    # proposal surface (file + escalate act; cleanup stays queued — GlitchTip
    # mutation is live-only). live = everything.
    if stage == "shadow":
        dry_run = True   # hard guarantee: shadow never writes externally
    cid = os.environ.get("FLEETD_CYCLE_ID", "")
    print(f"== signal-fleet cycle {cid or '(manual)'} stage={stage} "
          f"{datetime.datetime.now(datetime.timezone.utc).isoformat()} ==")
    disps, failures = [], 0
    triager_down = None
    try:
        disps += run_grafana(limit=limit, dry_run=dry_run)   # ALL non-meta Grafana alerts
    except triage.TriagerDown as e:
        triager_down = str(e)
    except Exception as e:  # noqa: BLE001
        failures += 1
        print("  grafana pass error:", e)
    if triager_down is None:   # triager down => both passes would fail; skip the rest
        try:
            disps += run_glitchtip(limit=limit, dry_run=dry_run)   # GlitchTip errors
        except triage.TriagerDown as e:
            triager_down = str(e)
        except Exception as e:  # noqa: BLE001
            failures += 1
            print("  glitchtip pass error:", e)
    if triager_down:
        failures += 2   # force a non-zero cycle so the daemon's health flags it too
        _file_triager_down(triager_down, dry_run)
    # operator-inbox surfacing (queue depth, escalations, VL content) —
    # best-effort: the dashboard lagging a cycle must never fail the cycle
    try:
        import inbox
        inbox.push_inbox()
    except Exception as e:  # noqa: BLE001
        print("  inbox push error:", e)
    spend = _spent(disps)
    try:
        with open(config.SPEND_FILE, "w") as f:
            f.write(f"{spend:.6f}\n")
    except OSError as e:
        print("  spend report failed:", e)
    print(f"== cycle done: {len(disps)} triaged, ${spend:.4f}, {failures} source failures ==")
    return failures


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--poll", "--cycle", dest="poll", action="store_true",
                    help="one daemon cycle: grafana + glitchtip (fleetd contract)")
    ap.add_argument("--synthetic", action="store_true", help="synthetic staleness signal")
    ap.add_argument("--glitchtip", action="store_true", help="process unresolved GlitchTip errors")
    ap.add_argument("--limit", type=int, default=5, help="max GlitchTip issues per run")
    ap.add_argument("--no-dry-run", action="store_true", help="really create issues (gated)")
    args = ap.parse_args()
    if args.poll:
        sys.exit(1 if run_poll(limit=args.limit, dry_run=not args.no_dry_run) >= 2 else 0)
    elif args.glitchtip:
        run_glitchtip(limit=args.limit, dry_run=not args.no_dry_run)
    else:
        run_once(use_synthetic=args.synthetic, dry_run=not args.no_dry_run)
