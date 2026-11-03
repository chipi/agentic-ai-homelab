"""Replay eval for the assistant-failover gate (2026-11-03), on the GlitchTip issues of that day.

Input (reference-operational/replay-2026-11-03-assistant-failover.json, frozen from the mini, scrubbed):
the 5 `litellm` issues the failover tests of LiteLLM's `assistant` alias made (RFC-0008 phase 5), each
with its latest event. The fleet filed all five as GitHub issues (#133-#137, closed as test noise):
  729/730  the X3 assistant stopped: "Connection error." (connection refused to 100.92.54.65:11435)
  731/732  the X3 assistant hung (SIGSTOP): "Request timed out." (request to 100.92.54.65:11435)
  733      a deliberate key check: assistant-cloud refused (403) — a real misuse, NOT a failover
Controls: reference-operational/replay-2026-10-01.json (its 5 live litellm issues and the 829 signals the
triager had ever disposed) and synthetic variants of 729.

     baseline  sources.to_error_signal + triage.operational_class at BASE_REV (git)
     fix       + sources.attach_backend (GlitchTip reads served from the corpus) + the working tree's gate

Pass:
  1. faithful: the baseline gives all five None (they reached the triager and were filed);
  2. the fix gives 729-732 assistant-failover, and 733 None;
  3. 729 naming another backend, naming the X3 AND another backend, the X3 address in another project,
     and an issue whose event lookup fails: all None, nothing raised;
  4. every control issue and historical signal keeps its baseline class; attach_backend reads events
     for litellm issues only.

  python3 eval_assistant_failover_replay.py      # exit 1 on any failure
"""
import copy
import importlib.util
import json
import os
import subprocess
import sys
import tempfile

os.environ.setdefault("OPENROUTER_API_KEY", "replay-dummy")
os.environ.setdefault("SF_OBSERV_DISABLED", "1")
HERE = os.path.dirname(os.path.abspath(__file__))
CORPUS = os.path.join(HERE, "..", "reference-operational", "replay-2026-11-03-assistant-failover.json")
CONTROLS = os.path.join(HERE, "..", "reference-operational", "replay-2026-10-01.json")
BASE_REV = "e6696ca"   # main before the assistant-failover gate
X3, OTHER = "100.92.54.65", "100.69.49.126"


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _baseline(module):
    src = subprocess.run(["git", "-C", HERE, "show", f"{BASE_REV}:signal-fleet/mvp/{module}.py"],
                         capture_output=True, text=True, check=True).stdout
    tmp = tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, dir=HERE, prefix=f"_{module}_base_")
    tmp.write(src)
    tmp.close()
    try:
        return _load(tmp.name, f"{module}_baseline")
    finally:
        os.unlink(tmp.name)


