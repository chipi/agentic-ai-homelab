"""GitHub filing with cross-day dedup, incident grouping, and hygiene gates.

The contract (operator-reviewed 2026-07-29):
- fingerprint → filed-ledger (results/filed.tsv) → never a duplicate issue:
    * ledger hit + issue OPEN      → rolling recurrence comment (≤1/day)
    * ledger hit + CLOSED <7 days  → reopen + "recurred after close" comment
    * ledger hit + CLOSED ≥7 days  → new issue linking the old (regression)
    * issue carries `triage-fleet/muted` label → do nothing, forever
- GitHub state is READ at file-time (operator close/label IS the ack) —
  never trusted from the local copy.
- Incident grouping: storm rules collapse related fingerprints into one
  group issue; every member fingerprint maps to it in the ledger.
- Hygiene: English-only + title gate (mechanical, not a prompt hope).

All GitHub writes go through _gh(); without GITHUB_TOKEN the module refuses
loudly (propose stage requires a token on this host).
"""
import json
import os
import re
import urllib.request
from datetime import datetime, timedelta, timezone

import config

FILED = os.path.expanduser(os.environ.get("SF_FILED_LEDGER",
                           "~/signal-fleet/results/filed.tsv"))
FILED_COLS = ["fingerprint", "repo", "issue", "group_key", "filed_at", "last_comment_day"]
REOPEN_WINDOW_DAYS = 7
MUTE_LABEL = "triage-fleet/muted"
ESCALATE_LABEL = "triage-fleet/escalated"
FILED_LABEL = "triage-fleet/filed"

# glitchtip project prefix → GitHub repo (operator mapping 2026-07-29).
# Unmapped projects fall back to SF_OPS_REPO; with neither, filing refuses
# (visible, not silent).
REPO_MAP = {
    "ORRERY": "chipi/orrery",
    "LITELLM": "chipi/agentic-ai-homelab",
    "PODCAST": "chipi/podcast_scraper",
    "PLAYER": "chipi/podcast_scraper",
}
OPS_REPO = os.environ.get("SF_OPS_REPO", "")

# storm rules: alertname regex → group key. Curated, reviewed like config.
GROUP_RULES = [
    (re.compile(r"gemini|circuit breaker tripped: provider=gemini|DEADLINE_EXCEEDED|"
                r"high demand|provider_retries_exhausted|503 UNAVAILABLE", re.I),
     "gemini-provider-instability"),
    (re.compile(r"dgx-whisper|resilience fuse", re.I), "dgx-whisper-fuse"),
    (re.compile(r"span batch|span export", re.I), "otel-span-export"),
]


def _now():
    return datetime.now(timezone.utc)


def _today():
    return _now().strftime("%Y-%m-%d")


def group_key_for(alertname, title=""):
    """Match alertname AND drafted title — storms often surface as generic
    transport errors (ReadTimeout) whose cause only the title names."""
    hay = f"{alertname or ''} {title or ''}"
    for rx, key in GROUP_RULES:
        if rx.search(hay):
            return key
    return ""


def repo_for(signal):
    fp = signal.get("fingerprint", "")           # glitchtip:PODCAST-8
    proj = re.sub(r"^glitchtip:", "", fp).rsplit("-", 1)[0]
    proj = re.sub(r"-(DEV|STAGING|\d+)$", "", proj)
    for prefix, repo in REPO_MAP.items():
        if proj.upper().startswith(prefix):
            return repo
    return OPS_REPO


def title_ok(title):
    """Mechanical hygiene gate: no placeholders, no non-English drafting."""
    t = (title or "").strip()
    if len(t) < 12:
        return False
    ascii_ratio = sum(1 for ch in t if ord(ch) < 128) / len(t)
    return ascii_ratio > 0.9


def sanitize_issue(signal, issue):
    """Enforce hygiene mechanically; fall back to a synthesized English title."""
    if not title_ok(issue.get("title", "")):
        alert = re.sub(r"[^\x20-\x7e]", "", signal.get("alertname", ""))[:90]
        issue = dict(issue)
        issue["title"] = f"[{signal.get('source', 'signal')}] {alert or signal.get('fingerprint', 'unnamed signal')}"
    return issue


# ── filed-ledger ─────────────────────────────────────────────────────────
def _ledger_rows():
    if not os.path.exists(FILED):
        return []
    with open(FILED) as f:
        lines = f.read().splitlines()
    return [dict(zip(FILED_COLS, ln.split("\t"))) for ln in lines[1:] if ln]


