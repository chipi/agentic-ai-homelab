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
import hashlib
import json
import os
import re
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

import config

# #8 — new signals drop into this milestone so release-planning sees them (184/200
# open issues had no milestone at the cleanup pass). Resolve-or-skip; never fail a file.
DEFAULT_MILESTONE = os.environ.get("SF_TRIAGE_MILESTONE", "triage")

FILED = os.path.expanduser(os.environ.get("SF_FILED_LEDGER",
                           "~/signal-fleet/results/filed.tsv"))
# norm_key (#1) appended LAST so old 6-col rows zip short and simply lack it —
# every read is `.get("norm_key","")`. This is `filed.tsv`, a SEPARATE ledger from
# config.LEDGER (dispositions.tsv, migrated by actions._ensure_ledger_schema).
FILED_COLS = ["fingerprint", "repo", "issue", "group_key", "filed_at",
              "last_comment_day", "norm_key"]

# ── #1 normalized dedup key ──────────────────────────────────────────────────
# GlitchTip mints a new shortId per unique event fingerprint, and its fingerprint
# embeds volatile per-occurrence tokens (episode hashes, byte counts, paths, run
# ids) → one logical bug fragments into N `glitchtip:*` fps → N issues. We compute
# a STABLE key by stripping volatile tokens from the title skeleton, then keying on
# (source, exception type, skeleton, crash frame). The 2026-08-27 cleanup pass: this
# alone collapses ~40% of the volume (audio-eviction #1840-49, ADR-148 #1556-1866).
NORM_KEY_VERSION = "v1"
# order matters, most-specific first. CONSERVATIVE by design: over-collapse hides a
# real bug (review R3), so we strip only unambiguously-volatile tokens and leave
# small integers / HTTP codes intact (under-collapse is the safe failure).
_VOLATILE = [
    (re.compile(r"\brun-\d{8}T\d{6}(?:\.\d+)?Z?\b"), "<run>"),          # run ids
    (re.compile(r"\b\d{4}-\d{2}-\d{2}[T ][\d:.]+Z?\b"), "<t>"),          # ISO timestamps
    (re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
                r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"), "<id>"),             # UUIDs
    # hex ids/hashes (episode ids) — MUST contain a hex letter, else a long DECIMAL
    # byte-count (69782850) matches here as <id> while a shorter one (551488) hits
    # the number rule as <n>: same template, two placeholders, no collapse.
    (re.compile(r"\b(?=[0-9a-f]*[a-f])[0-9a-f]{8,}\b", re.I), "<id>"),
    (re.compile(r"(?:/[\w.\-]+){2,}/?"), "<path>"),                      # filesystem paths
    (re.compile(r"\$\d+(?:\.\d+)?"), "<$>"),                             # dollar amounts
    (re.compile(r"\b\d{4,}\b"), "<n>"),                                  # byte counts / big ints
    (re.compile(r"\[\d+\]"), "[n]"),                                     # bracket counters [10]
]


def _normalize_skeleton(text):
    """Collapse a message to its volatile-free skeleton (lowercased, ws-collapsed)."""
    s = text or ""
    for rx, repl in _VOLATILE:
        s = rx.sub(repl, s)
    return re.sub(r"\s+", " ", s).strip().lower()


def normalized_key(signal, event_summary=None):
    """Stable dedup key across occurrences of the same logical bug. Prefers the
    event summary's raised type + crash frame (#5); else falls back to the GlitchTip
    issue metadata.type + culprit carried on the signal. Returns "" (never matches)
    when there is nothing stable to key on."""
    raw = signal.get("raw") or {}
    es = event_summary or {}
    exc_type = (es.get("exc_type")
                or (raw.get("metadata") or {}).get("type") or "").strip()
    frame = (es.get("top_frame")
             or raw.get("culprit")
             or (signal.get("labels") or {}).get("culprit") or "").strip()
    skeleton = _normalize_skeleton(signal.get("alertname") or es.get("message") or "")
    if not (skeleton or exc_type or frame):
        return ""
    basis = f"{signal.get('source', '')}|{exc_type}|{skeleton}|{frame}"
    # Grafana has empty exc_type/frame, so the key would rest on the alertname alone
    # → the SAME alert on two different boxes collapses, and repo_for routes by
    # instance → one box's incident buried in another repo's issue (Fable review F3).
    # Append the instance for grafana only, so GlitchTip keys stay byte-identical.
    if signal.get("source") == "grafana":
        inst = (signal.get("labels") or {}).get("instance", "")
        if inst:
            basis += f"|{inst}"
    return f"{NORM_KEY_VERSION}:" + hashlib.sha1(basis.encode()).hexdigest()[:12]
REOPEN_WINDOW_DAYS = 7
MUTE_LABEL = "triage-fleet/muted"
ESCALATE_LABEL = "triage-fleet/escalated"
FILED_LABEL = "triage-fleet/filed"
ACTIONABLE_LABEL = "triage-fleet/actionable"
ROUTE_LABEL = "triage-fleet/routed:bugfix"
# repos Fleet 1's chain can actually build+test today (B3 extends this)
CHAIN_REPOS = {"chipi/orrery"}

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
    # 2026-08 flood classes — collapse distinct-fingerprint same-class signals onto
    # ONE group issue (the 2nd+ finds the group via ledger_lookup(fp, group_key) and
    # comments, not files). Belt-and-suspenders behind triage's operational gate,
    # which already dismisses most of these; a group rule catches any that reach FILE.
    (re.compile(r"cost soft cap|cost cap exceeded|costcapexceeded|soft[- ]?cap exceeded", re.I),
     "cost-cap"),
    (re.compile(r"no budget|no credit|insufficient (credit|budget|fund)|\b402\b|"
                r"out of credit|quota exceeded", re.I),
     "provider-budget"),
    (re.compile(r"openaiprovider not initialized|provider not initialized|"
                r"fallback tier failed|fallback failed|summarization failed|summariz\w* fail", re.I),
     "provider-fallback"),
]


