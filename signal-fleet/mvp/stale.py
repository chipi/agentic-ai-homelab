"""#10 "looks resolved" nudge — an open fleet issue whose signal went quiet.

On 2026-09-30, 49 of 63 open issues in agentic-ai-homelab turned out to be stale:
the condition had resolved (30) or the issue was a duplicate (19), and nothing said
so. The fleet already knows when a signal last occurred: every occurrence lands in
dispositions.tsv, and an alert that is still firing is still firing. This module
decides, deterministically, which open issues look resolved.

The rule (evaluated per open issue the fleet filed):
  - last_seen = the newest occurrence of any of the issue's signals — its ledger
    fingerprints, or any fingerprint with the same alert_key (#9) — OR "now" if one
    of its Grafana alerts is firing right now;
  - stale when last_seen is >= QUIET_DAYS ago AND no human commented in that window.
A stale issue gets one comment and the triage-fleet/stale-candidate label. The fleet
never closes it: closing is the operator's call (fleet-architecture invariant 6).

Blind spot, by construction: "quiet" means quiet on the fleet's signal path. If the
path is broken (on 2026-09-30 LiteLLM's GlitchTip project did not exist, so its errors
never reached the fleet), a live problem looks resolved. The nudge says "no recurrence
seen by the fleet", never "fixed".
"""
import os
from datetime import datetime, timedelta, timezone

import filing

QUIET_DAYS = 7
STALE_LABEL = "triage-fleet/stale-candidate"


def _ts(s):
    return datetime.fromisoformat(str(s).replace("Z", "+00:00"))


def issue_signals(ledger_rows, repo, issue, names):
    """The issue's fingerprints, and the alert_keys they carry. `names` maps a
    fingerprint to (source, alertname) as dispositions.tsv recorded it."""
    fps = {r["fingerprint"] for r in ledger_rows
           if r.get("repo") == repo and str(r.get("issue")) == str(issue)}
    aks = {filing.alert_key(repo, *names[fp]) for fp in fps if fp in names} - {""}
    return fps, aks


def last_seen(fps, aks, repo, occurrences, firing_now, now):
    """occurrences: [(ts, fingerprint, source, alertname)]; firing_now: set of alert
    names firing at `now`. Returns the newest occurrence time (<= now), or None."""
    best, names = None, set()
    for ts, fp, src, name in occurrences:
        t = _ts(ts)
        if t > now:
            continue
        if fp in fps or (aks and filing.alert_key(repo, src, name) in aks):
            names.add(name)
            if best is None or t > best:
                best = t
    # a continuously firing alert records ONE occurrence (at its start) — so an alert
    # firing right now is "seen now", however old its occurrence row is (#71 on 09-30)
    if names & set(firing_now):
        return now
    return best


def is_stale(seen, human_comment_times, now, quiet_days=QUIET_DAYS):
    """True when the signal has been quiet for quiet_days and no human spoke up."""
    if seen is None:
        return False                      # no evidence either way -> never nudge
    window = now - timedelta(days=quiet_days)
    if seen > window:
        return False
    return not any(_ts(t) > window for t in human_comment_times)


def nudge_text(seen, now):
    days = (now - seen).days
    return (f"**Looks resolved?** The fleet has seen no recurrence of this issue's signal "
            f"for {days} days (last seen {seen:%Y-%m-%d %H:%M} UTC), and no one has "
            f"commented since. If it is fixed, close it; if not, remove "
            f"`{STALE_LABEL}` and say why. This is \"quiet on the fleet's signal path\", "
            f"not \"verified fixed\" — a broken signal path looks the same. "
            f"_signal-fleet stale check (#10)._")


def now_utc():
    return datetime.now(timezone.utc)


# ── live pass (once per UTC day from orchestrator.run_poll) ─────────────────────
LAST_RUN = os.path.expanduser(os.environ.get("SF_STALE_LAST_RUN",
                                             "~/signal-fleet/results/.stale_last_run"))


def _is_fleet_comment(body):
    return "signal-fleet" in (body or "") or (body or "").startswith("Recurred")


def _occurrences():
    import csv
    import config
    with open(config.LEDGER) as f:
        return [(d["ts"], d["fingerprint"], d["source"], d["alertname"])
                for d in csv.DictReader(f, delimiter="\t")]


def enabled():
    """Opt-in (SF_STALE_NUDGE=1): the first live pass comments on many issues across
    repos, so it stays a dry run until the operator has seen the list."""
    return os.environ.get("SF_STALE_NUDGE", "0") == "1"


def run_pass(dry_run=True, now=None, force=False):
    """Nudge stale open fleet issues. Once per UTC day unless force. Returns a summary
    string. Never closes an issue; skips muted and already-nudged ones. Writes only
    when not dry_run AND enabled()."""
    import urllib.parse
    import sources
    dry_run = dry_run or not enabled()
    now = now or now_utc()
    today = now.strftime("%Y-%m-%d")
    if not force and os.path.exists(LAST_RUN) and open(LAST_RUN).read().strip() == today:
        return "stale: already ran today"
    ledger = filing._ledger_rows()
    occ = _occurrences()
    names = {}
    for ts, fp, src, name in occ:
        names.setdefault(fp, (src, name))
    firing = {a.get("labels", {}).get("alertname", "") for a in sources.firing_alerts()}
    nudged, checked = [], 0
    for repo in sorted({r["repo"] for r in ledger if r.get("repo")}):
        q = f'repo:{repo} is:issue is:open label:"{filing.FILED_LABEL}"'
        items = filing._gh("GET", "/search/issues?per_page=100&q=" + urllib.parse.quote(q)).get("items") or []
        for it in items:
            labels = {l["name"] for l in it.get("labels", [])}
            if STALE_LABEL in labels or filing.MUTE_LABEL in labels:
                continue
            checked += 1
            fps, aks = issue_signals(ledger, repo, it["number"], names)
            if not fps:
                continue                  # not a ledger issue: never ours to nudge
            seen = last_seen(fps, aks, repo, occ, firing, now)
            comments = filing._gh("GET", f"/repos/{repo}/issues/{it['number']}/comments?per_page=100")
            human = [c["created_at"] for c in comments if not _is_fleet_comment(c.get("body"))]
            if not is_stale(seen, human, now):
                continue
            nudged.append(f"{repo}#{it['number']}")
            if not dry_run:
                filing._ensure_labels(repo, {STALE_LABEL})
                filing._gh("POST", f"/repos/{repo}/issues/{it['number']}/comments",
                           {"body": nudge_text(seen, now)})
                filing._gh("POST", f"/repos/{repo}/issues/{it['number']}/labels",
                           {"labels": [STALE_LABEL]})
    if not force:                         # a dry pass also counts as today's run —
        with open(LAST_RUN, "w") as f:    # else shadow would re-query GitHub every cycle
            f.write(today + "\n")
    return (f"stale: checked {checked} open fleet issues, "
            f"{'would nudge' if dry_run else 'nudged'} {len(nudged)}: {', '.join(nudged) or '-'}")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="comment + label (default: dry run)")
    a = ap.parse_args()
    print(run_pass(dry_run=not a.apply, force=True))
