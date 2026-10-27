"""Replay eval: OOM signals per container, and the edge-5xx dismiss guard (2026-10-27).

The misses (prod-podcast, from the live ledger):
- "Kernel OOM killer fired" is one alert per host. evals-inspector was OOM-killed ~337
  times from 2026-10-26 07:38, so the alert fired continuously from 07:39:40 and the fleet
  saw ONE occurrence. player-api's kills (10-26 13:46:07, 13:46:31; 10-27 07:13:37) left
  no ledger row at all.
- The edge-5xx burst of 2026-10-26 13:46:30 (closelistening.app, 11 5xx: player-api's
  kills) was dismissed at 13:53, gate "d:passed", on probes run after the api restarted.

Input (reference-oom-edge/corpus-2026-10-27.json, frozen from the mini):
  every kernel "oom-kill:" line on prod-podcast 2026-10-19 .. 10-27 (342), each docker
  cgroup id -> container name (cadvisor), every container start in the window (90), and
  every "Edge 5xx burst" firing (5).

Part A feeds 10-min fleet cycles through the REAL run_grafana of
  baseline  orchestrator.py at BASE_REV (one signal per alert)
  fix       the working tree (sources.to_signals: one signal per killed container)
with the alert's firing state derived from the kill lines (the rule: kills in the last
15 min), the triager stubbed to "file", and each run on its own temp ledger.
Part B feeds each edge firing, with the triager's recorded "dismiss" and a corroborating
probe, through baseline and fix triage._gate.

Pass:
  A  baseline is faithful: it files at the firings the ledger shows (10-19 06:2x file,
     10-19 08:2x recurrence, 10-26 07:3x file) and writes nothing for player-api after;
  A  fix writes a row for every player-api kill episode (10-19 06:19, 08:28; 10-26 13:46;
     10-27 07:13) and exactly ONE for the evals-inspector loop (no row per cycle);
  A  invariant: a non-OOM alert yields the identical signal in baseline and fix;
  B  baseline lets all 5 dismisses through (the bug);
  B  fix escalates every burst with a player-api kill or a container start around it,
     naming the container, and passes a burst with neither.
The trace for Part B is rebuilt from the recorded reason ("metric probe shows no 5xx");
the raw probe results of that triage were not stored.

  python3 eval_oom_edge_replay.py      # exit 1 on any failure
"""
import calendar
import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import time

os.environ.setdefault("OPENROUTER_API_KEY", "replay-dummy")
os.environ.setdefault("SF_OBSERV_DISABLED", "1")
_FILED = tempfile.NamedTemporaryFile("w", suffix=".tsv", delete=False)
_FILED.close()
os.environ["SF_FILED_LEDGER"] = _FILED.name
HERE = os.path.dirname(os.path.abspath(__file__))
CORPUS = os.path.join(HERE, "..", "reference-oom-edge", "corpus-2026-10-27.json")
BASE_REV = "2e41270"   # main before this fix
FMT = "%Y-%m-%dT%H:%M:%SZ"

import actions   # noqa: E402
import config    # noqa: E402
import guards    # noqa: E402
import observ    # noqa: E402
import sources   # noqa: E402
import triage    # noqa: E402

C = json.load(open(CORPUS))
INST = C["instance"]


def ts(s):
    return calendar.timegm(time.strptime(s[:19], "%Y-%m-%dT%H:%M:%S"))


def iso(t):
    return time.strftime(FMT, time.gmtime(t))


class Frozen:
    """guards' data interface served from the corpus."""

    def oom_kills(self, instance, start, end):
        lo, hi = ts(start), ts(end)
        return [k for k in C["oom_kill_lines"] if lo <= ts(k["t"]) <= hi]

    def container_name(self, instance, cid):
        return C["container_ids"].get(cid)

    def container_starts(self, instance, start, end):
        lo, hi = ts(start), ts(end)
        return [s for s in C["container_starts"] if lo <= ts(s["start"]) <= hi]


