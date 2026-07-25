"""Action handlers + the append-only dispositions ledger (SIGNALS §7, §9, §10).

- dismiss: record (propose-first for MVP — no source ack yet). If it carries an
  immediate_recommendation, ALSO emit a `config-enhancement` File (dry-run) — the
  Tune dual output (SIGNALS §7.1 / review R3-3), recorded on the ledger row via the
  `followup` column (review R4-3).
- file:    build the labelled GitHub issue payload; DRY-RUN until the target repo
           is chosen (SIGNALS §13.1 #3).
- escalate: operator note.
Idempotency is keyed on the OCCURRENCE (fingerprint + startsAt), not the
alertname (review R3-1).
"""
import datetime
import hashlib
import json
import os

import config

LEDGER_COLS = ["ts", "occurrence_id", "fingerprint", "source", "alertname",
               "disposition", "work_type", "followup", "model", "prompt_ver",
               "prompt_sha", "gates", "n_probes", "certainty", "reason",
               "signal_count", "cycle_id", "stage"]


def _now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _cell(s):
    return str(s).replace("\t", " ").replace("\n", " ")


def _ensure_ledger_schema():
    """Migrate-once on header mismatch so the overturn dataset never becomes a
    mixed-schema TSV (review R4-1). An old-schema file is set aside, not appended
    to under a stale header."""
    if not os.path.exists(config.LEDGER):
        return
    with open(config.LEDGER) as f:
        header = f.readline().rstrip("\n")
    if header != "\t".join(LEDGER_COLS):
        bak = f"{config.LEDGER}.{_now().replace(':', '').replace('.', '')}.bak"
        os.rename(config.LEDGER, bak)
        print(f"  [ledger] schema changed — archived old ledger to {os.path.basename(bak)}")


def ledger_append(signal, disp, followup=""):
    os.makedirs(os.path.dirname(config.LEDGER), exist_ok=True)
    _ensure_ledger_schema()
    new = not os.path.exists(config.LEDGER)
    meta = disp.get("_meta", {})
    wt = (disp.get("file") or {}).get("work_type", "") if disp.get("disposition") == "file" else ""
    row = [_now(), signal.get("occurrence_id", ""), signal.get("fingerprint", ""),
           signal.get("source", ""), signal.get("alertname", ""), disp["disposition"],
           wt, followup, meta.get("model", ""), meta.get("prompt_ver", ""),
           meta.get("prompt_sha", ""), meta.get("gates", ""), str(meta.get("n_probes", "")),
           meta.get("certainty", "") or "", disp.get("reason", "")[:300],
           str(signal.get("labels", {}).get("count", "")),
           os.environ.get("FLEETD_CYCLE_ID", ""),
           os.environ.get("FLEETD_STAGE", "")]
    with open(config.LEDGER, "a") as f:
        if new:
            f.write("\t".join(LEDGER_COLS) + "\n")
        f.write("\t".join(_cell(x) for x in row) + "\n")


def last_for_fingerprint(fp):
    """Most recent NON-recurrence ledger row for a fingerprint: the baseline a
    recurrence check compares against. Returns {ts, disposition, count} or None."""
    if not os.path.exists(config.LEDGER):
        return None
    fi = LEDGER_COLS.index("fingerprint")
    di = LEDGER_COLS.index("disposition")
    ti = LEDGER_COLS.index("ts")
    ci = LEDGER_COLS.index("signal_count")
    last = None
    with open(config.LEDGER) as f:
        for n, line in enumerate(f):
            if n == 0:
                continue
            p = line.rstrip("\n").split("\t")
            if len(p) > fi and p[fi] == fp and (len(p) <= di or p[di] != "recurrence"):
                cnt = 0
                if len(p) > ci and p[ci].isdigit():
                    cnt = int(p[ci])
                last = {"ts": p[ti], "disposition": p[di] if len(p) > di else "",
                        "count": cnt}
    return last


def record_recurrence(signal, prior):
    """A fingerprint re-fired after a disposition: log it (the implicit-overturn
    signal for Dismiss, review R2-2) without paying for a fresh triage."""
    disp = {"disposition": "recurrence",
            "reason": f"recurred after {prior['disposition']} @ {prior['ts']} "
                      f"(count {prior['count']} -> {signal.get('labels', {}).get('count')})",
            "_meta": {}}
    print(f"[RECURRENCE] {signal.get('fingerprint')} after {prior['disposition']} "
          f"({prior['count']} -> {signal.get('labels', {}).get('count')})")
    ledger_append(signal, disp)