# ── #4 low-signal gating → per-bucket rollup ─────────────────────────────────
# A single-occurrence, no-user-impact, unsymbolicated event is not worth its own
# issue (handover #1345: one unsymbolicated iOS SIGABRT). We do NOT dismiss it
# (that would risk false-dismiss — a real bug's FIRST hit is low-signal too); we
# FILE it onto ONE per-bucket rollup issue. When the same bug later crosses the
# threshold (recurs / gains users), it is PROMOTED out of the rollup into its own
# issue (review R6). Bucket = project/source (deterministic — NOT the LLM area).
ROLLUP_PREFIX = "low-signal:"


def low_signal(signal):
    """Deterministic: a sub-threshold event — ≤1 occurrence AND 0 users affected
    AND no symbolicated location. Reads the GlitchTip issue fields on the signal.

    SOURCE-GUARDED (Fable pre-deploy review F1): only GlitchTip issue-shaped signals
    carry occurrence evidence (count/userCount/culprit). A Grafana alert has none —
    so "evidence absent" must NOT read as "low", else EVERY Grafana alert (incl.
    orrery-staleness and the fail-closed substrate issue) would be buried in the
    rollup with promotion permanently unreachable (count is always 0)."""
    raw = signal.get("raw") or {}
    labels = signal.get("labels") or {}
    if signal.get("source") != "glitchtip":
        return False
    if "count" not in raw and "count" not in labels:
        return False   # evidence-present required — never infer low from absence

    def _int(*vals):
        for v in vals:
            try:
                return int(v)
            except (TypeError, ValueError):
                continue
        return 0

    count = _int(raw.get("count"), labels.get("count"))
    users = _int(raw.get("userCount"))
    culprit = (raw.get("culprit") or labels.get("culprit") or "").strip()
    return count <= 1 and users == 0 and not culprit


def rollup_bucket(signal):
    """The deterministic rollup bucket for a low-signal event."""
    return (signal.get("labels") or {}).get("project") or signal.get("source") or "misc"


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


# grafana-source signals: route by instance label (which BOX the symptom is
# on); homelab-operated boxes fall through to the homelab ops repo.
INSTANCE_REPO_MAP = {
    "prod-podcast": "chipi/podcast_scraper",
}
OPS_REPO_DEFAULT = "chipi/agentic-ai-homelab"


def repo_for(signal):
    fp = signal.get("fingerprint", "")           # glitchtip:PODCAST-8 | grafana:<hash>
    if fp.startswith("grafana:"):
        inst = (signal.get("labels") or {}).get("instance", "")
        return INSTANCE_REPO_MAP.get(inst, OPS_REPO or OPS_REPO_DEFAULT)
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


def ledger_lookup(fingerprint, group_key="", norm_key=""):
    """Newest matching row, strongest dimension first: exact fingerprint → group_key
    (storm) → norm_key (normalized dedup #1). Returns the row with an added `_dim`
    naming which dimension matched, or None.

    NEWEST-row (not first): multiple rows can share a group_key/norm_key (upsert
    dedups on fingerprint only), and first-match returns the OLDEST — after one
    regression cycle that resolves to a stale closed issue (review R3). Empty keys
    never match (a keyless row must not match every other keyless row)."""
    rows = _ledger_rows()

    def newest(pred):
        hit = None
        for r in rows:
            if pred(r):
                hit = r
        return dict(hit) if hit else None

    r = newest(lambda r: r.get("fingerprint") == fingerprint)
    if r:
        r["_dim"] = "fingerprint"
        return r
    if group_key:
        r = newest(lambda r: r.get("group_key") == group_key)
        if r:
            r["_dim"] = "group_key"
            return r
    if norm_key:  # truthy-only → empty norm_key can never match
        r = newest(lambda r: r.get("norm_key", "") == norm_key)
        if r:
            r["_dim"] = "norm_key"
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


