#!/usr/bin/env python3
"""telemetry-probe: send ONE labelled test signal, prove it landed only where expected, delete it.

Runs ON the Mac mini (via host-run): it uses the services' local ports and credential files.

    probe.py glitchtip --project player-dev [--assert-absent player,player-api] [--keep]
    probe.py umami     --site "Player (dev)" [--assert-absent Player] [--keep]
    probe.py langfuse  --keys ~/podcast-langfuse-dev.env [--keep]

Every probe is labelled zz-probe-<utc>, so it is findable and never mistaken for a real error.
Exit 0 and "PROBE: PASS" only when: it landed in the target, it is absent from every
--assert-absent target, and (unless --keep) it was deleted and re-reading it shows it gone.
Stdlib only (the mini has Python 3.9). Never prints a secret.
"""
import argparse, base64, json, os, subprocess, sys, tempfile, time, urllib.parse, urllib.request, uuid

GT = "http://127.0.0.1:8090"
UMAMI = "http://127.0.0.1:3001"
LF = "http://127.0.0.1:4000"
DOCKER = "/usr/local/bin/docker"
BROWSER_UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
              "Chrome/141.0.0.0 Safari/537.36 telemetry-probe/1.0")
LABEL = "zz-probe-" + time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
results = []


def check(ok, what):
    results.append(ok)
    print(f"  [{'PASS' if ok else 'FAIL'}] {what}")
    return ok


def envfile(path):
    d = {}
    for line in open(os.path.expanduser(path)):
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            d[k] = v.strip().strip('"').strip("'")
    return d


def http(url, data=None, headers=None, method=None, timeout=30):
    req = urllib.request.Request(url, data=data, headers=headers or {}, method=method)
    try:
        r = urllib.request.urlopen(req, timeout=timeout)
        return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def wait(fn, tries=20, delay=3):
    for _ in range(tries):
        v = fn()
        if v:
            return v
        time.sleep(delay)
    return None


# ---------------------------------------------------------------- GlitchTip
def gt_read(path):
    tok = envfile("~/signal-fleet/fleet-gateway.env")["GLITCHTIP_TOKEN"]
    code, body = http(GT + "/api/0" + path, headers={"Authorization": "Bearer " + tok})
    return code, (json.loads(body) if code == 200 else None)


def gt_superuser(method, path, body=None):
    """The superuser session write, done with curl exactly as the handbook recipe (section 7)."""
    script = r'''
set -a; . ~/agentic-ai-homelab/infra/glitchtip/.env; set +a
GT=http://127.0.0.1:8090; CJ=$(mktemp)
curl -s -c $CJ -b $CJ -o /dev/null $GT/_allauth/browser/v1/config; CSRF=$(awk '$6=="csrftoken"{print $7}' $CJ)
curl -s -c $CJ -b $CJ -o /dev/null -H 'Content-Type: application/json' -H "X-CSRFToken: $CSRF" -H "Referer: $GT/" \
  -d "{\"email\":\"$DJANGO_SUPERUSER_EMAIL\",\"password\":\"$DJANGO_SUPERUSER_PASSWORD\"}" $GT/_allauth/browser/v1/auth/login
CSRF=$(awk '$6=="csrftoken"{print $7}' $CJ)
curl -s -c $CJ -b $CJ -o /dev/null -w "%{http_code}" -X "$1" -H "X-CSRFToken: $CSRF" -H "Referer: $GT/" \
  -H 'Content-Type: application/json' ${3:+-d "$3"} "$GT$2"
rm -f $CJ
'''
    out = subprocess.run(["bash", "-c", script, "gt", method, path, body or ""],
                         capture_output=True, text=True, timeout=60)
    return out.stdout.strip()


def gt_find(project_slug, label):
    _, issues = gt_read(f"/organizations/homelab/issues/?limit=50&query=&project={gt_project_id(project_slug)}")
    return next((i for i in issues or [] if label in i.get("title", "")), None)


_projects = None


def gt_project_id(slug):
    global _projects
    if _projects is None:
        _projects = {p["slug"]: p["id"] for p in gt_read("/organizations/homelab/projects/")[1]}
    if slug not in _projects:
        sys.exit(f"unknown GlitchTip project {slug!r}; known: {sorted(_projects)}")
    return _projects[slug]


def probe_glitchtip(a):
    pid = gt_project_id(a.project)
    key = gt_read(f"/projects/homelab/{a.project}/keys/")[1][0]["public"]
    eid = uuid.uuid4().hex
    ev = {"event_id": eid, "timestamp": time.time(), "platform": "python", "level": "error",
          "environment": "probe", "release": "telemetry-probe",
          "message": {"formatted": f"{LABEL} telemetry-probe (delete me)"}}
    body = "\n".join([json.dumps({"event_id": eid}), json.dumps({"type": "event"}), json.dumps(ev)]).encode()
    code, _ = http(f"{GT}/api/{pid}/envelope/", data=body, method="POST", headers={
        "Content-Type": "application/x-sentry-envelope",
        "X-Sentry-Auth": f"Sentry sentry_version=7, sentry_key={key}, sentry_client=telemetry-probe/1.0"})
    check(code == 200, f"envelope accepted by {a.project} (HTTP {code})")
    issue = wait(lambda: gt_find(a.project, LABEL))
    check(bool(issue), f"issue landed in {a.project}" + (f": {issue['shortId']}" if issue else ""))
    for other in a.assert_absent:
        check(gt_find(other, LABEL) is None, f"absent from {other}")
    if issue and not a.keep:
        code = gt_superuser("DELETE", f"/api/0/organizations/homelab/issues/?id={issue['id']}")
        check(code in ("200", "204"), f"delete accepted (HTTP {code})")
        gone = wait(lambda: gt_read(f"/issues/{issue['id']}/")[0] == 404, tries=10, delay=3)
        check(bool(gone), "re-read returns 404 (deleted)")