def _baseline(name):
    src = subprocess.run(["git", "-C", HERE, "show", f"{BASE_REV}:signal-fleet/mvp/{name}.py"],
                         capture_output=True, text=True, check=True).stdout
    tmp = tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, dir=HERE, prefix=f"_{name}_base_")
    tmp.write(src)
    tmp.close()
    try:
        spec = importlib.util.spec_from_file_location(f"{name}_baseline", tmp.name)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    finally:
        os.unlink(tmp.name)


def oom_alert_at(now):
    """The rule (increase(oom_kill[15m]) > 0, for 0s): firing while a kill is within 15 min;
    startsAt is the first evaluation of the run (Grafana evaluates every 20 s here)."""
    kt = sorted(ts(k["t"]) for k in C["oom_kill_lines"] if ts(k["t"]) <= now)
    if not kt or now - kt[-1] > 900:
        return None
    i = len(kt) - 1
    while i > 0 and kt[i] - kt[i - 1] <= 900:
        i -= 1
    return {"fingerprint": "779e5ff58ed1e245", "startsAt": iso(kt[i] - kt[i] % 20 + 20),
            "status": {"state": "active"},
            "labels": {"alertname": guards.OOM_ALERT, "instance": INST, "severity": "critical", "kind": "infra"},
            "annotations": {"summary": f"OOM kill(s) on {INST} in the last 15m"}}


def part_a(mod):
    ledger = tempfile.NamedTemporaryFile("w", suffix=".tsv", delete=False)
    ledger.close()
    os.unlink(ledger.name)
    clock = {"now": 0}
    orig = (config.LEDGER, actions._now, actions.act, sources.firing_alerts, guards.Live,
            observ.push_disposition_metric, sources.time)
    config.LEDGER = ledger.name
    actions._now = lambda: iso(clock["now"]).replace("Z", "+00:00")
    actions.act = lambda sig, disp, dry_run=True: actions.ledger_append(sig, disp)
    observ.push_disposition_metric = lambda *a, **k: None
    guards.Live = Frozen
    sources.time = type("T", (), {"time": staticmethod(lambda: clock["now"]),
                                  "strftime": staticmethod(time.strftime), "gmtime": staticmethod(time.gmtime)})
    mod._hours_since = lambda t: (clock["now"] - ts(t)) / 3600
    mod._triage_or_defer = lambda sig: {"disposition": "file", "_meta": {}}
    out = sys.stdout
    try:
        sys.stdout = io.StringIO()
        t = ts("2026-10-19T06:00:00Z")
        while t <= ts("2026-10-27T11:30:00Z"):
            clock["now"] = t
            a = oom_alert_at(t)
            sources.firing_alerts = lambda a=a: [a] if a else []
            mod.run_grafana(limit=5, dry_run=True)
            t += 600
    finally:
        sys.stdout = out
        (config.LEDGER, actions._now, actions.act, sources.firing_alerts, guards.Live,
         observ.push_disposition_metric, sources.time) = orig
    rows = []
    with open(ledger.name) as f:
        for line in f:
            p = line.rstrip("\n").split("\t")
            if p[0] == "ts":   # the ledger's header row
                continue
            rows.append({"ts": p[0][:16], "occ": p[1], "fp": p[2], "disp": p[5]})
    os.unlink(ledger.name)
    return rows


def part_b(gate_fn, with_data):
    res = {}
    for at in C["edge_5xx_firings"]:
        sig = {"alertname": "Edge 5xx burst on a prod vhost (>=10 in 5m)", "startsAt": at,
               "labels": {"host": "closelistening.app"}}
        d = {"disposition": "dismiss", "reason": "probes show no ongoing errors",
             "dismissal_evidence": "metric probe: no 5xx in the last 5m"}
        # "metric probe shows no 5xx activity": a 5xx-rate series reading 0, which _usable
        # accepts (the recorded gate for 2026-10-26 13:46:30 was "d:passed")
        trace = [{"probe": "metric", "result": {"status": "success", "data": {"resultType": "vector",
                  "result": [{"metric": {}, "value": [ts(at) + 420, "0"]}]}}}]
        kw = {"edge_data": Frozen()} if with_data else {}
        d, g = gate_fn(d, sig, trace, **kw)
        res[at] = (d["disposition"], g, d.get("reason", "")[:120])
    return res


