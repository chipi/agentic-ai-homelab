"""Action handlers + the append-only dispositions ledger (SIGNALS §7, §9, §10).

- dismiss: record (propose-first for MVP — no source ack yet).
- file:    build the labelled GitHub issue payload; DRY-RUN until the target repo
           is chosen (SIGNALS §13.1 #3). work_type label routes it.
- escalate: operator note.
Every disposition is appended to the ledger (idempotency + overturn dataset).
"""
import datetime
import json
import os

import config


def _now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _cell(s):
    return str(s).replace("\t", " ").replace("\n", " ")


def ledger_append(signal, disp):
    os.makedirs(os.path.dirname(config.LEDGER), exist_ok=True)
    new = not os.path.exists(config.LEDGER)
    meta = disp.get("_meta", {})
    wt = (disp.get("file") or {}).get("work_type", "") if disp.get("disposition") == "file" else ""
    with open(config.LEDGER, "a") as f:
        if new:
            f.write("ts\tfingerprint\tsource\talertname\tdisposition\twork_type\t"
                    "model\tprompt_ver\tgate\treason\n")
        f.write("\t".join(_cell(x) for x in [
            _now(), signal["fingerprint"], signal["source"], signal.get("alertname", ""),
            disp["disposition"], wt, meta.get("model", ""), meta.get("prompt_ver", ""),
            meta.get("gate", ""), disp.get("reason", "")[:300],
        ]) + "\n")


def already_done(fingerprint):
    """Idempotency: last recorded disposition for this fingerprint, or None."""
    if not os.path.exists(config.LEDGER):
        return None
    last = None
    with open(config.LEDGER) as f:
        for line in f:
            p = line.rstrip("\n").split("\t")
            if len(p) >= 5 and p[1] == fingerprint:
                last = p[4]
    return last


def build_issue(signal, f):
    """The GitHub issue payload for a File disposition. Label = work_type (router)."""
    body = [
        f"**Signal:** `{signal.get('alertname')}` "
        f"(source: {signal['source']}, fp: `{signal['fingerprint']}`)",
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


def act(signal, disp, dry_run=True):
    d = disp["disposition"]
    if d == "dismiss":
        print(f"[DISMISS] {disp.get('reason', '')[:160]}")
        rec = disp.get("immediate_recommendation")
        if rec:
            print(f"          rec (config-enhancement candidate): {rec[:160]}")
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
