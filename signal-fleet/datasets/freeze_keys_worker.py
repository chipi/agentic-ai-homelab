#!/usr/bin/env python3
"""The keys filing derives for signals, computed by one version of the fleet's code (freeze_filing.py runs one of
these per deployed version). Reads JSONL {"i", "signal", "title"} on stdin, writes {"i", "keys"} on stdout.

    python3 freeze_keys_worker.py CODE_DIR    # CODE_DIR holds that version's signal-fleet/mvp

A separate process per version, so each imports its own `filing` (and its own config, scrub, ...). A key function
that version does not have gives "" (that version could not match on it)."""
import inspect
import json
import os
import sys

sys.path.insert(0, os.path.join(sys.argv[1], "signal-fleet", "mvp"))
os.environ.setdefault("SF_OBSERV_DISABLED", "1")
import filing  # noqa: E402


def call(name, *args):
    f = getattr(filing, name, None)
    if f is None:
        return ""
    # an older version may take fewer parameters (group_key_for gained `project`): pass what it declares
    return f(*args[:len(inspect.signature(f).parameters)]) or ""


for line in sys.stdin:
    x = json.loads(line)
    s, title = x["signal"], x.get("title") or ""
    repo = filing.repo_for(s) or ""
    keys = {"repo": repo,
            "group_key": call("group_key_for", s.get("alertname", ""), title, (s.get("labels") or {}).get("project", "")),
            "norm_key": call("normalized_key", s),
            "alert_key": call("alert_key", repo, s.get("source", ""), s.get("alertname", "")) if repo else ""}
    print(json.dumps({"i": x["i"], "keys": keys}), flush=True)
