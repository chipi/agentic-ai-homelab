#!/usr/bin/env python3
"""triage-fleet-review --proposals: triage the fleet's parked proposals in ~/signal-fleet/queue.

Runs ON the Mac mini (via host-run). Stdlib only (Python 3.9).

    proposals.py            # read-only: every pending proposal, its live GlitchTip issue, a proposed action
    proposals.py --apply    # carry out the "done", "stale" and "resolve" actions (operator's go first)

Pending proposals are the plain *.json files. `.filed`, `.resolved` and `.batched-*` are handled.
Each proposal's fingerprint is `glitchtip:<SHORT-ID>` or `grafana:<hash>`. GlitchTip issues are
indexed by short id across every project. Proposed actions:
  done     the GlitchTip issue is already resolved or deleted: mark the proposal resolved
  resolve  a cleanup of an unresolved test/probe/smoke issue: resolve it in GlitchTip, then mark
  stale    a config/tuning proposal whose issue was last seen > STALE_DAYS ago, or a grafana alert the
           fleet hasn't seen in STALE_DAYS (dispositions.tsv): mark resolved
  review   anything else: a person decides (listed, never touched)
--apply resolves through the GlitchTip superuser session (the handbook's curl login), re-reads each
issue to confirm, and renames only the proposals whose action succeeded.
"""
import argparse, collections, json, os, re, subprocess, sys, time, urllib.parse, urllib.request
from datetime import datetime, timedelta, timezone

GT = "http://127.0.0.1:8090"
QUEUE = os.path.expanduser("~/signal-fleet/queue")
DISPOSITIONS = os.path.expanduser("~/signal-fleet/results/dispositions.tsv")
STALE_DAYS = 14
TEST = re.compile(r"probe|smoke|wiring|test event|telemetry tier|delete me|safe to (resolve|delete)|zz-probe|verify\b", re.I)


def envfile(path):
    d = {}
    for line in open(os.path.expanduser(path)):
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            d[k] = v.strip().strip('"').strip("'")
    return d


TOKEN = envfile("~/signal-fleet/fleet-gateway.env")["GLITCHTIP_TOKEN"]


def get(url):
    r = urllib.request.urlopen(urllib.request.Request(url, headers={"Authorization": "Bearer " + TOKEN}), timeout=60)
    return json.loads(r.read()), r.headers.get("Link", "")


def index_issues():
    idx = {}
    for p in get(GT + "/api/0/organizations/homelab/projects/")[0]:
        for status in ("unresolved", "resolved"):
            url = GT + f"/api/0/organizations/homelab/issues/?project={p['id']}&limit=100&query=" + urllib.parse.quote(f"is:{status}")
            for _ in range(50):
                data, link = get(url)
                for i in data:
                    idx[i["shortId"]] = {"id": i["id"], "status": i["status"], "count": i["count"],
                                         "last": i["lastSeen"][:10], "project": p["slug"]}
                nxt = [s for s in link.split(",") if 'rel="next"' in s and 'results="true"' in s]
                if not nxt:
                    break
                url = nxt[0].split(";")[0].strip()[1:-1]
    return idx


def grafana_last_seen():
    last = {}
    try:
        for line in open(DISPOSITIONS):
            f = line.split("\t")
            if len(f) > 2 and f[2].startswith("grafana:"):
                last[f[2]] = max(last.get(f[2], ""), f[0][:10])
    except OSError:
        pass
    return last


def classify(item, idx, glast, today):
    kind, fp, title = item["kind"], item["signal"].get("fingerprint", ""), item["issue"].get("title", "")
    cutoff = (today - timedelta(days=STALE_DAYS)).strftime("%Y-%m-%d")
    if fp.startswith("glitchtip:"):
        g = idx.get(fp.split(":", 1)[1])
        if not g:
            return "done", "issue deleted", None
        if g["status"] == "resolved":
            return ("done" if kind == "cleanup" else "stale" if g["last"] < cutoff else "review"), \
                   f"{g['project']} resolved, last {g['last']}, x{g['count']}", g
        if kind == "cleanup" and TEST.search(title):
            return "resolve", f"{g['project']} unresolved test/smoke, last {g['last']}", g
        return "review", f"{g['project']} unresolved, last {g['last']}, x{g['count']}", g
    if fp.startswith("grafana:"):
        seen = glast.get(fp, "")
        return ("stale" if seen and seen < cutoff else "review"), f"grafana alert last reached the fleet {seen or 'never'}", None
    return "review", "unknown fingerprint shape", None