def _ledger_write(rows):
    with open(FILED, "w") as f:
        f.write("\t".join(FILED_COLS) + "\n")
        for r in rows:
            f.write("\t".join(str(r.get(c, "")) for c in FILED_COLS) + "\n")


def ledger_lookup(fingerprint, group_key=""):
    """Prefer exact fingerprint; else any member of the same group."""
    rows = _ledger_rows()
    for r in rows:
        if r["fingerprint"] == fingerprint:
            return r
    if group_key:
        for r in rows:
            if r["group_key"] == group_key:
                return r
    return None


def ledger_upsert(entry):
    rows = [r for r in _ledger_rows() if r["fingerprint"] != entry["fingerprint"]]
    rows.append(entry)
    _ledger_write(rows)


# ── GitHub REST ──────────────────────────────────────────────────────────
def _gh(method, path, payload=None):
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if not token:
        raise RuntimeError("filing requires GITHUB_TOKEN on this host (propose stage)")
    req = urllib.request.Request(f"https://api.github.com{path}", method=method,
                                 data=json.dumps(payload).encode() if payload else None)
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Accept", "application/vnd.github+json")
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read() or "{}")


def _glitchtip_note(signal, text):
    """Comment the GH link back onto the GlitchTip issue — closes the loop so
    anyone browsing GlitchTip sees 'tracked in GH#N'. Best-effort by design."""
    gt_id = signal.get("issue_id")
    if not gt_id or not config.GLITCHTIP_TOKEN:
        return
    try:
        req = urllib.request.Request(
            f"{config.GLITCHTIP_URL}/api/0/issues/{gt_id}/comments/",
            data=json.dumps({"data": {"text": text}}).encode(), method="POST")
        req.add_header("Authorization", f"Bearer {config.GLITCHTIP_TOKEN}")
        req.add_header("Content-Type", "application/json")
        urllib.request.urlopen(req, timeout=10)
    except Exception as ex:  # noqa: BLE001
        print(f"  filing: glitchtip note failed: {ex}")


def _grafana_annotation(text, tags):
    """Timeline marker on the fleet dashboards (storm/filing events become
    visible on 'Dispositions over time'). Best-effort; skips without creds."""
    user = os.environ.get("GRAFANA_USER")
    pw = os.environ.get("GRAFANA_PASSWORD")
    if not user or not pw:
        return
    import base64
    url = os.environ.get("SF_GRAFANA_URL", config.VM_URL.replace(":8428", ":3000"))
    try:
        req = urllib.request.Request(url + "/api/annotations",
                                     data=json.dumps({"text": text, "tags": tags}).encode(),
                                     method="POST")
        req.add_header("Content-Type", "application/json")
        req.add_header("Authorization", "Basic " +
                       base64.b64encode(f"{user}:{pw}".encode()).decode())
        urllib.request.urlopen(req, timeout=10)
    except Exception as ex:  # noqa: BLE001
        print(f"  filing: grafana annotation failed: {ex}")


def issue_state(repo, number):
    d = _gh("GET", f"/repos/{repo}/issues/{number}")
    labels = [l["name"] for l in d.get("labels", [])]
    closed_at = d.get("closed_at")
    return {"state": d.get("state"), "labels": labels,
            "closed_at": datetime.fromisoformat(closed_at.replace("Z", "+00:00"))
            if closed_at else None,
            "url": d.get("html_url", "")}