def already_done(occurrence_id):
    """Last disposition for this OCCURRENCE, or None (keyed on occurrence_id so a
    correct Dismiss of one firing never silences the next firing — review R3-1)."""
    if not os.path.exists(config.LEDGER):
        return None
    oi, di = LEDGER_COLS.index("occurrence_id"), LEDGER_COLS.index("disposition")
    last = None
    with open(config.LEDGER) as f:
        for n, line in enumerate(f):
            if n == 0:
                continue  # header
            p = line.rstrip("\n").split("\t")
            if len(p) > max(oi, di) and p[oi] == occurrence_id:
                last = p[di]
    return last


def build_issue(signal, f):
    """GitHub issue payload for a File-shaped item. Label = work_type (the router)."""
    body = [
        f"**Signal:** `{signal.get('alertname')}` "
        f"(source: {signal.get('source')}, fp: `{signal.get('fingerprint')}`)",
        "", f"**Symptom:** {f.get('symptom', '')}",
        "", f"**Area:** {f.get('area', '')}",
        "", "**Acceptance criteria (intent-cited):**",
    ]
    for c in f.get("acceptance", []):
        body.append(f"- {c.get('criterion')}  _(intent: {c.get('intent_source')})_")
    body.append("")
    body.append("**Evidence:**")
    for e in f.get("evidence", []):
        body.append(f"- {e}")
    body.append("")
    body.append("_Filed by signal-fleet MVP._")
    return {"title": f.get("title", ""),
            "labels": [f.get("work_type", "config-enhancement")],
            "body": "\n".join(body)}


def _tune_followup(signal, disp):
    """The File half of the Tune dual output: a config-enhancement built from the
    Dismiss's immediate_recommendation (SIGNALS §7.1). None if no recommendation.

    intent_source is `triager-recommendation` — the triager invented it, no
    operator stated it, so it must NOT masquerade as `operator-rule` (review R4-2).
    This sub-bar source is acceptable ONLY because config-enhancement is
    operator-gated; it is never valid for a `bug` File (which the intent gate
    enforces — `triager-recommendation` is deliberately not in ALLOWED_INTENT)."""
    rec = disp.get("immediate_recommendation")
    if not rec:
        return None
    return {
        "work_type": "config-enhancement",
        "title": f"[config] tune alert: {signal.get('alertname', '')}",
        "symptom": f"Dismissed as false alarm; recurring noise: {disp.get('reason', '')[:180]}",
        "area": "monitoring-config",
        "evidence": [f"signal fingerprint {signal.get('fingerprint')}"],
        "acceptance": [{"criterion": rec, "intent_source": "triager-recommendation"}],
    }


def queue_proposal(signal, issue, kind):
    """Write a File / config-enhancement proposal as a DRAFT to the queue for
    operator review (propose-first — EVAL.md transition (i)). Not a real issue;
    real issue creation is gated on the File-quality eval (transition (iii))."""
    os.makedirs(config.QUEUE_DIR, exist_ok=True)
    fp = (signal.get("fingerprint") or "sig").replace(":", "_").replace("/", "_")
    h = hashlib.sha1((issue.get("title", "")).encode()).hexdigest()[:6]
    path = os.path.join(config.QUEUE_DIR, f"{kind}-{fp}-{h}.json")
    with open(path, "w") as f:
        json.dump({"queued_at": _now(), "kind": kind,
                   "signal": {k: signal.get(k) for k in
                              ("fingerprint", "occurrence_id", "source", "alertname")},
                   "issue": issue}, f, indent=2)
    return path


def act(signal, disp, dry_run=True):
    d = disp["disposition"]
    followup = ""
    if d == "dismiss":
        print(f"[DISMISS] {disp.get('reason', '')[:140]}")
        follow = _tune_followup(signal, disp)
        if follow:
            followup = "config-enhancement"
            p = queue_proposal(signal, build_issue(signal, follow), "config-enhancement")
            print(f"  [+ queued config-enhancement proposal] {os.path.basename(p)}")
    elif d == "cleanup":
        prop = {"title": f"cleanup: {signal.get('alertname', '')}",
                "action": "resolve+tag (NOT delete)", "target": signal.get("fingerprint"),
                "marker": disp.get("marker"), "reason": disp.get("reason", "")[:200]}
        p = queue_proposal(signal, prop, "cleanup")
        print(f"[CLEANUP queued] resolve+tag {signal.get('fingerprint')} (marker: {disp.get('marker')}) "
              f"-> {os.path.basename(p)}")
    elif d == "file":
        if dry_run:
            p = queue_proposal(signal, build_issue(signal, disp["file"]),
                               disp["file"].get("work_type", "bug"))
            print(f"[FILE queued proposal] {os.path.basename(p)}")
        else:
            raise NotImplementedError(
                "real issue creation is gated on the File-quality eval (EVAL.md transition iii)")
    elif d == "escalate":
        q = disp.get("question", "")
        print(f"[ESCALATE -> operator] {disp.get('reason', '')[:130]}"
              + (f"  Q: {q[:110]}" if q else ""))
    ledger_append(signal, disp, followup=followup)
