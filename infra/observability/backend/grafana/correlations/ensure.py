#!/usr/bin/env python3
"""Make Grafana's correlations match correlations.json (idempotent; stdlib only).

Why not provisioning: Grafana 11.6's datasource provisioner cannot hold these — a
top-level `type` panics ("interface {} is string, not correlations.CorrelationType")
and without it the correlation is stored with an empty config (both tried 2026-10-14).
So the definitions live here in git and this script applies them through the API.

Matches by (sourceUID, label): creates what is missing, updates what differs, leaves
correlations it does not manage alone. Run on the mini after Grafana is (re)created:

  set -a; . infra/observability/backend/.env; set +a
  python3 infra/observability/backend/grafana/correlations/ensure.py [--check]

--check: report drift and exit 1 if any, change nothing.
"""
import base64, json, os, pathlib, sys, urllib.error, urllib.request

GRAFANA = os.environ.get("GRAFANA_URL", "http://127.0.0.1:3000")
AUTH = "Basic " + base64.b64encode(
    f"{os.environ['GRAFANA_ADMIN_USER']}:{os.environ['GRAFANA_ADMIN_PASSWORD']}".encode()).decode()
WANT = json.loads((pathlib.Path(__file__).parent / "correlations.json").read_text())
FIELDS = ("targetUID", "label", "description", "type", "config")


def api(method, path, body=None):
    req = urllib.request.Request(GRAFANA + path, method=method,
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Authorization": AUTH, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        sys.exit(f"{method} {path}: HTTP {e.code} {e.read().decode(errors='replace')[:300]}")


def main():
    check = "--check" in sys.argv
    have = api("GET", "/api/datasources/correlations?limit=1000").get("correlations", [])
    drift = 0
    for want in WANT:
        src = want["sourceUID"]
        body = {k: want[k] for k in FIELDS}
        cur = next((c for c in have if c["sourceUID"] == src and c["label"] == want["label"]), None)
        if cur is None:
            drift += 1
            print(f"missing: {src} -> {want['targetUID']} '{want['label']}'")
            if not check:
                api("POST", f"/api/datasources/uid/{src}/correlations", body)
                print("  created")
        elif any(cur.get(k) != want[k] for k in FIELDS):
            drift += 1
            print(f"differs: {src} '{want['label']}' ({cur['uid']})")
            if not check:
                api("PATCH", f"/api/datasources/uid/{src}/correlations/{cur['uid']}", body)
                print("  updated")
        else:
            print(f"ok: {src} -> {want['targetUID']} '{want['label']}'")
    if check and drift:
        sys.exit(1)


if __name__ == "__main__":
    main()