def _file_rollup(signal, issue, repo, fp, nk):
    """Fold a low-signal event onto ONE per-bucket rollup issue (#4). Finds an open
    rollup for the bucket via the ledger; comments the occurrence, else opens it.
    Maps this fp/norm_key to the rollup so the event's own recurrences land here."""
    bucket = rollup_bucket(signal)
    roll_gk = f"{ROLLUP_PREFIX}{bucket}"
    existing = None
    for r in _ledger_rows():
        if r.get("group_key") == roll_gk:
            existing = r                      # newest wins
    occ = f"- {_today()}: `{signal.get('alertname', '')[:160]}` (fp `{fp}`)"
    if existing:
        st = issue_state(existing["repo"], existing["issue"])
        if st["state"] != "open":
            existing = None                   # closed rollup — open a fresh one
    if existing:
        _gh("POST", f"/repos/{existing['repo']}/issues/{existing['issue']}/comments",
            {"body": f"Low-signal occurrence:\n{occ}\n_folded by signal-fleet (#4)._"})
        ledger_upsert({"fingerprint": fp, "repo": existing["repo"], "issue": existing["issue"],
                       "group_key": roll_gk, "filed_at": _now().isoformat(),
                       "last_comment_day": _today(), "norm_key": nk})
        return f"ROLLED-UP: {existing['repo']}#{existing['issue']} ({bucket})"
    body = (f"**Low-signal aggregate — {bucket}**\n\n"
            f"Sub-threshold events (≤1 occurrence, no users affected, unsymbolicated) "
            f"are folded here instead of individual issues (signal-fleet #4). Any that "
            f"later crosses the threshold is promoted to its own issue.\n\n{occ}")
    d = _gh("POST", f"/repos/{repo}/issues",
            {"title": f"[low-signal] aggregate — {bucket}", "body": body,
             "labels": sorted({FILED_LABEL, "triage-fleet/low-signal"})})
    ledger_upsert({"fingerprint": fp, "repo": repo, "issue": d["number"],
                   "group_key": roll_gk, "filed_at": _now().isoformat(),
                   "last_comment_day": _today(), "norm_key": nk})
    return f"ROLLUP-OPENED: {repo}#{d['number']} ({bucket})"


# ── #7 cross-link + #8 label/milestone helpers (all best-effort, never fatal) ──
def _related_issues(repo, signal, limit=2):
    """#7 — open filed issues in the repo sharing this signal's crash function, to
    cross-link 'possibly related'. Best-effort: any error → no links. Fuzzy by
    design (advisory, not a merge — a wrong link is cheap, a missed one costs nothing)."""
    frame = ((signal.get("raw") or {}).get("culprit")
             or (signal.get("labels") or {}).get("culprit") or "").strip()
    kw = frame.split()[-1] if frame else ""       # the function/symbol token
    if len(kw) < 3:
        return []
    try:
        q = f'repo:{repo} is:issue is:open label:"{FILED_LABEL}" "{kw}"'
        r = _gh("GET", "/search/issues?q=" + urllib.parse.quote(q))
        return [it["number"] for it in (r.get("items") or [])[:limit]]
    except Exception:                              # noqa: BLE001
        return []


def _ensure_labels(repo, labels):
    """Best-effort: create any label that may not exist so the issue POST can't 422
    on an unknown label. Idempotent — an already-exists 422 is swallowed."""
    for name in labels:
        try:
            _gh("POST", f"/repos/{repo}/labels", {"name": name})
        except Exception:                          # noqa: BLE001
            pass


def _milestone_number(repo, title):
    """#8 — resolve an OPEN milestone by title to its number, or None (skip). Never
    creates one and never fails a file."""
    if not title:
        return None
    try:
        for m in _gh("GET", f"/repos/{repo}/milestones?state=open") or []:
            if m.get("title") == title:
                return m.get("number")
    except Exception:                              # noqa: BLE001
        pass
    return None


