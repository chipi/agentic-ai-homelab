"""Action handlers + the append-only dispositions ledger (SIGNALS §7, §9, §10).

- dismiss: record (propose-first for MVP — no source ack yet). If it carries an
  immediate_recommendation, ALSO emit a `config-enhancement` File (dry-run) — the
  Tune dual output (SIGNALS §7.1 / review R3-3), so the follow-up half isn't lost.
- file:    build the labelled GitHub issue payload; DRY-RUN until the target repo
           is chosen (SIGNALS §13.1 #3).
- escalate: operator note.
Idempotency is keyed on the OCCURRENCE (fingerprint + startsAt), not the
alertname (review R3-1).
"""
import datetime
import json
import os

import config

LEDGER_COLS = ["ts", "occurrence_id", "fingerprint", "source", "alertname",
               "disposition", "work_type", "model", "prompt_ver", "prompt_sha",
               "gates", "reason"]


def _now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _cell(s):
    return str(s).replace("\t", " ").replace("\n", " ")


def ledger_append(signal, disp):
    os.makedirs(os.path.dirname(config.LEDGER), exist_ok=True)
    new = not os.path.exists(config.LEDGER)
    meta = disp.get("_meta", {})
    wt = (disp.get("file") or {}).get("work_type", "") if disp.get("disposition") == "file" else ""
    gates = f"i:{meta.get('intent_gate', '')}/d:{meta.get('dismiss_gate', '')}"
    row = [_now(), signal.get("occurrence_id", ""), signal.get("fingerprint", ""),
           signal.get("source", ""), signal.get("alertname", ""), disp["disposition"],
           wt, meta.get("model", ""), meta.get("prompt_ver", ""), meta.get("prompt_sha", ""),
           gates, disp.get("reason", "")[:300]]
    with open(config.LEDGER, "a") as f:
        if new:
            f.write("\t".join(LEDGER_COLS) + "\n")
        f.write("\t".join(_cell(x) for x in row) + "\n")


def already_done(occurrence_id):
    """Last disposition for this OCCURRENCE, or None. Keyed on occurrence_id so a
    correct Dismiss of one firing never silences the next firing (review R3-1)."""
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
    Dismiss's immediate_recommendation (SIGNALS §7.1). None if no recommendation."""
    rec = disp.get("immediate_recommendation")
    if not rec:
        return None
    return {
        "work_type": "config-enhancement",
        "title": f"[config] tune alert: {signal.get('alertname', '')}",
        "symptom": f"Dismissed as false alarm; recurring noise: {disp.get('reason', '')[:180]}",
        "area": "monitoring-config",
        "evidence": [f"signal fingerprint {signal.get('fingerprint')}"],
        "acceptance": [{"criterion": rec, "intent_source": "operator-rule"}],
    }


def act(signal, disp, dry_run=True):
    d = disp["disposition"]
    if d == "dismiss":
        print(f"[DISMISS] {disp.get('reason', '')[:160]}")
        follow = _tune_followup(signal, disp)
        if follow:
            print("[+ FILE dry-run: config-enhancement follow-up — Tune dual output §7.1]")
            print(json.dumps(build_issue(signal, follow), indent=2))
    elif d == "file":
        issue = build_issue(signal, disp["file"])
        if dry_run:
            print("[FILE dry-run] would open GitHub issue:")
            print(json.dumps(issue, indent=2))
        else:
            raise NotImplementedError(
                "real issue creation pending target-repo decision (SIGNALS §13.1 #3)")
    elif d == "escalate":
        print(f"[ESCALATE -> operator] {disp.get('reason', '')[:200]}")
    ledger_append(signal, disp)