# ── the filing decision tree ─────────────────────────────────────────────
def file_or_update(signal, issue, kind):
    """Returns a one-line outcome string (also printed by the caller)."""
    fp = signal.get("fingerprint", "")
    gk = group_key_for(signal.get("alertname", ""), (issue or {}).get("title", ""))
    repo = repo_for(signal)
    if not repo:
        return f"REFUSED: no repo mapping for {fp} and SF_OPS_REPO unset"
    issue = sanitize_issue(signal, issue)
    prior = ledger_lookup(fp, gk)

    if prior:
        st = issue_state(prior["repo"], prior["issue"])
        if MUTE_LABEL in st["labels"]:
            return f"MUTED: {fp} → {prior['repo']}#{prior['issue']} (operator muted)"
        if st["state"] == "open":
            if prior.get("last_comment_day") == _today():
                return f"DEDUP: {fp} already commented today on {prior['repo']}#{prior['issue']}"
            _gh("POST", f"/repos/{prior['repo']}/issues/{prior['issue']}/comments",
                {"body": f"Recurred {_today()}: `{signal.get('alertname', '')[:140]}` "
                         f"(fp `{fp}`). _signal-fleet recurrence tracking._"})
            prior["last_comment_day"] = _today()
            ledger_upsert(prior)
            return f"COMMENTED: recurrence on {prior['repo']}#{prior['issue']}"
        # closed
        age = (_now() - st["closed_at"]).days if st["closed_at"] else 999
        if age < REOPEN_WINDOW_DAYS:
            _gh("PATCH", f"/repos/{prior['repo']}/issues/{prior['issue']}", {"state": "open"})
            _gh("POST", f"/repos/{prior['repo']}/issues/{prior['issue']}/comments",
                {"body": f"Recurred {_today()} after close ({age}d) — reopening. "
                         f"`{signal.get('alertname', '')[:140]}`"})
            prior["last_comment_day"] = _today()
            ledger_upsert(prior)
            _glitchtip_note(signal, f"Recurred after close — reopened GitHub issue "
                                    f"{prior['repo']}#{prior['issue']}")
            _grafana_annotation(f"reopened {prior['repo']}#{prior['issue']} (recurrence after close)",
                                ["signal-fleet", "reopened"])
            return f"REOPENED: {prior['repo']}#{prior['issue']} (closed {age}d ago)"
        issue = dict(issue)
        issue["body"] = (f"Regression of {prior['repo']}#{prior['issue']} "
                         f"(closed {age}d ago).\n\n" + issue.get("body", ""))

    d = _gh("POST", f"/repos/{repo}/issues",
            {"title": issue["title"], "body": issue.get("body", ""),
             "labels": sorted(set((issue.get("labels") or []) + [FILED_LABEL]))})
    ledger_upsert({"fingerprint": fp, "repo": repo, "issue": d["number"],
                   "group_key": gk, "filed_at": _now().isoformat(),
                   "last_comment_day": _today()})
    _glitchtip_note(signal, f"Tracked in GitHub: {d.get('html_url', repo + '#' + str(d['number']))} "
                            f"(filed by signal-fleet{', group ' + gk if gk else ''})")
    _grafana_annotation(f"filed {repo}#{d['number']}: {issue['title'][:80]}",
                        ["signal-fleet", "filed"] + ([gk] if gk else []))
    return f"FILED: {repo}#{d['number']} {issue['title'][:60]}"


def file_escalation(signal, disp):
    """Escalation → GH issue with the fleet's analysis + the gate's refusal."""
    q = disp.get("question", "")
    issue = {
        "title": f"[escalation] {signal.get('alertname', '')[:100]}",
        "labels": [ESCALATE_LABEL],
        "body": "\n".join([
            f"**Signal:** `{signal.get('alertname')}` (fp `{signal.get('fingerprint')}`)",
            "", f"**Fleet analysis:** {disp.get('reason', '')}",
            "", f"**Question for operator:** {q}" if q else "",
            "", "Actions: close = dismiss confirmed · label "
                "`triage-fleet/routed:bugfix` = send to Fleet 1 · comment = "
                "answer, fleet re-triages · label `triage-fleet/muted` = never again.",
            "", "_Escalated by signal-fleet._"]),
    }
    return file_or_update(signal, issue, "escalation")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--flush-queue", action="store_true",
                    help="file the shadow queue through the dedup/grouping tree")
    ap.add_argument("--dry-run", action="store_true", help="print decisions only")
    args = ap.parse_args()
    if args.flush_queue:
        qd = os.path.expanduser("~/signal-fleet/queue")
        seen_fp, seen_gk = set(), set()   # dry-run simulation state, never the real ledger
        for name in sorted(os.listdir(qd)):
            if not name.endswith(".json"):
                continue
            with open(os.path.join(qd, name)) as f:
                item = json.load(f)
            kind = item.get("kind", "bug")
            if kind == "cleanup":
                print(f"SKIP (cleanup never files): {name}")
                continue
            sig, iss = item.get("signal") or {}, item.get("issue") or {}
            fp = sig.get("fingerprint", "")
            gk = group_key_for(sig.get("alertname", ""), (iss.get("title") or ""))
            if args.dry_run:
                dup = fp in seen_fp or (gk and gk in seen_gk) or ledger_lookup(fp, gk)
                verdict = "would COMMENT/group" if dup else "would FILE"
                print(f"{verdict}: [{kind}] {fp} gk={gk or '-'} "
                      f"repo={repo_for(sig) or 'UNMAPPED'} | {(iss.get('title') or '')[:70]}")
                seen_fp.add(fp)
                if gk:
                    seen_gk.add(gk)
            else:
                print(file_or_update(sig, iss, kind))
                os.rename(os.path.join(qd, name), os.path.join(qd, name + ".filed"))
