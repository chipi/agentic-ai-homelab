"""Replay eval for "needs you" counting open escalations only (operator, 2026-11-04: "needs me" is
something open, not closed).

Input (reference-inbox-open/corpus-2026-11-04.json, frozen from the mini): the 9 escalate rows of the 7
days before 2026-11-04 12:4x UTC (age, fingerprint, disposition only), the filed-ledger rows for their
fingerprints (6: three escalations were never filed), the states of those issues on GitHub (#86, #127,
#132 open; #133, #134, #137 closed: the 2026-11-03 failover tests), and the fleet's
signal_fleet_escalations_7d at freeze time (9).

     baseline  inbox._recent_escalations at BASE_REV (git)
     fix       the working tree's: an escalation whose newest filed issue is closed is not counted

Pass:
  1. faithful: the baseline counts all 9, the fleet's recorded metric;
  2. the fix counts 6: it drops exactly the escalations whose filed issue is closed, keeps the open
     ones and the three never filed;
  3. nothing else changes: every row it keeps is the baseline's row, unchanged;
  4. GitHub unreadable (state_of raises): all 9 counted, nothing raised.

  python3 eval_inbox_open_replay.py      # exit 1 on any failure
"""
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
CORPUS = os.path.join(HERE, "..", "reference-inbox-open", "corpus-2026-11-04.json")
BASE_REV = "f9b0d50"   # main before the open-only count
FILED_COLS = ["fingerprint", "repo", "issue", "group_key", "filed_at", "last_comment_day", "norm_key", "alert_key"]
DISP_COLS = ["ts", "fingerprint", "alertname", "disposition", "reason"]

corpus = json.load(open(CORPUS))
now = datetime.now(timezone.utc).timestamp()
tmp = tempfile.mkdtemp(prefix="inbox_open_")
disp, filed = os.path.join(tmp, "dispositions.tsv"), os.path.join(tmp, "filed.tsv")
with open(disp, "w") as f:
    f.write("\t".join(DISP_COLS) + "\n")
    for e in corpus["escalations"]:
        ts = datetime.fromtimestamp(now - e["age_s"], timezone.utc).isoformat()
        f.write("\t".join([ts, e["fingerprint"], "alert " + e["fingerprint"], e["disposition"], "replay"]) + "\n")
with open(filed, "w") as f:
    f.write("\t".join(FILED_COLS) + "\n")
    for r in corpus["filed"]:
        f.write("\t".join(str(r.get(c, "")) for c in FILED_COLS) + "\n")
os.environ.update(SF_DISPOSITIONS=disp, SF_FILED_LEDGER=filed, SF_QUEUE_DIR=tmp, SF_INBOX_SEEN=os.path.join(tmp, "seen"),
                  OPENROUTER_API_KEY=os.environ.get("OPENROUTER_API_KEY", "replay-dummy"), SF_OBSERV_DISABLED="1")
sys.path.insert(0, HERE)


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _baseline():
    src = subprocess.run(["git", "-C", HERE, "show", f"{BASE_REV}:signal-fleet/mvp/inbox.py"],
                         capture_output=True, text=True, check=True).stdout
    t = tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, dir=HERE, prefix="_inbox_base_")
    t.write(src)
    t.close()
    try:
        return _load(t.name, "inbox_baseline")
    finally:
        os.unlink(t.name)


fails = []
def check(name, ok, got=None):
    print(("ok   " if ok else "FAIL ") + name + ("" if ok else f"  (got {got})"))
    if not ok:
        fails.append(name)


base = _baseline()
fix = _load(os.path.join(HERE, "inbox.py"), "inbox_fix")
states = corpus["issue_states"]
state_of = lambda repo, n: {"state": states[f"{repo}#{n}"]}
b = base._recent_escalations()
check("faithful: the baseline counts the fleet's recorded metric", len(b) == corpus["fleet_metric_escalations_7d"] == 9, len(b))
check("the baseline has no open-only filter (BASE_REV is right)", "state_of" not in base._recent_escalations.__code__.co_varnames)

newest = {}
for r in corpus["filed"]:
    if r["fingerprint"] not in newest or r["filed_at"] >= newest[r["fingerprint"]]["filed_at"]:
        newest[r["fingerprint"]] = r
closed_fps = {fp for fp, r in newest.items() if states[f'{r["repo"]}#{r["issue"]}'] == "closed"}
x = fix._recent_escalations(state_of=state_of)
check("the fix drops exactly the escalations whose filed issue is closed",
      sorted(e["fingerprint"] for e in b if e["fingerprint"] not in closed_fps) == sorted(e["fingerprint"] for e in x) and len(x) == 6, len(x))
check("the never-filed escalations are kept", all(any(e["fingerprint"] == u["fingerprint"] for e in x)
                                                  for u in corpus["escalations"] if u["fingerprint"] not in newest))
check("nothing else changes: every kept row is the baseline's row", all(e in b for e in x))

def boom(repo, n):
    raise RuntimeError("github down")
y = fix._recent_escalations(state_of=boom)
check("GitHub unreadable: all 9 counted, nothing raised", len(y) == 9, len(y))

print(f"\nbaseline {len(b)} | fix {len(x)} | unreadable {len(y)}")
print("REPLAY FAIL (%d)" % len(fails) if fails else "REPLAY PASS")
sys.exit(1 if fails else 0)
