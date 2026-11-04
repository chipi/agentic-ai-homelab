#!/usr/bin/env python3
"""v2 of the Orrery triage items: v1's decisions with the hindsight taken out. Read-only; runs on the fleet host.

v1 (build_orrery_items.py, 2026-10-29) rebuilt each decision's evidence from the stores as they were
when it ran, and some of what it wrote describes that day instead of the decision's (eval-harness
replay, 2026-11-04):

  - an answer it could not recover named the outcome: "GlitchTip issue X no longer exists", "short id
    X now belongs to a newer issue", "<store> holds nothing before <date>". Each is now
    `<UNAVAILABLE: not captured>`; why is kept in provenance only, where the model never reads it;
  - a rebuilt trace lookup that failed today (`<error: HTTP Error 404 ...>`) cannot tell a trace that
    never existed from one the store has since dropped: also not captured;
  - lastSeen came from the GlitchTip event's own `timestamp`, which the browser sets (2023-11-14 from a
    fixed client clock, midnight from another). It is now the event's server-side `created`, latest at
    or before the decision; event_detail and occurrence_history rebuilt from that same event;
  - first/lastRelease were the issue's at build time (on ORRERY-9 and ORRERY-PROD-8 a release created
    after the decision). They are now the releases of the issue's first event and of the event above,
    never one created after the decision;
  - present-state issue fields the decision could not have had (stats, numComments, assignedTo,
    statusDetails, subscriptionDetails, userReportCount, matchingEventId, shareId) are dropped.

Answers the model actually read (probe_source `verbatim`) and `static` ones are kept byte for byte, as
are logs, metrics and source state rebuilt with their window anchored at the decision. Ids, the
fleet's decision, the outcome and ground truth are carried over unchanged. Each item gains
provenance.v2: what changed, `evidence_rebuilt` (none | partial | all of its probe answers) and where
its lastSeen came from.

Usage (on the fleet host):  python3 build_orrery_items_v2.py V1_DECISIONS_JSONL OUT_DIR
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
import correlate, scrub  # noqa: E402,E401

UTC = dt.timezone.utc
NOT_CAPTURED = "<UNAVAILABLE: not captured>"
PRESENT_STATE = ("stats", "numComments", "assignedTo", "statusDetails", "subscriptionDetails",
                 "userReportCount", "matchingEventId", "shareId")
DOCKER = ["sudo", "-n", "-u", "_dockerhost", "env", "HOME=/var/_dockerhost",
          "PATH=/usr/local/bin:/usr/bin:/bin", "docker"]
BUILT_AT = dt.datetime.now(UTC).isoformat()


def ts(s):
    s = str(s).strip().replace("Z", "+00:00").replace(" ", "T")
    s = re.sub(r"\.(\d+)", lambda m: "." + (m.group(1) + "000000")[:6], s, count=1)
    s = re.sub(r"([+-]\d\d)$", r"\1:00", s)
    t = dt.datetime.fromisoformat(s)
    return t if t.tzinfo else t.replace(tzinfo=UTC)


def iso(t):
    return t.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.") + f"{t.microsecond // 1000:03d}Z"


def pg(sql):
    r = subprocess.run(DOCKER + ["exec", "glitchtip-postgres-1", "psql", "-U", "glitchtip", "-d", "glitchtip",
                                 "-tAF", "\t", "-c", sql], capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError(r.stderr[:300])
    return [x.split("\t") for x in r.stdout.splitlines() if x.strip()]


def event_by_received(issue_id, T, first=False):
    """(event id hex, server-received time, release version, release created) of the issue's latest event
    received at or before T (or its first event), or None."""
    order = "asc" if first else "desc"
    r = pg(f"select replace(e.event_id::text,'-',''), e.created, coalesce(r.version,''), coalesce(r.created::text,'') "
           f"from issue_events_issueevent e left join releases_release r on r.id=e.release_id "
           f"where e.issue_id={int(issue_id)} and e.created <= '{T.isoformat()}' order by e.created {order} limit 1")
    if not r:
        return None
    eid, created, ver, rcreated = r[0]
    return eid, ts(created), ver or None, ts(rcreated) if rcreated else None


def release(ver, created, T):
    if not ver or created is None or created > T:
        return None
    return {"version": ver, "shortVersion": ver, "dateCreated": iso(created)}


def fix(row, stats):
    T = ts(row["provenance"]["decision_time"])
    sig, probes = row["signal"], row["probes"]
    src = row["provenance"]["probe_source"]
    changes, last_seen_source, ev = [], "none", None
    raw = sig.get("raw") or {}
    iid = sig.get("issue_id")
    if raw and iid:
        latest = event_by_received(iid, T)
        firstev = event_by_received(iid, T, first=True)
        if latest:
            eid, received, ver, rcreated = latest
            if raw.get("lastSeen") and ts(raw["lastSeen"]) != received:
                changes.append(f"lastSeen {raw.get('lastSeen')} -> {iso(received)} (server-received)")
            raw["lastSeen"] = iso(received)
            last_seen_source = "server-received"
            new_last = release(ver, rcreated, T)
            new_first = release(*firstev[2:], T) if firstev else None
            for k, new in (("lastRelease", new_last), ("firstRelease", new_first)):
                old = raw.get(k)
                if old and new and ts(old.get("dateCreated") or "1970-01-01") == ts(new["dateCreated"]):
                    continue  # the same release: v1's object, byte for byte
                changes.append(f"{k}.dateCreated {(old or {}).get('dateCreated')} -> "
                               f"{(new or {}).get('dateCreated')} (the release of the event at/before the decision)")
                raw[k] = dict(new, dateReleased=None) if new else None
            ev = correlate._gt(f"/issues/{iid}/events/{eid}/")
            if not isinstance(ev, dict) or not ev:
                ev = None
        else:
            # the issue is gone from GlitchTip since v1: keep only what cannot be later than the decision
            last_seen_source = "unknown"
            for k in ("lastSeen",):
                if raw.get(k) and (ts(raw[k]) > T or ts(raw[k]) < ts(raw.get("firstSeen") or raw[k])):
                    changes.append(f"{k} {raw[k]} -> null (outside firstSeen..decision, issue gone)")
                    raw[k] = None
            for k in ("lastRelease", "firstRelease"):
                d = (raw.get(k) or {}).get("dateCreated")
                if d and ts(d) > T:
                    changes.append(f"{k} created {d} after the decision -> null")
                    raw[k] = None
        dropped = [k for k in PRESENT_STATE if k in raw]
        for k in dropped:
            raw.pop(k)
        if dropped:
            changes.append("dropped present-state fields: " + ",".join(dropped))
        sig["raw"] = raw
    for k in sorted(probes):
        name, s, old = k.split(":", 1)[0], src.get(k), probes[k]
        new = old
        if s == "unavailable":
            new = NOT_CAPTURED
        elif s == "rebuilt" and name == "trace" and isinstance(old, str) and old.startswith("<"):
            new = NOT_CAPTURED
            src[k] = "unavailable"
        elif s == "rebuilt" and name == "event_detail" and ev is not None:
            new = correlate._summarize_event(ev)
        elif s == "rebuilt" and name == "occurrence_history" and raw:
            new = {f: raw.get(f) for f in ("count", "userCount", "firstSeen", "lastSeen", "level", "status", "culprit")}
        if json.dumps(scrub.scrub(new), sort_keys=True) != json.dumps(old, sort_keys=True):
            changes.append(f"probe {k} ({s}) changed")
            stats[f"probe {name} {s}"] += 1
        probes[k] = new
    kinds = collections.Counter(v for v in src.values() if v != "static")
    level = "none" if not (kinds["rebuilt"] or kinds["unavailable"]) else ("all" if not kinds["verbatim"] else "partial")
    row["provenance"]["v2"] = {"built_at": BUILT_AT, "from": "v1 (build_orrery_items.py, 2026-10-29)",
                               "evidence_rebuilt": level, "last_seen_source": last_seen_source,
                               "changes": changes}
    stats[f"evidence_rebuilt {level}"] += 1
    stats[f"last_seen_source {last_seen_source}"] += 1
    stats["items changed" if changes else "items unchanged"] += 1
    return scrub.scrub(row)


def main(v1_path, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    rows = [json.loads(x) for x in open(v1_path) if x.strip()]
    stats = collections.Counter()
    out = [fix(r, stats) for r in rows]
    path = os.path.join(out_dir, "orrery-triage-items-v2.jsonl")
    with open(path, "w") as f:
        for r in out:
            f.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")
    os.chmod(path, 0o600)
    leftover = [(r["id"], k) for r in out for k, v in r["probes"].items()
                if isinstance(v, str) and re.search(r"no longer exists|belongs to a newer issue|holds nothing before", v)]
    print("items:", len(out), "|", dict(sorted(stats.items())))
    print("outcome-stating answers left:", len(leftover), leftover[:3])
    print("secret hits after scrub:", sum(len(scrub.scan(r)) for r in out))
    print("path:", path, "| bytes:", os.path.getsize(path))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