# ---------------------------------------------------------------- Umami
def umami_sql(sql):
    out = subprocess.run([DOCKER, "exec", "-i", "umami-db", "psql", "-U", "umami", "-d", "umami",
                          "-At", "-F", "|", "-v", "ON_ERROR_STOP=1"], input=sql, capture_output=True, text=True)
    if out.returncode:
        sys.exit("umami sql failed: " + out.stderr.strip()[:300])
    return out.stdout.strip()


def umami_site(name_or_id):
    q = name_or_id.replace("'", "''")
    row = umami_sql(f"SELECT website_id, name FROM website WHERE deleted_at IS NULL AND "
                    f"(website_id::text = '{q}' OR name = '{q}');")
    if not row:
        sys.exit(f"unknown Umami site {name_or_id!r}")
    return row.split("\n")[0].split("|")


def probe_umami(a):
    sid, sname = umami_site(a.site)
    body = json.dumps({"type": "event", "payload": {"website": sid, "hostname": "telemetry-probe.localhost",
                       "url": "/zz-probe", "name": LABEL, "data": {"probe": True}}}).encode()
    code, resp = http(UMAMI + "/api/send", data=body, method="POST",
                      headers={"Content-Type": "application/json", "User-Agent": BROWSER_UA})
    bot = b"beep" in resp
    check(code == 200 and not bot, f"collect accepted by {sname} (HTTP {code}{', BOT-FILTERED' if bot else ''})")
    count = lambda w: int(umami_sql(f"SELECT count(*) FROM website_event WHERE website_id = '{w}' "
                                     f"AND event_name = '{LABEL}';") or 0)
    landed = wait(lambda: count(sid) > 0, tries=10, delay=2)
    check(bool(landed), f"event stored in {sname}")
    for other in a.assert_absent:
        oid, oname = umami_site(other)
        check(count(oid) == 0, f"absent from {oname}")
    if landed and not a.keep:
        umami_sql(f"""BEGIN;
CREATE TEMP TABLE p AS SELECT event_id, session_id FROM website_event WHERE event_name = '{LABEL}';
DELETE FROM event_data WHERE website_event_id IN (SELECT event_id FROM p);
DELETE FROM website_event WHERE event_id IN (SELECT event_id FROM p);
DELETE FROM session_data WHERE session_id IN (SELECT session_id FROM p)
  AND NOT EXISTS (SELECT 1 FROM website_event w WHERE w.session_id = session_data.session_id);
DELETE FROM session WHERE session_id IN (SELECT session_id FROM p)
  AND NOT EXISTS (SELECT 1 FROM website_event w WHERE w.session_id = session.session_id);
COMMIT;""")
        check(count(sid) == 0, "deleted (event and orphan session gone)")


# ---------------------------------------------------------------- Langfuse
def probe_langfuse(a):
    k = envfile(a.keys)
    auth = "Basic " + base64.b64encode(f"{k['LANGFUSE_PUBLIC_KEY']}:{k['LANGFUSE_SECRET_KEY']}".encode()).decode()
    tid = uuid.uuid4().hex
    ts = time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime())
    batch = {"batch": [{"id": uuid.uuid4().hex, "type": "trace-create", "timestamp": ts,
                        "body": {"id": tid, "name": LABEL, "tags": ["telemetry-probe"]}}]}
    code, _ = http(LF + "/api/public/ingestion", data=json.dumps(batch).encode(), method="POST",
                   headers={"Content-Type": "application/json", "Authorization": auth})
    check(code in (200, 207), f"ingestion accepted (HTTP {code})")
    got = wait(lambda: http(f"{LF}/api/public/traces/{tid}", headers={"Authorization": auth})[0] == 200,
               tries=15, delay=4)
    check(bool(got), f"trace readable in project {k.get('LANGFUSE_PROJECT', '(from keys)')}")
    if got and not a.keep:
        code, _ = http(f"{LF}/api/public/traces/{tid}", method="DELETE", headers={"Authorization": auth})
        check(code in (200, 202, 204), f"delete accepted (HTTP {code}; Langfuse deletes asynchronously)")
        gone = wait(lambda: http(f"{LF}/api/public/traces/{tid}", headers={"Authorization": auth})[0] == 404,
                    tries=15, delay=4)
        check(bool(gone), "re-read returns 404 (deleted)")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="service", required=True)
    g = sub.add_parser("glitchtip"); g.add_argument("--project", required=True)
    u = sub.add_parser("umami"); u.add_argument("--site", required=True)
    l = sub.add_parser("langfuse"); l.add_argument("--keys", required=True, help="env file with LANGFUSE_PUBLIC_KEY/SECRET_KEY")
    for p in (g, u):
        p.add_argument("--assert-absent", default="", help="comma-separated targets that must NOT get the probe")
    for p in (g, u, l):
        p.add_argument("--keep", action="store_true", help="leave the probe in place (default: delete it)")
    a = ap.parse_args()
    if hasattr(a, "assert_absent"):
        a.assert_absent = [x.strip() for x in a.assert_absent.split(",") if x.strip()]
    print(f"telemetry-probe {a.service} label={LABEL}")
    {"glitchtip": probe_glitchtip, "umami": probe_umami, "langfuse": probe_langfuse}[a.service](a)
    ok = all(results) and results
    print("PROBE: PASS" if ok else "PROBE: FAIL")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