def superuser_resolve(issue_ids):
    script = r'''
set -a; . ~/agentic-ai-homelab/infra/glitchtip/.env; set +a
GT=http://127.0.0.1:8090; CJ=$(mktemp)
curl -s -c $CJ -b $CJ -o /dev/null $GT/_allauth/browser/v1/config; CSRF=$(awk '$6=="csrftoken"{print $7}' $CJ)
curl -s -c $CJ -b $CJ -o /dev/null -H 'Content-Type: application/json' -H "X-CSRFToken: $CSRF" -H "Referer: $GT/" \
  -d "{\"email\":\"$DJANGO_SUPERUSER_EMAIL\",\"password\":\"$DJANGO_SUPERUSER_PASSWORD\"}" $GT/_allauth/browser/v1/auth/login
CSRF=$(awk '$6=="csrftoken"{print $7}' $CJ)
for id in "$@"; do
  printf "%s %s\n" "$id" "$(curl -s -c $CJ -b $CJ -o /dev/null -w "%{http_code}" -X PUT -H "X-CSRFToken: $CSRF" -H "Referer: $GT/" -H 'Content-Type: application/json' -d '{"status":"resolved"}' "$GT/api/0/organizations/homelab/issues/?id=$id")"
done
rm -f $CJ
'''
    out = subprocess.run(["bash", "-c", script, "gt"] + [str(i) for i in issue_ids], capture_output=True, text=True, timeout=300)
    return dict(l.split() for l in out.stdout.splitlines() if len(l.split()) == 2)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    today = datetime.now(timezone.utc)
    pending = sorted(n for n in os.listdir(QUEUE) if n.endswith(".json") and os.path.isfile(os.path.join(QUEUE, n)))
    states = collections.Counter(re.sub(r"^.*\.json", "", n) or "(pending)" for n in os.listdir(QUEUE)
                                 if os.path.isfile(os.path.join(QUEUE, n)))
    print(f"queue: {dict(states)}")
    if not pending:
        print("PROPOSALS: 0 pending")
        return
    idx, glast = index_issues(), grafana_last_seen()
    rows = []
    for n in pending:
        item = json.load(open(os.path.join(QUEUE, n)))
        action, why, g = classify(item, idx, glast, today)
        rows.append((action, n, item, why, g))
    by = collections.Counter(r[0] for r in rows)
    for action in ("review", "resolve", "stale", "done"):
        sel = [r for r in rows if r[0] == action]
        if sel:
            print(f"== {action} ({len(sel)})")
            for _, n, item, why, _ in sel:
                print(f"  {item['signal'].get('fingerprint', '')[:34]:34} {why:52.52} | {item['issue'].get('title', '')[:70]}")
    print(f"PROPOSALS: {len(rows)} pending: " + ", ".join(f"{k} {v}" for k, v in sorted(by.items())))
    if not a.apply:
        print("(read-only; --apply carries out done/stale/resolve after the operator's go)")
        return
    res = [r for r in rows if r[0] == "resolve"]
    codes = superuser_resolve([r[4]["id"] for r in res]) if res else {}
    marked = 0
    for action, n, item, why, g in rows:
        if action == "review":
            continue
        if action == "resolve":
            if codes.get(str(g["id"])) != "200":
                print(f"  NOT marked (resolve failed, HTTP {codes.get(str(g['id']))}): {n}")
                continue
            st = get(GT + f"/api/0/issues/{g['id']}/")[0].get("status")
            if st != "resolved":
                print(f"  NOT marked (re-read shows {st}): {n}")
                continue
        os.rename(os.path.join(QUEUE, n), os.path.join(QUEUE, n + ".resolved"))
        marked += 1
    print(f"APPLIED: {marked} proposal(s) marked resolved; review left: {by.get('review', 0)}")


if __name__ == "__main__":
    main()
