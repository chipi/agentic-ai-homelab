#!/usr/bin/env python3
"""Resolve GlitchTip issues nobody has seen for N days, so "unresolved" means something again.

On 2026-10-15 every issue in every project was unresolved (424 in podcast-pipeline alone):
nothing ever resolved them, so the open count measured history, not current problems.
An issue resolved here and seen again is reopened by GlitchTip (regression), so this
loses nothing; it only stops old noise from looking current.

    python3 resolve-stale.py              # dry run: what would be resolved, per project
    python3 resolve-stale.py --apply      # resolve
    python3 resolve-stale.py --days 30    # another threshold

Runs on the mini (LaunchDaemon com.homelab.glitchtip-resolve-stale, daily), as the
GlitchTip superuser from infra/glitchtip/.env (the fleet's read token cannot write).
"""
import argparse
import collections
import datetime as dt
import http.cookiejar
import json
import os
import urllib.parse
import urllib.request
from pathlib import Path

GT = os.environ.get("GLITCHTIP_URL", "http://127.0.0.1:8090")
ORG = os.environ.get("GLITCHTIP_ORG", "homelab")
ENV_FILE = Path(__file__).resolve().parent / ".env"


def _env():
    if not os.environ.get("DJANGO_SUPERUSER_EMAIL") and ENV_FILE.exists():
        for line in ENV_FILE.read_text().splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


class Session:
    def __init__(self):
        self.jar = http.cookiejar.CookieJar()
        self.op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar))

    def _csrf(self):
        return next((c.value for c in self.jar if c.name == "csrftoken"), "")

    def call(self, method, path, body=None):
        req = urllib.request.Request(GT + path, method=method,
                                     data=json.dumps(body).encode() if body is not None else None,
                                     headers={"Content-Type": "application/json", "Referer": GT + "/",
                                              "X-CSRFToken": self._csrf()})
        with self.op.open(req, timeout=60) as r:
            raw = r.read()
            # GlitchTip marks its cookies Secure (it serves behind HTTPS), and urllib rightly
            # won't send those over the plain-HTTP loopback this script uses on the mini.
            for c in self.jar:
                c.secure = False
            return json.loads(raw) if raw else None, r.headers

    def login(self):
        self.call("GET", "/_allauth/browser/v1/config")
        self.call("POST", "/_allauth/browser/v1/auth/login",
                  {"email": os.environ["DJANGO_SUPERUSER_EMAIL"], "password": os.environ["DJANGO_SUPERUSER_PASSWORD"]})


def unresolved(s):
    cursor = ""
    while True:
        q = urllib.parse.urlencode({"query": "is:unresolved", "limit": 100})
        page, headers = s.call("GET", f"/api/0/organizations/{ORG}/issues/?{q}{cursor}")
        yield from page or []
        nxt = [p for p in (headers.get("Link") or "").split(",") if 'rel="next"' in p and 'results="true"' in p]
        if not nxt:
            return
        cursor = "&cursor=" + urllib.parse.quote(nxt[0].split("cursor=")[1].split(">")[0].split("&")[0])


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--days", type=int, default=14)
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    _env()
    s = Session()
    s.login()
    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=a.days)
    stale, kept = collections.defaultdict(list), collections.Counter()
    for i in unresolved(s):
        project = (i.get("project") or {}).get("slug", "?")
        seen = dt.datetime.fromisoformat(i["lastSeen"].replace("Z", "+00:00"))
        if seen < cutoff:
            stale[project].append(i["id"])
        else:
            kept[project] += 1
    total = sum(len(v) for v in stale.values())
    for project in sorted(set(stale) | set(kept)):
        print(f"  {project:28} resolve {len(stale[project]):4}   keep open {kept[project]:4}")
    if not a.apply:
        print(f"DRY RUN: would resolve {total} issue(s) not seen for {a.days} days (pass --apply)")
        return
    done = 0
    for project, ids in stale.items():
        for k in range(0, len(ids), 100):
            batch = ids[k:k + 100]
            q = "&".join(f"id={x}" for x in batch)
            s.call("PUT", f"/api/0/organizations/{ORG}/issues/?{q}", {"status": "resolved"})
            done += len(batch)
    print(f"resolved {done} issue(s) not seen for {a.days} days")


if __name__ == "__main__":
    main()
