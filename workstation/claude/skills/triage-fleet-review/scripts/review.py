#!/usr/bin/env python3
"""Weekly review of the triage fleet (signal-fleet, Fleet 2). Read-only.

Host side (over ssh): fleetd cycle health, dispositions and filed ledgers, state
files. GitHub side (local `gh`): what the fleet did on issues in the window, and the
three failure shapes to look for: fan-out, reopened duplicates, rollup burials.

  review.py [--days 7] [--ssh "ssh -i ~/.ssh/homelab_mini -o IdentitiesOnly=yes markodragoljevic@homelab"]
            [--repos chipi/podcast_scraper,chipi/orrery,chipi/agentic-ai-homelab]
"""
import argparse
import collections
import datetime as dt
import json
import os
import re
import shlex
import subprocess
import sys

DEFAULT_SSH = os.environ.get("HOMELAB_SSH",
                             "ssh -i ~/.ssh/homelab_mini -o IdentitiesOnly=yes markodragoljevic@homelab")
DEFAULT_REPOS = "chipi/podcast_scraper,chipi/orrery,chipi/agentic-ai-homelab"

# Runs ON the fleet host with python3 (stdlib only; the mini has 3.9).
HOST = r'''
import csv, collections, json, os, re, sys, datetime as dt
days = int(sys.argv[1]); since = (dt.datetime.utcnow() - dt.timedelta(days=days)).strftime("%Y-%m-%dT%H:%M")
H = os.path.expanduser
out = {"since": since}
# fleetd: one line per cycle, local time 'YYYY/MM/DD HH:MM:SS [triage] cycle <id>: <outcome> ...'
cyc = collections.Counter(); last = ""
lsince = (dt.datetime.now() - dt.timedelta(days=days)).strftime("%Y/%m/%d %H:%M")
for l in open(H("~/fleetd/fleetd.log"), errors="replace"):
    if "[triage] cycle triage-" in l and l[:16] >= lsince:
        m = re.search(r"cycle triage-\S+: (\w+)", l); cyc[m.group(1) if m else "?"] += 1; last = l.strip()
out["cycles"] = dict(cyc); out["last_cycle"] = last
out["stop_flag"] = os.path.exists(H("~/signal-fleet/STOP"))
rows = [d for d in csv.DictReader(open(H("~/signal-fleet/results/dispositions.tsv")), delimiter="\t") if d["ts"][:16] >= since]
out["dispositions"] = [[k[0], k[1], n] for k, n in collections.Counter((d["source"], d["disposition"]) for d in rows).most_common()]
rec = collections.Counter(d["fingerprint"] for d in rows if d["disposition"] == "recurrence")
out["top_recurrence"] = rec.most_common(5)
out["gates"] = collections.Counter(d["gates"].split("/")[0] for d in rows if d["disposition"] != "recurrence" and d["gates"]).most_common(8)
out["escalations"] = [[d["ts"][:16], d["fingerprint"], d["alertname"][:90], d["reason"][:160]] for d in rows if d["disposition"] == "escalate"]
out["dismiss_sample"] = [[d["ts"][:16], d["fingerprint"], d["alertname"][:90], d["gates"], d["reason"][:200]]
                         for d in rows if d["disposition"] == "dismiss"][-5:]
out["spend_rows"] = len([d for d in rows if d.get("model") and d["model"] != "none(operational-gate)"])
filed = list(csv.DictReader(open(H("~/signal-fleet/results/filed.tsv")), delimiter="\t"))
out["filed_rows"] = len(filed)
out["filed_new"] = [[r["filed_at"][:16], r["repo"], r["issue"], r["fingerprint"]] for r in filed if (r.get("filed_at") or "")[:16] >= since]
out["ledger_lines"] = sum(1 for _ in open(H("~/signal-fleet/results/dispositions.tsv")))
out["deferred"] = json.load(open(H("~/signal-fleet/results/.deferred.json"))) if os.path.exists(H("~/signal-fleet/results/.deferred.json")) else {}
print(json.dumps(out))
'''


def host_stats(ssh, days):
    cmd = shlex.split(os.path.expanduser(ssh)) + ["python3", "-", str(days)]
    r = subprocess.run(cmd, input=HOST, capture_output=True, text=True, timeout=180)
    if r.returncode != 0:
        sys.exit(f"host query failed: {r.stderr.strip()[:400]}")
    return json.loads(r.stdout)


def gh(path):
    r = subprocess.run(["gh", "api", "--paginate", path], capture_output=True, text=True, timeout=180)
    if r.returncode != 0:
        sys.exit(f"gh api {path} failed: {r.stderr.strip()[:300]}")
    txt = r.stdout.strip().replace("][", ",")        # --paginate concatenates arrays
    return json.loads(txt or "[]")


FLEET_MARKERS = ("Recurred ", "Low-signal occurrence", "**Looks resolved?**", "signal-fleet")


