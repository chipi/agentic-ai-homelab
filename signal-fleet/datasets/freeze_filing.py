#!/usr/bin/env python3
"""Freeze what a replay of the fleet's filing stage needs. Read-only; runs on the fleet host.

The filing stage (`filing.file_or_update`) decides, for a signal the triager filed or escalated, whether it becomes
a comment on an existing issue, a reopen, a regression, a rollup line, or a new issue. It reads two things besides
the signal: the filed ledger (`results/filed.tsv`, overwritten, so its past states are not kept) and GitHub's issue
states. A replay therefore re-runs every filing decision in time order from an empty ledger, and answers GitHub's
questions from each issue's timeline as of that decision's time. This script freezes the inputs for that:

  decisions.jsonl   one line per file/escalate decision the fleet made in a writing stage (propose/live), oldest
                    first: the ledger row, and the signal as of the decision's time (GlitchTip: rebuilt like
                    build_orrery_items_v2.py, nothing dated after the decision; Grafana: the probe capture, else
                    the alert state history's labels, else the ledger's name only: see `signal_level`), and the
                    title of the issue the decision created, if one exists
  issues.jsonl      every fleet issue in the repos the ledger names: creation, closes (reason, the comment beside
                    them), reopens, duplicate marks, label adds and removes (a mute is a label), and the fleet's
                    own comments, each with its time, and the fingerprints its body or the fleet's comments name
                    (and every comment's time, with whether the stale sweep counts it as the fleet's; no bodies)
  occurrences.jsonl every dispositions.tsv row (time, fingerprint, source, alert name): the stale sweep's last-seen
  grafana_history.jsonl  Grafana's alert state history (time, alert, new state, the instance's labels): which
                    alerts fired when, for the Grafana signals' labels and the stale sweep's "firing now"
  filed_final.tsv   the ledger as it is now, for checking where the replay ends
  freeze.json       counts, the code commit, and what was left out and why

Everything is passed through the fleet's scrubber. Usage (on the fleet host):
  python3 freeze_filing.py OUT_DIR [LEDGER_SNAPSHOT.tsv ...]   # a snapshot's issues are fetched too
"""
import collections
import datetime as dt
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "mvp"))
os.environ.setdefault("SF_OBSERV_DISABLED", "1")
for line in open(os.path.expanduser("~/signal-fleet/fleet-gateway.env")):
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1)
        os.environ.setdefault(k, v.strip().strip('"').strip("'"))
import correlate, scrub, sources  # noqa: E402,E401

UTC = dt.timezone.utc
RESULTS = os.path.expanduser("~/signal-fleet/results")
WRITING_STAGES = {"propose", "live"}
FLEET_LABELS = ["triage-fleet/filed", "triage-fleet/escalated", "triage-fleet/low-signal", "triage-fleet/substrate"]
PRESENT_STATE = ("stats", "numComments", "assignedTo", "statusDetails", "subscriptionDetails",
                 "userReportCount", "matchingEventId", "shareId")
FP_IN_TEXT = re.compile(r"fp:? `([^`]+)`")
FLEET_TEXT = re.compile(r"signal-fleet|_filed by|^Recurred |^Low-signal occurrence|— reopening", re.I | re.M)
DOCKER = ["sudo", "-n", "-u", "_dockerhost", "env", "HOME=/var/_dockerhost",
          "PATH=/usr/local/bin:/usr/bin:/bin", "docker"]
ISSUE_FIELDS = """number title body state stateReason createdAt closedAt labels(first:30){nodes{name}}
      timelineItems(first:150, itemTypes:[CLOSED_EVENT,REOPENED_EVENT,ISSUE_COMMENT,MARKED_AS_DUPLICATE_EVENT,
                                         UNMARKED_AS_DUPLICATE_EVENT,LABELED_EVENT,UNLABELED_EVENT]){
        pageInfo{hasNextPage}
        nodes{__typename
          ... on ClosedEvent{createdAt stateReason duplicateOf{... on Issue{number repository{nameWithOwner}}}}
          ... on ReopenedEvent{createdAt}
          ... on IssueComment{createdAt body}
          ... on MarkedAsDuplicateEvent{createdAt canonical{... on Issue{number repository{nameWithOwner}}}}
          ... on UnmarkedAsDuplicateEvent{createdAt}
          ... on LabeledEvent{createdAt label{name}}
          ... on UnlabeledEvent{createdAt label{name}}}}"""