# ── the filing decision tree ─────────────────────────────────────────────
def file_or_update(signal, issue, kind):
    """Returns a one-line outcome string (also printed by the caller)."""
    fp = signal.get("fingerprint", "")
    gk = group_key_for(signal.get("alertname", ""), (issue or {}).get("title", ""))
    nk = normalized_key(signal)
    repo = repo_for(signal)
    if not repo:
        return f"REFUSED: no repo mapping for {fp} and SF_OPS_REPO unset"
    issue = sanitize_issue(signal, issue)
    prior = ledger_lookup(fp, gk, nk)

    # #4 promotion (review R6) — checked BEFORE the mute gate (Fable pre-deploy
    # review) so a signal that has crossed the threshold escapes a MUTED rollup
    # instead of inheriting its mute: muting the low-signal aggregate must not bury
    # a bug that later became real.
    if prior and str(prior.get("group_key", "")).startswith(ROLLUP_PREFIX) \
            and not low_signal(signal):
        issue = dict(issue)
        issue["body"] = (f"Promoted out of low-signal rollup "
                         f"{prior['repo']}#{prior['issue']} — crossed threshold "
                         f"(recurred / gained users).\n\n" + issue.get("body", ""))
        prior = None

    st = None
    if prior:
        st = issue_state(prior["repo"], prior["issue"])
        if MUTE_LABEL in st["labels"]:
            # A norm_key hit is a FUZZY match; inheriting a mute across it would
            # silently bury a DIFFERENT bug the operator never muted (review R3).
            # Exact fp / group_key hits honor mute; norm_key hits file fresh.
            if prior.get("_dim") == "norm_key":
                prior = None
            else:
                return f"MUTED: {fp} → {prior['repo']}#{prior['issue']} (operator muted)"

    if prior:
        # backfill norm_key onto an old (pre-#1) fingerprint row so future
        # occurrences dedup on it too; never clobber a different bug's key
        if prior.get("_dim") == "fingerprint" and not prior.get("norm_key"):
            prior["norm_key"] = nk
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

    # #4 low-signal: a genuinely-new sub-threshold event folds onto the per-bucket
    # rollup instead of getting its own issue (never a dismiss — protects
    # false-dismiss). A regression (prior truthy) is NOT low-signal-routed. Nor are
    # escalations/substrate issues (Fable review F2): those carry an operator
    # question / outage notice that MUST land as its own issue, not a rollup comment.
    if not prior and kind not in ("escalation", "substrate") and low_signal(signal):
        return _file_rollup(signal, issue, repo, fp, nk)

    labels = set((issue.get("labels") or []) + [FILED_LABEL])
    body = issue.get("body", "")
    # routability proposal: the fleet assesses, the operator dispatches —
    # `bug` in a chain-capable repo gets the actionable marker so the operator's
    # GH filter (label:triage-fleet/actionable) IS the routing inbox
    if kind == "bug" and repo in CHAIN_REPOS:
        labels.add(ACTIONABLE_LABEL)
        body += (f"\n\n**Fleet 1 assessment: routable** — repo is chain-capable and "
                 f"acceptance is testable. Add `{ROUTE_LABEL}` to dispatch the bug-fix fleet.")
    # #7 cross-link possibly-related open issues (advisory, best-effort)
    related = _related_issues(repo, signal)
    if related:
        body += "\n\n**Possibly related:** " + ", ".join(f"#{n}" for n in related)
    # #8 area/verdict labels must exist; drop new signals into the triage milestone
    _ensure_labels(repo, labels)
    payload = {"title": issue["title"], "body": body, "labels": sorted(labels)}
    ms = _milestone_number(repo, DEFAULT_MILESTONE)
    if ms:
        payload["milestone"] = ms
    d = _gh("POST", f"/repos/{repo}/issues", payload)
    ledger_upsert({"fingerprint": fp, "repo": repo, "issue": d["number"],
                   "group_key": gk, "filed_at": _now().isoformat(),
                   "last_comment_day": _today(), "norm_key": nk})
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
        seen_fp, seen_gk, seen_nk = set(), set(), set()   # dry-run sim, never the real ledger
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
            nk = normalized_key(sig)
            if args.dry_run:
                dup = (fp in seen_fp or (gk and gk in seen_gk) or (nk and nk in seen_nk)
                       or ledger_lookup(fp, gk, nk))
                verdict = "would COMMENT/group" if dup else "would FILE"
                print(f"{verdict}: [{kind}] {fp} gk={gk or '-'} nk={nk or '-'} "
                      f"repo={repo_for(sig) or 'UNMAPPED'} | {(iss.get('title') or '')[:70]}")
                seen_fp.add(fp)
                if gk:
                    seen_gk.add(gk)
                if nk:
                    seen_nk.add(nk)
            else:
                print(file_or_update(sig, iss, kind))
                os.rename(os.path.join(qd, name), os.path.join(qd, name + ".filed"))
