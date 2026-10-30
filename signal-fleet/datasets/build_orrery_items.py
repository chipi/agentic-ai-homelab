#!/usr/bin/env python3
"""Build the triage fleet's Orrery decisions as replayable evh items. Read-only; runs on the fleet host.

One item per Orrery non-recurrence decision in ~/signal-fleet/results/dispositions.tsv, in
freeze.py's fixture shape (id, source, frozen_at, signal, probes, freeze_dispositions,
ground_truth) plus fleet_decision, outcome and provenance. For eval-harness's "datasets from
production" (RFC-019); first built 2026-10-29.

Probe answers, per probe key (provenance.probe_source):
  verbatim     the exact text the model read, from the gateway's Langfuse generations
  rebuilt      re-fetched with the window anchored at the decision time
  unavailable  the store holds nothing that old: <UNAVAILABLE: ...> (not <TABLE-MISS>)
  static       the constant the live probe returns (no store involved)
Store windows are measured at run time (retention rolls forward daily).

Outcome per item: every fleet issue in chipi/orrery whose body names the decision's fingerprint
(`fp: ...`), with its relation to the decision and each close/reopen event paired with the
comment beside it (the operator's close comment carries the verdict; GitHub's close reason and
actor do not, since the fleet writes with the operator's token). Plus later decisions on the
same fingerprint. Writes nothing outside OUT_DIR; the fleet, its ledgers and GitHub are only read.

Usage (on the fleet host):  python3 build_orrery_items.py OUT_DIR
"""
import collections, csv, datetime as dt, json, os, re, subprocess, sys, urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
MVP = os.path.join(os.path.dirname(HERE), "mvp")
os.environ.setdefault("SF_OBSERV_DISABLED", "1")
for line in open(os.path.expanduser("~/signal-fleet/fleet-gateway.env")):
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1)
        os.environ.setdefault(k, v.strip().strip('"').strip("'"))
sys.path.insert(0, MVP)
import config, correlate, probes, scrub, sources  # noqa: E402

UTC = dt.timezone.utc
REPO = "chipi/orrery"
DOCKER = ["sudo", "-n", "-u", "_dockerhost", "env", "HOME=/var/_dockerhost",
          "PATH=/usr/local/bin:/usr/bin:/bin", "docker"]
BUILT_AT = dt.datetime.now(UTC).isoformat()
TEST_TITLES = re.compile(r"tls-node migration (probe|FINAL verify)|post-closure check", re.I)
FLEET_TEXT = re.compile(r"signal-fleet|_filed by|^Recurred |^Low-signal occurrence", re.I | re.M)
FP_IN_TEXT = re.compile(r"fp:? `([^`]+)`")


def ts(s):
    s = s.strip().replace("Z", "+00:00").replace(" ", "T")
    # Python 3.9 (the mini's) parses only 3- or 6-digit fractions; VictoriaLogs gives 9
    s = re.sub(r"\.(\d+)", lambda m: "." + (m.group(1) + "000000")[:6], s, count=1)
    t = dt.datetime.fromisoformat(s)
    return t if t.tzinfo else t.replace(tzinfo=UTC)


def iso(t):
    return t.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError(r.stderr[:300])
    return r.stdout


def pg(sql):
    out = run(DOCKER + ["exec", "glitchtip-postgres-1", "psql", "-U", "glitchtip", "-d", "glitchtip",
                        "-tAF", "\t", "-c", sql])
    return [l.split("\t") for l in out.splitlines() if l.strip()]


def ch(sql):
    out = run(DOCKER + ["exec", "langfuse-clickhouse-1", "clickhouse-client", "-q", sql])
    return [json.loads(l) for l in out.splitlines() if l.strip()]


# ---- store windows, measured now ---------------------------------------------------------
def _vl_oldest(url):
    out = correlate.post_form_text(f"{url}/select/logsql/query",
                                   {"query": "_time:400d | stats min(_time) oldest"}, timeout=60)
    return ts(json.loads(out.splitlines()[0])["oldest"])


def _vm_oldest():
    url = f"{config.VM_URL}/api/v1/query?" + urllib.parse.urlencode(
        {"query": "min(min_over_time(timestamp(up)[400d:1d]))"})
    return dt.datetime.fromtimestamp(float(correlate.get_json(url, timeout=120)["data"]["result"][0]["value"][1]), UTC)