GQL = ("query($owner:String!,$name:String!,$labels:[String!],$cursor:String){repository(owner:$owner,name:$name){"
       "issues(first:30, after:$cursor, labels:$labels, states:[OPEN,CLOSED]){pageInfo{hasNextPage endCursor}"
       "nodes{" + ISSUE_FIELDS + "}}}}")
ONE = ("query($owner:String!,$name:String!,$n:Int!){repository(owner:$owner,name:$name){issue(number:$n){"
       + ISSUE_FIELDS + "}}}")


def ts(s):
    s = str(s).strip().replace("Z", "+00:00").replace(" ", "T")
    s = re.sub(r"\.(\d+)", lambda m: "." + (m.group(1) + "000000")[:6], s, count=1)
    s = re.sub(r"([+-]\d\d)$", r"\1:00", s)
    t = dt.datetime.fromisoformat(s)
    return t if t.tzinfo else t.replace(tzinfo=UTC)


def iso(t):
    return t.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.") + f"{t.microsecond // 1000:03d}Z"


def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError(r.stderr[:300])
    return r.stdout


def pg(sql):
    out = run(DOCKER + ["exec", "glitchtip-postgres-1", "psql", "-U", "glitchtip", "-d", "glitchtip", "-tAF", "\t",
                        "-c", sql])
    return [x.split("\t") for x in out.splitlines() if x.strip()]


def read_tsv(path):
    with open(path) as f:
        lines = f.read().splitlines()
    head = lines[0].split("\t")
    return head, [dict(zip(head, x.split("\t"))) for x in lines[1:] if x]


# ---- GitHub: every fleet issue, its timeline --------------------------------------------------------------
def fetch_issues(repo):
    owner, name = repo.split("/")
    out, cursor = [], None
    while True:
        cmd = ["gh", "api", "graphql", "-f", f"query={GQL}", "-f", f"owner={owner}", "-f", f"name={name}"]
        for lab in FLEET_LABELS:
            cmd += ["-f", f"labels[]={lab}"]
        if cursor:
            cmd += ["-f", f"cursor={cursor}"]
        page = json.loads(run(cmd))["data"]["repository"]["issues"]
        out += page["nodes"]
        if not page["pageInfo"]["hasNextPage"]:
            return out
        cursor = page["pageInfo"]["endCursor"]


def fetch_one(repo, n):
    """One issue by number, in the same shape as fetch_issues' nodes; None if it cannot be read."""
    owner, name = repo.split("/")
    try:
        out = json.loads(run(["gh", "api", "graphql", "-f", f"query={ONE}", "-f", f"owner={owner}",
                              "-f", f"name={name}", "-F", f"n={n}"]))
    except Exception:  # noqa: BLE001 — a deleted or transferred issue: reported as unfetched
        return None
    return ((out.get("data") or {}).get("repository") or {}).get("issue")


def shape_issue(repo, i):
    tl = i["timelineItems"]["nodes"]
    comments = [c for c in tl if c["__typename"] == "IssueComment"]

    def beside(at):
        t0 = ts(at)
        near = [c for c in comments if abs((ts(c["createdAt"]) - t0).total_seconds()) <= 600
                and not FLEET_TEXT.search(c.get("body") or "")]
        near.sort(key=lambda c: abs((ts(c["createdAt"]) - t0).total_seconds()))
        return (near[0].get("body") or "")[:300] if near else None

    events = []
    for e in tl:
        k = e["__typename"]
        if k == "ClosedEvent":
            d = e.get("duplicateOf") or {}
            events.append({"type": "closed", "at": e["createdAt"], "reason": e.get("stateReason"),
                           "duplicate_of": [d.get("repository", {}).get("nameWithOwner"), d.get("number")] if d else None,
                           "comment": beside(e["createdAt"])})
        elif k == "ReopenedEvent":
            events.append({"type": "reopened", "at": e["createdAt"]})
        elif k == "MarkedAsDuplicateEvent":
            c = e.get("canonical") or {}
            events.append({"type": "marked_duplicate", "at": e["createdAt"],
                           "canonical": [c.get("repository", {}).get("nameWithOwner"), c.get("number")] if c else None})
        elif k == "UnmarkedAsDuplicateEvent":
            events.append({"type": "unmarked_duplicate", "at": e["createdAt"]})
        elif k in ("LabeledEvent", "UnlabeledEvent"):
            events.append({"type": "labeled" if k == "LabeledEvent" else "unlabeled", "at": e["createdAt"],
                           "label": (e.get("label") or {}).get("name")})
        elif k == "IssueComment":
            body = e.get("body") or ""
            # every comment's time, and whether stale.py's rule counts it as the fleet's (stale._is_fleet_comment):
            # the stale sweep nudges only when no one else commented in its window. No body: not needed, not kept.
            events.append({"type": "comment", "at": e["createdAt"],
                           "stale_fleet": "signal-fleet" in body or body.startswith("Recurred")})
            if FLEET_TEXT.search(body):
                events.append({"type": "fleet_comment", "at": e["createdAt"], "text": body[:300]})
    fps = set(FP_IN_TEXT.findall(i.get("body") or ""))
    for c in comments:
        if FLEET_TEXT.search(c.get("body") or ""):
            fps |= set(FP_IN_TEXT.findall(c.get("body") or ""))
    return {"repo": repo, "number": i["number"], "title": i["title"], "created_at": i["createdAt"],
            "state_now": i["state"], "labels_now": [l["name"] for l in i["labels"]["nodes"]],
            "fingerprints": sorted(fps), "events": sorted(events, key=lambda e: e["at"]),
            "timeline_truncated": i["timelineItems"]["pageInfo"]["hasNextPage"]}


# ---- GlitchTip: the signal as of the decision ---------------------------------------------------------------
_issue_cache = {}
MISMATCH = collections.Counter()
EXTRA_LEDGERS = []   # ledger snapshots the replay may start from: paths after OUT_DIR


def glitchtip_issue(short, T):
    """(issue id, issue JSON) of the issue holding this short id at T (a recreated project restarts its ids)."""
    slug, sid = short.rsplit("-", 1)
    # GlitchTip writes the counter in base 32, 0-9A-V: short_id 35 is "13", 170 is "5A"
    rows = pg(f"select i.id from issue_events_issue i join projects_project p on p.id=i.project_id "
              f"where upper(p.slug)='{slug}' and i.short_id={int(sid, 32)} and i.first_seen <= '{T.isoformat()}' "
              f"order by i.first_seen desc limit 1")
    if not rows:
        return None, None
    iid = rows[0][0]
    if iid not in _issue_cache:
        j = correlate._gt(f"/issues/{iid}/")
        _issue_cache[iid] = j if isinstance(j, dict) and j.get("shortId") else None
    if _issue_cache[iid] and _issue_cache[iid]["shortId"].upper() != short.upper():
        MISMATCH[short] += 1  # never use another issue's signal
        return None, None
    return iid, _issue_cache[iid]


def event_at(iid, T, first=False):
    r = pg(f"select e.created, coalesce(r.version,''), coalesce(r.created::text,'') from issue_events_issueevent e "
           f"left join releases_release r on r.id=e.release_id where e.issue_id={int(iid)} and e.created <= "
           f"'{T.isoformat()}' order by e.created {'asc' if first else 'desc'} limit 1")
    if not r:
        return None
    created, ver, rcreated = r[0]
    return ts(created), ver or None, ts(rcreated) if rcreated else None


def release(ver, created, T):
    if not ver or created is None or created > T:
        return None
    return {"version": ver, "shortVersion": ver, "dateCreated": iso(created), "dateReleased": None}


# ---- Grafana: the alert's labels as of the decision ---------------------------------------------------------
# The ledger keeps an alert's name, not its labels, and filing routes a Grafana signal by its `instance` label and
# keys it with that label too (filing.repo_for, filing.normalized_key). Two places still have the labels: the probe
# capture (on from 2026-10-29: the exact signal the fleet acted on) and Grafana's alert state history, whose entries
# carry each alert instance's label set ("Name {k=v, k=v} - values").
CAPTURE_DIR = os.path.join(RESULTS, "probes")
HISTORY_LABELS = re.compile(r"\{([^}]*)\}")
GRAFANA_CHECK = collections.Counter()   # history vs capture, where both exist
_captures = None
_history = None


def captures():
    """fingerprint -> [(capture time, signal)] from the probe capture."""
    global _captures
    if _captures is None:
        _captures = collections.defaultdict(list)
        for name in sorted(os.listdir(CAPTURE_DIR)) if os.path.isdir(CAPTURE_DIR) else []:
            if name.endswith(".json"):
                try:
                    item = json.load(open(os.path.join(CAPTURE_DIR, name)))
                except (OSError, ValueError):
                    continue
                sig = item.get("signal") or {}
                _captures[sig.get("fingerprint")].append((ts(item["frozen_at"]), sig))
    return _captures


def history(t_from, t_to):
    """alertname -> [(time, new state, labels)], oldest first, from Grafana's alert state history."""
    global _history
    if _history is None:
        import config  # noqa: PLC0415 — the fleet's own Grafana credentials
        headers = {"Authorization": f"Bearer {config.GRAFANA_TOKEN}"} if config.GRAFANA_TOKEN else None
        user, pw = (None, None) if config.GRAFANA_TOKEN else (config.GRAFANA_USER, config.GRAFANA_PW)
        seen, _history = set(), collections.defaultdict(list)
        day = dt.timedelta(days=1)
        t = t_from
        while t < t_to:
            url = (f"{config.GRAFANA_URL}/api/annotations?type=alert&limit=5000"
                   f"&from={int(t.timestamp() * 1000)}&to={int((t + day).timestamp() * 1000)}")
            page = sources.get_json(url, user, pw, headers=headers, timeout=60)
            if len(page) >= 5000:
                raise RuntimeError(f"state history page full at {t}: narrow the window")
            for a in page:
                if a["id"] in seen:
                    continue
                seen.add(a["id"])
                m = HISTORY_LABELS.search(a.get("text") or "")
                labels = dict(kv.split("=", 1) for kv in m.group(1).split(", ") if "=" in kv) if m else {}
                _history[a.get("alertName")].append((dt.datetime.fromtimestamp(a["time"] / 1000, UTC),
                                                     a.get("newState") or "", labels))
            t += day
        for v in _history.values():
            v.sort(key=lambda x: x[0])
    return _history


def labels_from_history(alertname, T, starts):
    """The label set of the instance of `alertname` firing at T; when several fire, the one that went Alerting at
    the occurrence's start. (labels, how) or (None, why not)."""
    state = {}
    for at, new, labels in (_history or {}).get(alertname, []):
        if at > T:
            break
        state[tuple(sorted(labels.items()))] = (at, new)
    firing = [k for k, (at, new) in state.items() if new.startswith("Alerting")]
    if len(firing) == 1:
        return dict(firing[0]), "firing"
    if starts:
        near = [k for k in firing if abs((state[k][0] - starts).total_seconds()) <= 60]
        if len(near) == 1:
            return dict(near[0]), "firing, by start"
    return None, f"{len(firing)} instances firing"


def grafana_signal(row, T):
    fp = row["fingerprint"]
    occ = row.get("occurrence_id") or ""
    starts = ts(occ.split("@", 1)[1]) if "@" in occ else None
    base = {"source": "grafana", "fingerprint": fp, "occurrence_id": occ or None, "alertname": row["alertname"],
            "summary": row["alertname"], "startsAt": iso(starts) if starts else None}
    from_hist, how = labels_from_history(row["alertname"], T, starts)
    if from_hist is not None and ":oom:" in fp:
        from_hist = dict(from_hist, container=fp.split(":oom:", 1)[1])
    near = [s for at, s in captures().get(fp, []) if abs((at - T).total_seconds()) <= 120]
    if near:
        sig = dict(near[-1])
        sig.pop("raw", None)
        if from_hist is None:
            GRAFANA_CHECK[f"capture only (history: {how})"] += 1
        else:
            GRAFANA_CHECK["history agrees with capture" if from_hist.get("instance") == (sig.get("labels") or {}).get("instance")
                          else "history DISAGREES with capture (instance)"] += 1
        return sig, "captured"
    if from_hist is not None:
        return dict(base, labels=from_hist), "state-history"
    GRAFANA_CHECK[f"no labels ({how})"] += 1
    return dict(base, labels={}), "ledger-only"


def signal_for(row, T):
    fp, src = row["fingerprint"], row["source"]
    if src == "grafana":
        return grafana_signal(row, T)
    if src != "glitchtip":
        return {"source": src, "fingerprint": fp, "alertname": row["alertname"], "labels": {},
                "summary": row["alertname"]}, "ledger-only"
    short = fp.split(":", 1)[1]
    iid, issue = glitchtip_issue(short, T)
    if not issue:
        return {"source": "glitchtip", "fingerprint": fp, "alertname": row["alertname"],
                "labels": {"project": short.rsplit("-", 1)[0].lower()}, "summary": row["alertname"],
                "issue_id": None}, "ledger-only"
    raw = {k: v for k, v in issue.items() if k not in PRESENT_STATE}
    raw.update(count=row.get("signal_count") or issue.get("count"), status="unresolved", userCount=None)
    latest, firstev = event_at(iid, T), event_at(iid, T, first=True)
    if latest:
        raw["lastSeen"] = iso(latest[0])
        raw["lastRelease"] = release(latest[1], latest[2], T)
        raw["firstRelease"] = release(firstev[1], firstev[2], T) if firstev else None
    else:
        for k in ("lastRelease", "firstRelease"):
            d = (raw.get(k) or {}).get("dateCreated")
            if d and ts(d) > T:
                raw[k] = None
    sig = sources.to_error_signal(raw)
    sig["occurrence_id"] = row.get("occurrence_id")
    return sig, "rebuilt-at-decision" if latest else "issue-only"


KEY_CHANGES = collections.Counter()


def keys_of(signal, title):
    """The three keys filing.file_or_update derives for a signal (filing.py: group_key_for, normalized_key,
    alert_key), with the repo it routes to."""
    import filing  # noqa: PLC0415  (the fleet's own, from ../mvp)
    repo = filing.repo_for(signal) or ""
    return {"repo": repo,
            "group_key": filing.group_key_for(signal.get("alertname", ""), title or "",
                                              (signal.get("labels") or {}).get("project", "")),
            "norm_key": filing.normalized_key(signal),
            "alert_key": filing.alert_key(repo, signal.get("source", ""), signal.get("alertname", "")) if repo else ""}


def main(out_dir):
    os.makedirs(out_dir, exist_ok=True)
    head, disp = read_tsv(os.path.join(RESULTS, "dispositions.tsv"))
    _, filed = read_tsv(os.path.join(RESULTS, "filed.tsv"))
    repos = sorted({r["repo"] for r in filed if r.get("repo")})
    issues = []
    for repo in repos:
        issues += [dict(shape_issue(repo, i), fleet_labelled=True) for i in fetch_issues(repo)]
    # Filing also reads issues without a fleet label: a duplicate's canonical (often the operator's own issue,
    # and file_or_update remaps the ledger row to it), and any issue a ledger row names, today's or a snapshot's
    # the replay starts from (extra ledgers: the paths after OUT_DIR). Their timelines are needed too.
    have = {(i["repo"], i["number"]) for i in issues}
    wanted = set()
    for i in issues:
        for e in i["events"]:
            for ref in (e.get("duplicate_of"), e.get("canonical")):
                if ref and ref[0] and ref[1]:
                    wanted.add((ref[0], int(ref[1])))
    ledgers = [filed] + [read_tsv(p)[1] for p in EXTRA_LEDGERS]
    for rows in ledgers:
        for r in rows:
            if r.get("repo") and str(r.get("issue", "")).isdigit():
                wanted.add((r["repo"], int(r["issue"])))
    missing = sorted(wanted - have)
    for repo, n in missing:
        node = fetch_one(repo, n)
        if node:
            issues.append(dict(shape_issue(repo, node), fleet_labelled=False))
    unfetched = [f"{r}#{n}" for r, n in missing if (r, n) not in {(i["repo"], i["number"]) for i in issues}]
    created_by = {}   # fingerprint -> [(created_at, repo, number, title)]
    for i in issues:
        for fp in i["fingerprints"]:
            created_by.setdefault(fp, []).append((i["created_at"], i["repo"], i["number"], i["title"]))
    skipped = collections.Counter()
    decisions = []
    graf = [ts(r["ts"]) for r in disp if r.get("source") == "grafana" and r.get("disposition") in ("file", "escalate")]
    if graf:
        # from a week before the first decision: an alert that went Alerting before it is still firing at it
        history(min(graf) - dt.timedelta(days=7), max(graf) + dt.timedelta(days=1))
    for r in disp:
        if r.get("disposition") not in ("file", "escalate"):
            continue
        if r.get("stage") not in WRITING_STAGES:
            skipped[f"stage {r.get('stage') or '(none)'}"] += 1
            continue
        T = ts(r["ts"])
        sig, level = signal_for(r, T)
        made = [c for c in created_by.get(r["fingerprint"], [])
                if T - dt.timedelta(minutes=1) <= ts(c[0]) <= T + dt.timedelta(minutes=15)]
        decisions.append({"ts": r["ts"], "fingerprint": r["fingerprint"], "source": r["source"],
                          "disposition": r["disposition"], "work_type": r.get("work_type", ""),
                          "stage": r.get("stage"), "cycle_id": r.get("cycle_id"), "reason": r.get("reason", "")[:300],
                          "signal": sig, "signal_level": level,
                          # the keys filing derives, from the signal BEFORE scrubbing: the ledger holds keys of
                          # real messages, and scrubbing (IPs, hosts, the repo owner) can change a key
                          "keys_unscrubbed": keys_of(sig, made[0][3] if made else ""),
                          "issue_created": {"repo": made[0][1], "number": made[0][2], "title": made[0][3]} if made else None})
    decisions.sort(key=lambda d: d["ts"])
    for d in decisions:
        d["keys_change_under_scrub"] = sorted(k for k, v in keys_of(scrub.scrub(d["signal"]),
                                                                   (d["issue_created"] or {}).get("title", "")).items()
                                              if v != d["keys_unscrubbed"].get(k))
        KEY_CHANGES.update(d["keys_change_under_scrub"])
    # the stale sweep's other inputs: every ledger row is an occurrence (stale._occurrences), and which Grafana
    # alerts fire when it runs (from the state history)
    occurrences = [{"ts": r["ts"], "fingerprint": r["fingerprint"], "source": r["source"], "alertname": r["alertname"]}
                   for r in disp]
    grafana_history = [{"at": iso(at), "alertname": name, "state": new, "labels": labels}
                       for name, rows in sorted((_history or {}).items()) for at, new, labels in rows]
    for name, rows in (("decisions.jsonl", decisions), ("issues.jsonl", issues), ("occurrences.jsonl", occurrences),
                       ("grafana_history.jsonl", grafana_history)):
        p = os.path.join(out_dir, name)
        with open(p, "w") as f:
            for x in rows:
                f.write(json.dumps(scrub.scrub(x), ensure_ascii=False, sort_keys=True) + "\n")
        os.chmod(p, 0o600)
    cols = list(filed[0].keys()) if filed else []
    with open(os.path.join(out_dir, "filed_final.tsv"), "w") as f:
        f.write(scrub.scrub("\n".join(["\t".join(cols)] + ["\t".join(r.get(c, "") for c in cols) for r in filed])) + "\n")
    os.chmod(os.path.join(out_dir, "filed_final.tsv"), 0o600)
    checkout = os.environ.get("SF_CHECKOUT", os.path.expanduser("~/agentic-ai-homelab"))
    commit = run(["git", "-C", checkout, "rev-parse", "--short", "HEAD"]).strip()
    summary = {"frozen_at": dt.datetime.now(UTC).isoformat(), "code_commit": commit, "repos": repos,
               "decisions": len(decisions), "issues": len(issues),
               "decisions_by_signal_level": dict(collections.Counter(d["signal_level"] for d in decisions)),
               "decisions_by_repo_of_created_issue": dict(collections.Counter(
                   (d["issue_created"] or {}).get("repo", "(none created)") for d in decisions)),
               "issues_by_repo": dict(collections.Counter(i["repo"] for i in issues)),
               "issues_with_truncated_timeline": sum(i["timeline_truncated"] for i in issues),
               "skipped": dict(skipped), "shortid_mismatches": dict(MISMATCH),
               "issues_not_fleet_labelled": sum(1 for i in issues if not i.get("fleet_labelled")),
               "issues_unfetched": unfetched, "extra_ledgers": EXTRA_LEDGERS,
               "decisions_whose_keys_change_under_scrub": sum(1 for d in decisions if d["keys_change_under_scrub"]),
               "key_changes_under_scrub": dict(KEY_CHANGES),
               "grafana_labels_history_vs_capture": dict(GRAFANA_CHECK),
               "grafana_decisions_by_signal_level": dict(collections.Counter(d["signal_level"] for d in decisions if d["source"] == "grafana")),
               "secret_hits_after_scrub": sum(len(scrub.scan(scrub.scrub(x))) for x in decisions + issues)}
    json.dump(summary, open(os.path.join(out_dir, "freeze.json"), "w"), indent=1, sort_keys=True)
    print(json.dumps(summary, indent=1, sort_keys=True))


if __name__ == "__main__":
    EXTRA_LEDGERS.extend(sys.argv[2:])
    main(sys.argv[1])
