"""Routing replay for alert labels (2026-09-30): where does each Grafana issue land?

filing.repo_for routes a Grafana signal by its `instance` label (prod-podcast ->
chipi/podcast_scraper; anything else -> the homelab ops repo). Rules whose query
aggregates the host away carried no instance, so prod-app symptoms (digest
scheduler, pipeline, enrichment, delivery cadences) landed in the homelab repo.

Operator decision, 2026-09-30: prod-APP symptoms go to podcast_scraper; "a host or
its telemetry went dark" stays in homelab, next to the observability stack. The
rules now carry that as labels: prod-app rules get instance=prod-podcast; the dark
rules get host/service/environment but no instance.

Replay over every Grafana filing in reference-filing/replay-2026-09-30.json:
  baseline  repo_for(signal without the new labels) must equal where the issue
            actually landed — the check that the replay is faithful;
  fix       repo_for(signal + the rule's labels from rules.yaml): only prod-app
            rules may change repo, and each must move to podcast_scraper.

  python3 eval_routing_replay.py      # exit 1 on an unfaithful baseline or a wrong move
"""
import json
import os
import sys

import filing

HERE = os.path.dirname(__file__)
CORPUS = os.path.join(HERE, "..", "reference-filing", "replay-2026-09-30.json")
RULES = os.path.join(HERE, "..", "..", "infra", "observability", "backend", "grafana",
                     "provisioning", "alerting", "rules.yaml")
PROD_REPO = "chipi/podcast_scraper"
# Rules whose QUERY result keeps `instance` (by (instance, ...) or no aggregation) —
# their routing never depended on rule labels, and this change does not touch them.
# The ledger does not store which instance fired, so the replay reads it back from
# where the issue landed; that makes their baseline faithful by construction and
# leaves the real question — did the new rule labels move them? — intact.
INSTANCE_FROM_QUERY = {"infra-target-down", "infra-disk-low", "infra-disk-crit", "infra-mem-low",
                       "infra-mem-crit", "infra-oom-kill", "dgx-memfree-crit", "dgx-gpu-mem-overcommit",
                       "dgx-gpu-metrics-stale", "mini-mem-high", "mini-cpu-temp-high", "mini-cpu-temp-crit"}


def _rules_by_title():
    try:
        import yaml
        doc = yaml.safe_load(open(RULES))
    except ImportError:                      # the mini's python3: parse with system Ruby
        import subprocess
        out = subprocess.run(["/usr/bin/ruby", "-ryaml", "-rjson", "-e",
                              "puts YAML.safe_load(STDIN.read).to_json"],
                             input=open(RULES).read(), capture_output=True, text=True, check=True).stdout
        doc = json.loads(out)
    return {r["title"]: r for g in doc["groups"] for r in g["rules"]}


def main():
    corpus = json.load(open(CORPUS))
    rules = _rules_by_title()
    first = {}
    for r in corpus["rows"]:
        k = (r["repo"], r["issue"])
        if r["fingerprint"].startswith("grafana:") and (k not in first or r["filed_at"] < first[k]["filed_at"]):
            first[k] = r
    unfaithful, wrong, moved, unmatched = [], [], [], 0
    for (repo, issue), r in sorted(first.items(), key=lambda kv: kv[1]["filed_at"]):
        rule = rules.get(r["alertname"])
        if not rule:
            unmatched += 1
            continue
        sig = {"fingerprint": r["fingerprint"], "source": "grafana", "alertname": r["alertname"]}
        query_labels = {}
        if rule["uid"] in INSTANCE_FROM_QUERY:
            query_labels = {"instance": "prod-podcast" if repo == PROD_REPO else "homelab"}
        before = filing.repo_for(dict(sig, labels=query_labels))
        after = filing.repo_for(dict(sig, labels=dict(rule.get("labels") or {}) | query_labels))
        if before != repo:
            unfaithful.append((repo, issue, before))
        if after != before:
            ok = after == PROD_REPO and rule["labels"].get("instance") == "prod-podcast"
            moved.append((repo, issue, rule["uid"], after, ok))
            if not ok:
                wrong.append(issue)
    print(f"Routing replay — {len(first)} Grafana issues in the ledger "
          f"({unmatched} from rules no longer in rules.yaml, skipped)\n")
    print(f"  baseline reproduces history: {len(first) - unmatched - len(unfaithful)}/{len(first) - unmatched}")
    for repo, issue, b in unfaithful:
        print(f"    ✗ {repo}#{issue}: replay says {b}")
    print(f"  issues that route differently with the new labels: {len(moved)}")
    for repo, issue, uid, after, ok in moved:
        print(f"    {'✓' if ok else '✗'} {repo.split('/')[1]}#{issue} -> {after.split('/')[1]}   ({uid})")
    return 1 if (unfaithful or wrong) else 0


if __name__ == "__main__":
    sys.exit(main())
