#!/usr/bin/env python3
"""Alert-rule drift: does Grafana run the rules the repo says it runs?

Grafana only picks up rules.yaml changes on an alerting-provisioning reload. On
2026-09-30 two committed changes had never been loaded: the podcast-ingest-stalled
fix (9bc438f, 09-19) and four delivery-cadence rules (b7f7f07, 09-18). The old
ingest rule fired a false critical alert for 12 days (#58), and the four rules
never ran. Nothing noticed, because nothing compared the two.

This compares the repo's rules.yaml with Grafana's provisioned rules, per uid:
  missing  in the repo, not live   (a committed rule that never took effect)
  extra    live, not in the repo   (a rule nobody can review)
  changed  both, but the evaluated behaviour differs: queries, conditions, the
           condition ref, `for`, noDataState, title or labels. Annotations are
           left out on purpose — wording is not behaviour.
Durations are compared as seconds ("0s" == "0m"): the 2026-09-30 comparison found
five rules that differed only in that spelling.

  drift.py --repo rules.yaml --live live.json            # compare two files
  drift.py --repo rules.yaml --grafana URL --env FILE    # compare against Grafana
           [--push VM_URL]                               # and push the counts
Exit code: 0 = no drift, 1 = drift, 2 = could not check.
"""
import argparse
import base64
import json
import re
import sys
import subprocess
import urllib.request

try:
    import yaml
except ImportError:          # the mini's /usr/bin/python3 has no PyYAML; nothing is
    yaml = None              # installed for this — macOS's system Ruby parses YAML instead

DEFAULT_NODATA = "NoData"   # Grafana's default when a rule omits noDataState


def _seconds(d):
    if d in (None, "", 0):
        return 0
    if isinstance(d, (int, float)):
        return int(d)
    m = re.fullmatch(r"\s*(\d+)\s*([smhd]?)\s*", str(d))
    if not m:
        return str(d)
    return int(m.group(1)) * {"": 1, "s": 1, "m": 60, "h": 3600, "d": 86400}[m.group(2)]


def _data(rule):
    out = []
    for q in rule.get("data") or []:
        m = q.get("model") or {}
        rtr = q.get("relativeTimeRange") or {}
        out.append({
            "refId": q.get("refId"),
            "datasource": q.get("datasourceUid"),
            "expr": m.get("expr"),
            "expression": m.get("expression"),
            "type": m.get("type"),
            "conditions": json.dumps(m.get("conditions"), sort_keys=True) if m.get("conditions") else None,
            "reducer": m.get("reducer"),
            # Grafana stores (0, 0) on expression steps where rules.yaml omits the range
            "range": (_seconds(rtr.get("from")), _seconds(rtr.get("to"))),
        })
    return sorted(out, key=lambda x: str(x["refId"]))


def behaviour(rule):
    """The fields that decide when and how a rule fires."""
    return {
        "title": rule.get("title"),
        "condition": rule.get("condition"),
        "for": _seconds(rule.get("for")),
        "noDataState": rule.get("noDataState") or DEFAULT_NODATA,
        "labels": dict(sorted((rule.get("labels") or {}).items())),
        "data": _data(rule),
    }


def _load_yaml(text):
    if yaml is not None:
        return yaml.safe_load(text)
    out = subprocess.run(["/usr/bin/ruby", "-ryaml", "-rjson", "-e",
                          "puts YAML.safe_load(STDIN.read).to_json"],
                         input=text, capture_output=True, text=True, check=True).stdout
    return json.loads(out)


def repo_rules(rules_yaml_text):
    doc = _load_yaml(rules_yaml_text) or {}
    return {r["uid"]: r for g in doc.get("groups") or [] for r in g.get("rules") or []}


def compare(repo, live):
    """repo, live: {uid: rule}. Returns {"missing": [...], "extra": [...],
    "changed": {uid: [field, ...]}}."""
    changed = {}
    for uid in sorted(set(repo) & set(live)):
        a, b = behaviour(repo[uid]), behaviour(live[uid])
        diff = [k for k in a if a[k] != b[k]]
        if diff:
            changed[uid] = diff
    return {"missing": sorted(set(repo) - set(live)),
            "extra": sorted(set(live) - set(repo)),
            "changed": changed}


def _grafana_rules(url, env_file):
    pw = ""
    with open(env_file) as f:
        for line in f:
            if line.startswith("GRAFANA_ADMIN_PASSWORD="):
                pw = line.split("=", 1)[1].strip()
    req = urllib.request.Request(url.rstrip("/") + "/api/v1/provisioning/alert-rules")
    req.add_header("Authorization", "Basic " + base64.b64encode(f"admin:{pw}".encode()).decode())
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.load(r)


def metrics(result, ok=True):
    """Prometheus exposition for VictoriaMetrics. Timestamp pushed last, only when
    the check itself ran — its staleness is the dead-man."""
    lines = []
    if ok:
        for kind in ("missing", "extra", "changed"):
            lines.append(f'grafana_alert_rules_drift{{kind="{kind}",service="grafana",'
                         f'environment="operations"}} {len(result[kind])}')
    lines.append(f'grafana_alert_rules_drift_check_ok{{service="grafana",environment="operations"}} {int(ok)}')
    if ok:
        lines.append('grafana_alert_rules_drift_last_check_timestamp{service="grafana",'
                     'environment="operations"} ' + str(int(__import__("time").time())))
    return "\n".join(lines) + "\n"


def report(result):
    n = len(result["missing"]) + len(result["extra"]) + len(result["changed"])
    print(f"drift: {n} rule(s) — missing {len(result['missing'])}, extra {len(result['extra'])}, "
          f"changed {len(result['changed'])}")
    for uid in result["missing"]:
        print(f"  missing  {uid}  (in the repo, never loaded)")
    for uid in result["extra"]:
        print(f"  extra    {uid}  (live, not in the repo)")
    for uid, fields in result["changed"].items():
        print(f"  changed  {uid}  ({', '.join(fields)})")
    return n


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True, help="path to rules.yaml")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--live", help="JSON export of /api/v1/provisioning/alert-rules")
    src.add_argument("--grafana", help="Grafana base URL, e.g. http://localhost:3000")
    ap.add_argument("--env", help="file holding GRAFANA_ADMIN_PASSWORD (with --grafana)")
    ap.add_argument("--push", help="VictoriaMetrics import URL for the counts")
    a = ap.parse_args(argv)
    try:
        with open(a.repo) as f:
            repo = repo_rules(f.read())
        if a.live:
            with open(a.live) as f:
                live_list = json.load(f)
        else:
            live_list = _grafana_rules(a.grafana, a.env)
        live = {r["uid"]: r for r in live_list}
    except Exception as ex:  # noqa: BLE001 — any failure is "could not check", loudly
        print(f"drift: could not check: {ex}", file=sys.stderr)
        if a.push:
            _push(a.push, metrics(None, ok=False))
        return 2
    result = compare(repo, live)
    n = report(result)
    if a.push:
        _push(a.push, metrics(result))
    return 1 if n else 0


def _push(url, body):
    try:
        urllib.request.urlopen(urllib.request.Request(url, data=body.encode(), method="POST"), timeout=8)
    except Exception as ex:  # noqa: BLE001
        print(f"drift: push failed: {ex}", file=sys.stderr)


if __name__ == "__main__":
    sys.exit(main())
