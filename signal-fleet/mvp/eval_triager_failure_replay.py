"""Replay eval for triager-failure handling (#11) — the 126 real failures, old vs new code.

Input: every escalation in dispositions.tsv whose reason was "triager call failed"
(2026-07-25 .. 2026-09-30), with the error each one actually hit, and how many GitHub
issues those escalations filed (reference-triager-failures/replay-2026-10-01.json).

Each failure is replayed through triage.triage() with the triager call raising that
exact error:
  baseline  triage.py as committed BEFORE #11 (loaded from git, BASE_REV), i.e. the
            code running today: 401/403 fail closed; everything else escalated per signal
  fix       the working-tree triage.py: 402 fails closed too; transient errors defer
Outcome per failure: "aggregate" (TriagerDown — one fleet-wide issue), "deferred"
(retried next cycle, no issue), or "per-signal" (an escalation issue for this signal).

  python3 eval_triager_failure_replay.py     # exit 1 if the fix still escalates per signal
"""
import http.client
import importlib.util
import json
import os
import socket
import subprocess
import sys
import tempfile
import urllib.error
from collections import Counter

os.environ.setdefault("OPENROUTER_API_KEY", "replay-dummy")
os.environ.setdefault("SF_OBSERV_DISABLED", "1")

HERE = os.path.dirname(os.path.abspath(__file__))
CORPUS = os.path.join(HERE, "..", "reference-triager-failures", "replay-2026-10-01.json")
BASE_REV = "e992391"   # main just before #11


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _baseline_module():
    src = subprocess.run(["git", "-C", HERE, "show", f"{BASE_REV}:signal-fleet/mvp/triage.py"],
                         capture_output=True, text=True, check=True).stdout
    tmp = tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, dir=HERE, prefix="_triage_base_")
    tmp.write(src)
    tmp.close()
    try:
        return _load(tmp.name, "triage_baseline")
    finally:
        os.unlink(tmp.name)


def _error(cls):
    if cls.startswith("HTTP "):
        code = int(cls.split()[1])
        return urllib.error.HTTPError("https://triager.example", code, "replayed", {}, None)
    if cls == "timeout":
        return socket.timeout("timed out")
    return http.client.RemoteDisconnected("Remote end closed connection without response")


SIGNAL = {"fingerprint": "grafana:replay", "occurrence_id": "replay", "source": "grafana",
          "alertname": "replayed signal", "labels": {}, "annotations": {}}


def outcome(mod, cls):
    def fake_post(*a, **k):
        raise _error(cls)
    mod.post_json = fake_post
    try:
        d = mod.triage(dict(SIGNAL))
    except mod.TriagerDown:
        return "aggregate"
    except Exception as e:  # noqa: BLE001
        if type(e).__name__ == "TriageDeferred":
            return "deferred"
        return f"crash: {type(e).__name__}"
    return "per-signal" if d.get("disposition") == "escalate" else d.get("disposition", "?")


def main():
    corpus = json.load(open(CORPUS))
    base, fix = _baseline_module(), _load(os.path.join(HERE, "triage.py"), "triage_fix")
    rows = Counter()
    for f in corpus["failures"]:
        rows[(f["cls"], outcome(base, f["cls"]), outcome(fix, f["cls"]))] += 1
    issues = corpus["escalation_issues_filed"]
    print(f"Triager-failure replay — {len(corpus['failures'])} real failures "
          f"({corpus['window']}), {sum(issues.values())} escalation issues they filed\n")
    print(f"  {'error':<10} {'n':>4}  {'baseline (today)':<17} {'fix':<10} issues filed then")
    per_signal_fix = 0
    for (cls, b, f), n in sorted(rows.items()):
        per_signal_fix += n if f == "per-signal" else 0
        print(f"  {cls:<10} {n:>4}  {b:<17} {f:<10} {issues.get(cls, 0)}")
    base_ps = sum(n for (c, b, f), n in rows.items() if b == "per-signal")
    print(f"\n  per-signal escalations — baseline: {base_ps}, fix: {per_signal_fix}")
    return 1 if per_signal_fix else 0


if __name__ == "__main__":
    sys.exit(main())