def github(repos, since_iso):
    acts, issues = [], []
    for repo in repos:
        for c in gh(f"repos/{repo}/issues/comments?since={since_iso}&per_page=100"):
            if c["created_at"] < since_iso or not c["body"].startswith(FLEET_MARKERS) and "signal-fleet" not in c["body"]:
                continue
            body = c["body"]
            kind = ("reopen" if "after close" in body else "recurrence" if body.startswith("Recurred") else
                    "rollup" if body.startswith("Low-signal") else "stale-nudge" if "Looks resolved" in body else "other")
            m = re.search(r"`([^`]+)`", body)
            num = int(c["issue_url"].rsplit("/", 1)[1])
            acts.append({"t": c["created_at"], "repo": repo, "issue": num, "kind": kind,
                         "signal": (m.group(1) if m else "")[:100], "via_dup": "via duplicate" in body, "body": body[:400]})
        for i in gh(f"repos/{repo}/issues?state=all&labels=triage-fleet/filed&since={since_iso}&per_page=100"):
            if "pull_request" not in i and i["created_at"] >= since_iso:
                issues.append({"repo": repo, "issue": i["number"], "t": i["created_at"], "title": i["title"][:90],
                               "labels": [l["name"] for l in i["labels"]]})
    return acts, issues


def fanout(acts, minutes=15):
    """Several DIFFERENT issues written for the same signal text within minutes."""
    by = collections.defaultdict(list)
    for a in acts:
        if a["kind"] in ("reopen", "recurrence") and a["signal"]:
            by[(a["repo"], a["signal"])].append(a)
    flags = []
    for (repo, sig), xs in by.items():
        xs.sort(key=lambda a: a["t"])
        for i in range(len(xs)):
            win = [x for x in xs[i:] if _ts(x["t"]) - _ts(xs[i]["t"]) <= dt.timedelta(minutes=minutes)]
            iss = sorted({x["issue"] for x in win})
            if len(iss) >= 3:
                flags.append((repo, sig, xs[i]["t"][:16], iss))
                break
    return flags


def _ts(s):
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--ssh", default=DEFAULT_SSH)
    ap.add_argument("--repos", default=DEFAULT_REPOS)
    a = ap.parse_args()
    since_iso = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=a.days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    h = host_stats(a.ssh, a.days)
    acts, new = github(a.repos.split(","), since_iso)

    print(f"# Triage fleet review — last {a.days} days (since {since_iso})\n")
    print("## 1. Alive")
    print(f"- cycles: {h['cycles'] or 'NONE'}  (healthy: all `ok`, ~{a.days * 144} at 10-min intervals)")
    print(f"- last cycle: `{h['last_cycle']}`")
    print(f"- STOP flag present: {h['stop_flag']}")
    print("\n## 2. Decided (dispositions ledger)")
    for src, disp, n in h["dispositions"]:
        print(f"- {src:<9} {disp:<10} {n}")
    print(f"- deterministic gates on decisions: {h['gates']}")
    print(f"- most recurrence rows: {h['top_recurrence']}  (since b3c4c5f: one row per count change; dozens for one fingerprint = a regression)")
    print(f"- escalations: {len(h['escalations'])}")
    for e in h["escalations"][:10]:
        print(f"  - {e[0]} {e[1]} — {e[2]} — {e[3]}")
    print("\n## 3. Did on GitHub")
    kinds = collections.Counter((x["repo"].split("/")[1], x["kind"]) for x in acts)
    for (repo, kind), n in sorted(kinds.items()):
        print(f"- {repo:<20} {kind:<12} {n}")
    print(f"- new issues filed: {len(new)}")
    for i in new:
        print(f"  - {i['repo']}#{i['issue']} {i['t'][:16]} {i['title']}")
    print("\n## 4. Flags (each needs a human look)")
    fo = fanout(acts)
    print(f"- fan-out (one signal, 3+ issues within 15 min): {len(fo)}")
    for repo, sig, t, iss in fo:
        print(f"  - {repo} {t} `{sig}` -> issues {iss}  (fix the source rule, see runbook)")
    reopen = [x for x in acts if x["kind"] == "reopen"]
    print(f"- reopens: {len(reopen)} (judge each: was the close premature, or is the match wrong?)")
    for x in reopen[:15]:
        print(f"  - {x['repo']}#{x['issue']} {x['t'][:16]} `{x['signal']}`{' (via duplicate)' if x['via_dup'] else ''}")
    roll = [x for x in acts if x["kind"] == "rollup"]
    print(f"- rollup comments (low-signal bucket): {len(roll)} — check none is a real bug buried as one line")
    for x in roll[:10]:
        line = re.sub(r"\s+", " ", x["body"])[:160]
        print(f"  - {x['repo']}#{x['issue']} {x['t'][:16]} {line}")
    print(f"- stale nudges: {sum(1 for x in acts if x['kind'] == 'stale-nudge')}")
    print("\n## 5. False-dismiss audit (sample — check each cited evidence in GlitchTip/Grafana)")
    for d in h["dismiss_sample"]:
        print(f"- {d[0]} {d[1]} — {d[2]} [{d[3]}] — {d[4]}")
    print("\n## 6. Ledger health")
    print(f"- dispositions.tsv lines: {h['ledger_lines']}; filed.tsv rows: {h['filed_rows']} ({len(h['filed_new'])} new in window)")
    print(f"- deferred signals (.deferred.json): {h['deferred'] or 'none'}")
    print("\n## Not covered by this script")
    print("- warnings and errors that never reach the fleet: run the `o11y-review` skill for the same window")
    print("- spend vs the $2/day cap: Grafana 'Fleet Workforce — Triage (Fleet 2)', fleetd_spend_day")
    print("- whether each flagged item is right or wrong: that is the reviewer's judgement, not the script's")


if __name__ == "__main__":
    main()