def main():
    fails = []

    def check(ok, what):
        print(("  PASS " if ok else "  FAIL ") + what)
        if not ok:
            fails.append(what)

    if not C["oom_kill_lines"] or not C["edge_5xx_firings"]:
        print("empty corpus"); return 1
    base_orch, base_triage = _baseline("orchestrator"), _baseline("triage")
    import orchestrator as fix_orch
    print("== Part A: OOM signals")
    b, f = part_a(base_orch), part_a(fix_orch)
    for name, rows in (("baseline", b), ("fix", f)):
        print(f"  {name}: {len(rows)} rows")
        for r in rows:
            print(f"    {r['ts']}  {r['disp']:10s}  {r['occ']}")
    bdays = [(r["ts"][:13], r["disp"]) for r in b]
    check(len(b) == 3 and [d for _, d in bdays] == ["file", "recurrence", "file"]
          and bdays[0][0] == "2026-10-19T06" and bdays[1][0] == "2026-10-19T08" and bdays[2][0] == "2026-10-26T07",
          "baseline faithful: file 10-19 06h, recurrence 10-19 08h, file 10-26 07h, nothing else")
    pa = [r for r in f if r["fp"].endswith(":oom:player-api-1")]
    ev = [r for r in f if r["fp"].endswith(":oom:evals-inspector")]
    check([r["ts"][:13] for r in pa] == ["2026-10-19T06", "2026-10-19T08", "2026-10-26T13", "2026-10-27T07"],
          f"fix: a row per player-api kill episode (got {[r['ts'][:13] for r in pa]})")
    check(len(ev) == 1 and ev[0]["disp"] == "file", f"fix: exactly one row for the evals-inspector loop (got {len(ev)})")
    check(all(":oom:" in r["fp"] for r in f), "fix: every OOM row names a container")
    other = {"fingerprint": "abc", "startsAt": "2026-10-26T13:46:30Z", "status": {"state": "active"},
             "labels": {"alertname": "Edge 5xx burst on a prod vhost (>=10 in 5m)", "host": "x"}, "annotations": {}}
    check(sources.to_signals(other, data=Frozen()) == [sources.to_signal(other)],
          "invariant: a non-OOM alert yields the identical single signal")
    print("== Part B: edge-5xx dismiss")
    bb, fb = part_b(base_triage._gate, False), part_b(triage._gate, True)
    for at in C["edge_5xx_firings"]:
        print(f"    {at}  baseline {bb[at][0]:8s} {bb[at][1]:24s} | fix {fb[at][0]:8s} {fb[at][1]}  {fb[at][2][:70]}")
    check(all(v[0] == "dismiss" for v in bb.values()), "baseline lets every dismiss through (the bug)")
    # expected straight from the corpus (not through guards): a kill line or a container
    # start within [burst - 10 min, burst + 5 min]
    want = {at: any(ts(at) - 600 <= ts(x) <= ts(at) + 300
                    for x in [k["t"] for k in C["oom_kill_lines"]] + [s["start"] for s in C["container_starts"]])
            for at in C["edge_5xx_firings"]}
    check(all((fb[at][0] == "escalate") == want[at] for at in want),
          f"fix escalates exactly the bursts with a restart/OOM nearby {sorted(k for k, v in want.items() if v)}")
    check(fb["2026-10-26T13:46:30Z"][0] == "escalate" and "player-api-1" in fb["2026-10-26T13:46:30Z"][2],
          "the 2026-10-26 13:46:30 burst escalates, naming player-api-1")
    print("\nOOM-EDGE REPLAY: " + ("PASS" if not fails else f"FAIL ({len(fails)})"))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