def main():
    corpus = json.load(open(CORPUS))
    controls = json.load(open(CONTROLS))
    base_tr, base_src = _baseline("triage"), _baseline("sources")
    fix_tr, fix_src = _load(os.path.join(HERE, "triage.py"), "triage_fix"), _load(os.path.join(HERE, "sources.py"), "sources_fix")
    if hasattr(base_src, "attach_backend"):
        print("FAIL: the baseline already has attach_backend — BASE_REV is wrong")
        return 1

    events, reads = {}, []

    def stub_gt(path):          # GlitchTip reads come from the corpus; a replay never calls out
        reads.append(path)
        iid = path.split("/issues/")[1].split("/")[0]
        if iid not in events:
            raise RuntimeError(f"no event in the corpus for issue {iid}")
        return events[iid]
    fix_src._gt = stub_gt

    def run(issue, event=None):
        """(baseline class, fix class) for one issue; event None = the lookup fails."""
        iid = str(issue.get("id"))
        events.pop(iid, None)
        if event is not None:
            events[iid] = event
        b = base_tr.operational_class(base_src.to_error_signal(copy.deepcopy(issue)))
        sig = fix_src.attach_backend(fix_src.to_error_signal(copy.deepcopy(issue)))
        return b, fix_tr.operational_class(sig), sig["raw"].get("_backends")

    fails = []
    want = {"729": "assistant-failover", "730": "assistant-failover", "731": "assistant-failover",
            "732": "assistant-failover", "733": None}
    print("1-2. the 2026-11-03 issues")
    print(f"   {'issue':<6} {'baseline':<10} {'fix':<20} backends in the latest event / title")
    by_id = {}
    for row in corpus["issues"]:
        i, ev = row["issue"], row["latest_event"]
        by_id[str(i["id"])] = (i, ev)
        b, f, be = run(i, ev)
        print(f"   {i['id']:<6} {str(b):<10} {str(f):<20} {be}  {i['title'][:44]}")
        if b is not None:
            fails.append(f"{i['id']}: baseline class {b}, but it was filed (#133-#137) — replay not faithful")
        if f != want[str(i["id"])]:
            fails.append(f"{i['id']}: fix class {f}, want {want[str(i['id'])]}")

    print("\n3. controls built from 729 (the X3 stopped)")
    i729, ev729 = by_id["729"]
    evs = json.dumps(ev729)
    both = copy.deepcopy(ev729)            # a second backend inside the exception entry itself
    exc = next(e for e in both["entries"] if e.get("type") == "exception")
    exc["data"]["values"][0]["value"] = str(exc["data"]["values"][0].get("value")) + f" (then http://{OTHER}:8003/v1)"
    tuple_form = copy.deepcopy(ev729)      # a second backend named only as a refused connection
    exc = next(e for e in tuple_form["entries"] if e.get("type") == "exception")
    exc["data"]["values"][0]["value"] = str(exc["data"]["values"][0].get("value")) + f" [Errno 111] Connect call failed ('{OTHER}', 8003)"
    cases = [
        ("another backend (the DGX vLLM)", i729, json.loads(evs.replace(X3, OTHER).replace("11435", "8003"))),
        ("the X3 and another backend", i729, both),
        ("the X3 and a refused ('ip', port)", i729, tuple_form),
        ("the X3 address, project not litellm", dict(copy.deepcopy(i729), project={"slug": "podcast"}), ev729),
        ("event lookup fails", i729, None),
    ]
    for name, issue, ev in cases:
        try:
            b, f, be = run(issue, ev)
        except Exception as e:
            fails.append(f"control '{name}' raised {e!r}")
            continue
        print(f"   {name:<38} fix {str(f):<20} backends {be}")
        if f is not None:
            fails.append(f"control '{name}' dismissed as {f}")
    if not any(be and len(be) > 1 for _, _, be in [run(cases[1][1], cases[1][2])] if cases[1][2] is not None):
        fails.append("control 'the X3 and another backend' did not put two backends in the event — not a real control")
    # each project check on its own: attach_backend must not read a non-litellm issue's event, and the
    # gate must not dismiss a non-litellm signal even if it carries the X3 as its only backend
    reads.clear()
    _, other_issue, other_ev = next(c for c in cases if c[0] == "the X3 address, project not litellm")
    run(other_issue, other_ev)
    if reads:
        fails.append(f"attach_backend read an event for a non-litellm issue: {reads}")
    other = fix_src.to_error_signal(dict(copy.deepcopy(i729), project={"slug": "podcast"}))
    other["raw"]["_backends"] = [X3 + ":11435"]
    got = fix_tr.operational_class(other)
    print(f"   {'non-litellm signal carrying the X3':<38} fix {str(got):<20} (gate's own project check)")
    if got is not None:
        fails.append(f"gate dismissed a non-litellm signal as {got}")

    print("\n4. invariant: the 2026-10-01 corpus")
    reads.clear()
    changed = []
    for i in controls["litellm_project_issues"]:
        events[str(i.get("id"))] = {"entries": []}          # no event frozen that day: names nothing
        b, f, _ = run(i, {"entries": []})
        if b != f:
            changed.append((i["shortId"], b, f))
    sigs = controls["triaged_signals"]
    for s in sigs:
        sig = {"source": s["source"], "alertname": s["alertname"], "summary": s["alertname"], "labels": {}}
        b, f = base_tr.operational_class(sig), fix_tr.operational_class(fix_src.attach_backend(copy.deepcopy(sig)))
        if b != f:
            changed.append((s["alertname"][:60], b, f))
    non_litellm_reads = [p for p in reads if not any(str(i.get("id")) in p for i in controls["litellm_project_issues"])]
    print(f"   {len(controls['litellm_project_issues'])} litellm issues + {len(sigs)} historical signals; class changed: {len(changed)}")
    for name, b, f in changed:
        print(f"     {b} -> {f}: {name}")
        fails.append(f"control class changed: {name}")
    if non_litellm_reads:
        fails.append(f"attach_backend read events for non-litellm signals: {non_litellm_reads[:3]}")

    print("\n" + ("PASS" if not fails else "FAIL:\n  " + "\n  ".join(fails)))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