VL_OLDEST = _vl_oldest(config.VL_URL)
VT_OLDEST = _vl_oldest(config.VT_URL)
VM_OLDEST = _vm_oldest()
LF_OLDEST = ts(ch("select min(start_time) t from observations where name='triage-turn-1' format JSONEachRow")[0]["t"])
STORES = {"victorialogs": iso(VL_OLDEST), "victoriatraces": iso(VT_OLDEST),
          "victoriametrics": iso(VM_OLDEST), "langfuse_conversations": iso(LF_OLDEST)}


def unavailable(store, oldest, T):
    return f"<UNAVAILABLE: {store} holds nothing before {oldest.date()} (decision at {iso(T)})>"


# ---- GitHub: every fleet issue in the repo, with closes/reopens and comments --------------
GQL = """query($cursor:String){repository(owner:"chipi",name:"orrery"){
  issues(first:40, after:$cursor, labels:["triage-fleet/filed","triage-fleet/escalated"], states:[OPEN,CLOSED]){
    pageInfo{hasNextPage endCursor}
    nodes{number title body state stateReason createdAt closedAt labels(first:30){nodes{name}}
      timelineItems(first:100, itemTypes:[CLOSED_EVENT,REOPENED_EVENT,ISSUE_COMMENT,MARKED_AS_DUPLICATE_EVENT]){nodes{
        __typename
        ... on ClosedEvent{createdAt stateReason actor{login}}
        ... on ReopenedEvent{createdAt actor{login}}
        ... on IssueComment{createdAt author{login} body}
        ... on MarkedAsDuplicateEvent{createdAt canonical{... on Issue{number}}}}}}}}}"""


def fetch_issues():
    issues, cursor = [], None
    while True:
        cmd = ["gh", "api", "graphql", "-f", f"query={GQL}"] + (["-f", f"cursor={cursor}"] if cursor else [])
        page = json.loads(run(cmd))["data"]["repository"]["issues"]
        issues += page["nodes"]
        if not page["pageInfo"]["hasNextPage"]:
            return issues
        cursor = page["pageInfo"]["endCursor"]


def shape_issue(i):
    tl = i["timelineItems"]["nodes"]
    comments = [{"at": c["createdAt"], "author": (c.get("author") or {}).get("login"),
                 "text": (c.get("body") or "")[:300], "fleet_comment": bool(FLEET_TEXT.search(c.get("body") or ""))}
                for c in tl if c["__typename"] == "IssueComment"]

    def beside(at):
        # the comment closest to the event within 10 min, preferring one not written by the fleet
        t0 = ts(at)
        near = [c for c in comments if abs((ts(c["at"]) - t0).total_seconds()) <= 600]
        near.sort(key=lambda c: (c["fleet_comment"], abs((ts(c["at"]) - t0).total_seconds())))
        return near[0] if near else None

    events = []
    for e in tl:
        if e["__typename"] in ("ClosedEvent", "ReopenedEvent"):
            events.append({"type": "closed" if e["__typename"] == "ClosedEvent" else "reopened",
                           "at": e["createdAt"], "state_reason": e.get("stateReason"),
                           "actor": (e.get("actor") or {}).get("login"), "comment": beside(e["createdAt"])})
    dup = [e["canonical"]["number"] for e in tl if e["__typename"] == "MarkedAsDuplicateEvent" and e.get("canonical")]
    fps = set(FP_IN_TEXT.findall(i.get("body") or ""))
    for c in tl:
        if c["__typename"] == "IssueComment" and FLEET_TEXT.search(c.get("body") or ""):
            fps |= set(FP_IN_TEXT.findall(c.get("body") or ""))
    return {"number": i["number"], "title": i["title"], "state": i["state"], "state_reason": i["stateReason"],
            "created_at": i["createdAt"], "closed_at": i["closedAt"],
            "labels": [l["name"] for l in i["labels"]["nodes"]], "duplicate_of": dup[-1] if dup else None,
            "close_reopen_events": events, "reopen_count": sum(1 for e in events if e["type"] == "reopened"),
            "comment_count": len(comments), "_fps": fps}


def linked_issues(fp, alertname, disposition, T, issues):
    out = []
    for iss in issues:
        by_fp = fp in iss["_fps"]
        by_title = bool(alertname) and alertname[:80] in iss["title"]
        if not (by_fp or by_title):
            continue
        created = ts(iss["created_at"])
        closed = ts(iss["closed_at"]) if iss["closed_at"] else None
        if disposition in ("file", "escalate") and T - dt.timedelta(minutes=1) <= created <= T + dt.timedelta(minutes=15):
            rel = "created_by_this_decision"
        elif created < T and (closed is None or closed > T or iss["reopen_count"]):
            rel = "existing_at_decision"
        elif created < T:
            rel = "closed_before_decision"
        else:
            rel = "created_later"
        out.append(dict({k: v for k, v in iss.items() if k != "_fps"}, relation=rel,
                        matched_by="fingerprint" if by_fp else "title"))
    order = {"created_by_this_decision": 0, "existing_at_decision": 1, "closed_before_decision": 2, "created_later": 3}
    return sorted(out, key=lambda x: (order[x["relation"]], x["created_at"]))


