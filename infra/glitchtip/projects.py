#!/usr/bin/env python3
"""GlitchTip projects as code: diff projects.json against the live org, create what is missing.

    python3 projects.py            # dry run: missing / extra / platform differences
    python3 projects.py --apply    # create missing projects (never deletes or renames)

Runs on the mini as the GlitchTip superuser (infra/glitchtip/.env), like resolve-stale.py.
Creating a project mints a DSN; wiring it into an app (its deploy secret) stays a deliberate
step, so this prints the new project's id and never the key.
"""
import argparse
import json
from pathlib import Path

from importlib.machinery import SourceFileLoader

HERE = Path(__file__).resolve().parent
rs = SourceFileLoader("resolve_stale", str(HERE / "resolve-stale.py")).load_module()


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    want = {p["slug"]: p for p in json.loads((HERE / "projects.json").read_text())["projects"]}
    rs._env()
    s = rs.Session()
    s.login()
    live = {p["slug"]: p for p in (s.call("GET", f"/api/0/organizations/{rs.ORG}/projects/")[0] or [])}
    teams = {t["slug"] for t in (s.call("GET", f"/api/0/organizations/{rs.ORG}/teams/")[0] or [])}
    missing = [w for w in want.values() if w["slug"] not in live]
    for slug, p in sorted(live.items(), key=lambda kv: int(kv[1]["id"])):
        w = want.get(slug)
        note = "NOT IN projects.json" if not w else ""
        if w and (p.get("platform") or "") != w["platform"]:
            note = f"platform live={p.get('platform')} want={w['platform']}"
        print(f"  {p['id']:>4} {slug:28} {note}")
    for w in missing:
        print(f"   new {w['slug']:28} MISSING (team {w['team']})")
    if not a.apply:
        print(f"DRY RUN: {len(missing)} missing project(s) (pass --apply to create)")
        return
    for w in missing:
        if w["team"] not in teams:
            s.call("POST", f"/api/0/organizations/{rs.ORG}/teams/", {"slug": w["team"]})
            teams.add(w["team"])
        p = s.call("POST", f"/api/0/teams/{rs.ORG}/{w['team']}/projects/", {"name": w["slug"], "platform": w["platform"]})[0]
        print(f"created {p.get('slug')} id {p.get('id')} — set its DSN in the app's deploy secret")


if __name__ == "__main__":
    main()