# ---- Langfuse: the model's own conversation ------------------------------------------------
def langfuse_conversation(alertname, T):
    lo = (T - dt.timedelta(minutes=20)).strftime("%Y-%m-%d %H:%M:%S")
    hi = (T + dt.timedelta(minutes=3)).strftime("%Y-%m-%d %H:%M:%S")
    best = None
    for f in ch(f"select trace_id, start_time, input from observations where name='triage-turn-1' "
                f"and start_time between '{lo}' and '{hi}' format JSONEachRow"):
        try:
            msgs = json.loads(f["input"])["messages"]
            sig = json.loads(msgs[1]["content"].split("SIGNAL:\n", 1)[1].split("\n\n")[0])
        except Exception:  # noqa: BLE001
            continue
        if sig.get("alertname") == alertname:
            t = ts(f["start_time"])
            if t <= T + dt.timedelta(minutes=3) and (best is None or t > best[1]):
                best = (f["trace_id"], t, sig)
    if not best:
        return None
    turns = ch(f"select name, input from observations where trace_id='{best[0]}' "
               f"and name like 'triage-turn-%' format JSONEachRow")
    msgs = json.loads(max(turns, key=lambda x: int(x["name"].rsplit("-", 1)[1]))["input"])["messages"]
    calls = []
    for a, u in zip(msgs[2::2], msgs[3::2]):
        m = re.match(r"PROBE (\S+) result:\n(.*)\Z", u.get("content") or "", re.S)
        if a.get("role") != "assistant" or not m:
            continue
        try:
            req = json.loads(a["content"])
        except Exception:  # noqa: BLE001
            req = {}
        calls.append((m.group(1), req.get("probe_args") or {}, m.group(2)))
    return {"trace_id": best[0], "signal_view": best[2], "calls": calls}


# ---- anchored probe rebuild --------------------------------------------------------------
def event_at(issue_id, T):
    r = pg(f"select replace(event_id::text,'-',''), timestamp from issue_events_issueevent "
           f"where issue_id={int(issue_id)} and timestamp <= '{iso(T)}' order by timestamp desc limit 1")
    if not r:
        return None, None
    return correlate._gt(f"/issues/{issue_id}/events/{r[0][0]}/"), r[0][1]


def vl_window(query, T, hours):
    start = T - dt.timedelta(hours=hours)
    if start < VL_OLDEST:
        return unavailable("VictoriaLogs", VL_OLDEST, T), "unavailable"
    return correlate.vl_query(query.format(win=f"[{iso(start)}, {iso(T)})")), "rebuilt"


def vm_at(promql, T):
    if T - dt.timedelta(minutes=5) < VM_OLDEST:
        return unavailable("VictoriaMetrics", VM_OLDEST, T), "unavailable"
    url = f"{config.VM_URL}/api/v1/query?" + urllib.parse.urlencode({"query": promql, "time": T.timestamp()})
    return correlate.get_json(url, timeout=12), "rebuilt"


def rebuild(name, args, sig, T, ev, gt_note):
    svc = args.get("service") or sig.get("labels", {}).get("project", "")
    if name in ("event_detail", "occurrence_history") and sig.get("issue_id") is None and gt_note:
        return f"<UNAVAILABLE: {gt_note}>", "unavailable"
    if name == "event_detail":
        if not sig.get("issue_id"):
            return "<not applicable: not a GlitchTip issue>", "static"
        if ev is None:
            return f"<UNAVAILABLE: no GlitchTip event at or before {iso(T)}>", "unavailable"
        return correlate._summarize_event(ev), "rebuilt"
    if name == "occurrence_history":
        r = sig.get("raw") or {}
        return {k: r.get(k) for k in ("count", "userCount", "firstSeen", "lastSeen", "level", "status", "culprit")}, "rebuilt"
    if name == "service_logs":
        if not svc:
            return "<no service to query>", "static"
        w = args.get("window", "6h")
        h = int(w[:-1]) * (24 if w.endswith("d") else 1) if re.fullmatch(r"\d+[hd]", w) else 6
        return vl_window(f"app:{svc} AND _time:{{win}} | sort by (_time) desc | limit 15", T, h)
    if name == "metric":
        q = {"5xx": f'sum(rate(http_requests_total{{job=~".*{svc}.*",status=~"5.."}}[5m]))',
             "up": f'up{{job=~".*{svc}.*"}}'}.get(args.get("kind", "5xx"), f'up{{job=~".*{svc}.*"}}')
        return vm_at(q, T)
    if name == "trace":
        tid = args.get("trace_id")
        if not tid:
            return "<no trace_id provided>", "static"
        if T < VT_OLDEST:
            return unavailable("VictoriaTraces", VT_OLDEST, T), "unavailable"
        rr = correlate.vt_trace(tid)
        return (rr if (isinstance(rr, dict) and rr.get("data")) else f"<trace {tid[:8]} not found>"), "rebuilt"
    if name == "source_state":
        return vl_window("job:orrery-data-refresh AND _time:{win} | sort by (_time) desc | limit 10", T, 24)
    return f"<unknown probe: {name}>", "static"


def safe(*a):
    try:
        return rebuild(*a)
    except Exception as e:  # noqa: BLE001 — a probe never raises, live or rebuilt
        return f"<error: {e}>", "rebuilt"


def decision_kind(model, reason):
    if (reason or "").startswith("triager call failed"):
        return "triager_failure"  # the model never decided (e.g. the 2026-08 401 outage)
    if (model or "").startswith("none"):
        return "gate"  # a deterministic gate decided, no LLM
    return "model"


# ---- build -------------------------------------------------------------------------------
def main(out_dir):
    os.makedirs(out_dir, exist_ok=True)
    rows = list(csv.reader(open(os.path.expanduser("~/signal-fleet/results/dispositions.tsv")), delimiter="\t"))
    H = {k: i for i, k in enumerate(rows[0])}
    alld = rows[1:]
    col = lambda r, k: r[H[k]] if H[k] < len(r) else ""  # noqa: E731
    orr = [r for r in alld if "orrery" in "\t".join(r[1:5]).lower() and col(r, "disposition") != "recurrence"]
    issues = [shape_issue(i) for i in fetch_issues()]
    by_short = {}
    for (iid,) in pg("select i.id from issue_events_issue i join projects_project p on p.id=i.project_id "
                     "where p.slug like 'orrery%'"):
        j = correlate._gt(f"/issues/{iid}/")
        if isinstance(j, dict) and j.get("shortId"):
            by_short[j["shortId"]] = j
    labels = {}
    refdir = os.path.join(os.path.dirname(HERE), "reference")
    for fn in os.listdir(refdir):
        if fn.endswith(".json"):
            d = json.load(open(os.path.join(refdir, fn)))
            g, fp = d.get("ground_truth") or {}, (d.get("signal") or {}).get("fingerprint")
            if fp and g.get("disposition"):
                labels[fp] = (g, fn, d.get("frozen_at"))

    items, stats = [], collections.Counter()
    for r in orr:
        T, fp, disp = ts(col(r, "ts")), col(r, "fingerprint"), col(r, "disposition")
        short = fp.split(":", 1)[1] if fp.startswith("glitchtip:") else ""
        issue, gt_note = by_short.get(short), ""
        if issue and ts(issue.get("firstSeen") or "2100-01-01T00:00:00Z") > T + dt.timedelta(minutes=5):
            gt_note = (f"GlitchTip short id {short} now belongs to a newer issue (first seen "
                       f"{issue.get('firstSeen')}); the original issue is gone")
            issue = None
        elif not issue and short:
            gt_note = f"GlitchTip issue {short} no longer exists (project deleted or recreated)"
        ev = None
        if issue:
            raw = dict(issue, count=col(r, "signal_count") or issue.get("count"), status="unresolved", userCount=None)
            ev, ev_ts = event_at(issue["id"], T)
            if ev_ts:
                raw["lastSeen"] = ev_ts.replace(" ", "T")
            sig = sources.to_error_signal(raw)
        else:
            sig = {"fingerprint": fp, "source": col(r, "source"), "alertname": col(r, "alertname"),
                   "labels": {"project": short.rsplit("-", 1)[0].lower() if short else ""},
                   "summary": col(r, "alertname"), "issue_id": None}
        sig["occurrence_id"] = col(r, "occurrence_id")
        lf = langfuse_conversation(col(r, "alertname"), T) if T >= LF_OLDEST else None
        table, meta = {}, {}
        if lf:
            for k in ("source", "alertname", "labels", "summary"):
                sig[k] = lf["signal_view"].get(k)
            for name, args, text in lf["calls"]:
                k = probes.probe_key(name, args)
                table[k], meta[k] = text, "verbatim"
        wanted = [(n, {}) for n in probes.PROBES]
        tid = correlate._summarize_event(ev).get("trace_id") if isinstance(ev, dict) else None
        if tid:
            wanted.append(("trace", {"trace_id": tid}))
        for name, args in wanted:
            k = probes.probe_key(name, args)
            if k not in table:
                table[k], meta[k] = safe(name, args, sig, T, ev, gt_note)
        if lf:
            level = "exact"
        elif T >= VT_OLDEST + dt.timedelta(hours=24):
            level = "full-rebuild"
        elif T >= VL_OLDEST + dt.timedelta(hours=24):
            level = "no-traces"
        elif T >= VM_OLDEST:
            level = "no-logs"
        else:
            level = "glitchtip-only" if issue else "ledger-only"
        stats[level] += 1
        g = {"disposition": None, "work_type": None, "notes": ""}
        if fp in labels:
            lg, fn, fat = labels[fp]
            g = dict(lg, notes=(lg.get("notes") or "") +
                     f" [hand label carried from reference/{fn}, frozen {str(fat)[:10]}, same fingerprint]")
        kind = decision_kind(col(r, "model"), col(r, "reason"))
        items.append({
            "id": f"orrery-{short or fp}-{iso(T)}",
            "source": col(r, "source"),
            "frozen_at": BUILT_AT,
            "signal": sig,
            "probes": table,
            "freeze_dispositions": [],
            "ground_truth": g,
            "is_test_signal": bool(TEST_TITLES.search(col(r, "alertname"))),
            "decision_kind": kind,
            "fleet_decision": {k: col(r, k) for k in (
                "ts", "occurrence_id", "fingerprint", "disposition", "work_type", "model", "prompt_ver",
                "prompt_sha", "gates", "n_probes", "certainty", "reason", "signal_count", "cycle_id", "stage")},
            "outcome": {
                "linked_issues": linked_issues(fp, col(r, "alertname"), disp, T, issues),
                "later_decisions_same_fingerprint": [
                    {"ts": col(x, "ts"), "disposition": col(x, "disposition")} for x in alld
                    if col(x, "fingerprint") == fp and col(x, "ts") > col(r, "ts") and col(x, "disposition") != "recurrence"],
            },
            "provenance": {
                "evidence_level": level, "probe_source": meta,
                "langfuse_trace_id": lf["trace_id"] if lf else None,
                "glitchtip_issue_available": bool(issue), "glitchtip_note": gt_note or None,
                "decision_time": iso(T), "store_oldest": STORES,
                "verbatim_answers_are_trimmed_text": True,
                "github_actor_note": "every close/reopen/comment shows the operator's login: the fleet writes with the operator's token; read the comment text",
                "notes": "freeze_dispositions empty: no model passes were run for this build. "
                         "Rebuilt occurrence_history uses the ledger's signal_count; userCount unknown."},
        })

    clean = [scrub.scrub(i) for i in items]
    hits = sum(len(scrub.scan(i)) for i in clean)
    path = os.path.join(out_dir, "orrery-triage-items.jsonl")
    with open(path, "w") as f:
        for i in clean:
            f.write(json.dumps(i, ensure_ascii=False, sort_keys=True) + "\n")
    os.chmod(path, 0o600)
    print("store windows:", STORES)
    print("items:", len(clean), "| by evidence level:", dict(stats), "| secret hits after scrub:", hits)
    print("decision kinds:", dict(collections.Counter(i["decision_kind"] for i in items)),
          "| test signals:", sum(1 for i in items if i["is_test_signal"]))
    print("probe sources:", dict(collections.Counter(v for i in items for v in i["provenance"]["probe_source"].values())))
    print("items with a linked issue:", sum(1 for i in items if i["outcome"]["linked_issues"]),
          "| file/escalate decisions with an issue created by them:",
          sum(1 for i in items if any(x["relation"] == "created_by_this_decision" for x in i["outcome"]["linked_issues"])),
          "of", sum(1 for i in items if i["fleet_decision"]["disposition"] in ("file", "escalate")))
    print("hand labels carried:", sum(1 for i in items if i["ground_truth"].get("disposition")))
    print("fleet issues read from GitHub:", len(issues))
    print("path:", path, "| bytes:", os.path.getsize(path))


if __name__ == "__main__":
    main(sys.argv[1])
