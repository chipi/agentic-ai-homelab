"""Replay eval for two 2026-10-01 fixes, on the LiteLLM errors live in GlitchTip that day.

Input (reference-operational/replay-2026-10-01.json, captured from the mini):
  - the 5 unresolved issues of the recreated `litellm` GlitchTip project (id 19), with
    the full exception value GlitchTip keeps in metadata.value;
  - every distinct (source, alertname) the triager has ever disposed (829) — controls.
And reference-filing/filed-2026-10-01.tsv, the filed-ledger as it stood that day.

1. Ledger collision. The project was recreated under the same slug, so its shortIds
   restarted at LITELLM-1 and matched the deleted project's ledger rows: LITELLM-5 (a
   rate limit) reopened #14 (ProxyModelNotFoundError) at 13:13Z.
     baseline  ledger_lookup on the snapshot as-is
     fix       after filing.retire_glitchtip_project("litellm", "2026-09-30")
   Pass: no live issue matches an old row on the fingerprint dimension; every row that
   is not `glitchtip:LITELLM-<n>` (incl. LITELLM-VPS-*) is byte-identical.

2. Upstream rate limit (homelab #17, operator: not actionable, never ticket).
     baseline  triage.operational_class as committed at BASE_REV
     fix       the working-tree operational_class
   Pass: LITELLM-5 goes None -> upstream-rate-limit; the same error with a limit_source
   that is NOT the shared pool stays None; and the class of all 829 historical signals
   and the other 4 live issues is unchanged.

  python3 eval_glitchtip_litellm_replay.py      # exit 1 on any failure
"""
import copy
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile

os.environ.setdefault("OPENROUTER_API_KEY", "replay-dummy")
os.environ.setdefault("SF_OBSERV_DISABLED", "1")
HERE = os.path.dirname(os.path.abspath(__file__))
CORPUS = os.path.join(HERE, "..", "reference-operational", "replay-2026-10-01.json")
LEDGER = os.path.join(HERE, "..", "reference-filing", "filed-2026-10-01.tsv")
BASE_REV = "12ed430"   # main before these fixes
_TMP = tempfile.mkdtemp(prefix="sf-gt-replay-")
os.environ["SF_FILED_LEDGER"] = os.path.join(_TMP, "filed.tsv")
shutil.copy(LEDGER, os.environ["SF_FILED_LEDGER"])

import filing    # noqa: E402  — reads SF_FILED_LEDGER at import
import sources   # noqa: E402


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _baseline_triage():
    src = subprocess.run(["git", "-C", HERE, "show", f"{BASE_REV}:signal-fleet/mvp/triage.py"],
                         capture_output=True, text=True, check=True).stdout
    tmp = tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, dir=HERE, prefix="_triage_base_")
    tmp.write(src)
    tmp.close()
    try:
        return _load(tmp.name, "triage_baseline")
    finally:
        os.unlink(tmp.name)


def ledger_part(issues):
    fails = []
    before = {i["shortId"]: filing.ledger_lookup(f"glitchtip:{i['shortId']}") for i in issues}
    snapshot = filing._ledger_rows()
    res = filing.retire_glitchtip_project("litellm", "2026-09-30")
    after = {i["shortId"]: filing.ledger_lookup(f"glitchtip:{i['shortId']}") for i in issues}
    print(f"1. ledger collision — retired {res['retired']} of {res['rows']} rows")
    print(f"   {'live issue':<11} {'baseline (today)':<20} fix")
    for i in issues:
        b, a = before[i["shortId"]], after[i["shortId"]]
        bs = f"#{b['issue']} via {b['_dim']}" if b else "no match"
        as_ = f"#{a['issue']} via {a['_dim']}" if a else "no match"
        print(f"   {i['shortId']:<11} {bs:<20} {as_}   {i['title'][:50]}")
        if a and a["_dim"] == "fingerprint":
            fails.append(f"{i['shortId']} still collides with #{a['issue']}")
    for old, new in zip(snapshot, filing._ledger_rows()):
        retired = new["fingerprint"].startswith(filing.RETIRED_PREFIX)
        if retired and not old["fingerprint"].startswith("glitchtip:LITELLM-"):
            fails.append(f"retired a non-LiteLLM row: {old['fingerprint']}")
        if not retired and old != new:
            fails.append(f"changed an unrelated row: {old['fingerprint']}")
        if "LITELLM-VPS-" in old["fingerprint"] and old != new:
            fails.append(f"touched the separate litellm-vps project: {old['fingerprint']}")
    return fails


def rate_limit_part(issues, signals):
    fails = []
    base, fix = _baseline_triage(), _load(os.path.join(HERE, "triage.py"), "triage_fix")
    print("\n2. upstream rate limit")
    print(f"   {'live issue':<11} {'baseline':<10} fix")
    for i in issues:
        sig = sources.to_error_signal(i)
        b, f = base.operational_class(sig), fix.operational_class(sig)
        print(f"   {i['shortId']:<11} {str(b):<10} {f}   {i['title'][:50]}")
        shared_pool = "upstream_provider_shared_pool" in i["metadata"].get("value", "")
        if shared_pool and f != "upstream-rate-limit":
            fails.append(f"{i['shortId']}: shared-pool 429 not classified ({f})")
        if not shared_pool and f != b:
            fails.append(f"{i['shortId']}: class changed {b} -> {f}")
        if shared_pool:
            own = copy.deepcopy(i)
            own["metadata"]["value"] = own["metadata"]["value"].replace(
                "upstream_provider_shared_pool", "key").replace("temporarily rate-limited upstream", "rate-limited")
            got = fix.operational_class(sources.to_error_signal(own))
            print(f"   {'  (control)':<11} {'':<10} {got}   same 429, limit_source=key (our quota)")
            if got is not None:
                fails.append(f"own-key 429 dismissed ({got}) — must reach the triager")
    changed = []
    for s in signals:
        sig = {"source": s["source"], "alertname": s["alertname"], "summary": s["alertname"], "labels": {}}
        b, f = base.operational_class(sig), fix.operational_class(sig)
        if b != f:
            changed.append((s["alertname"][:70], b, f))
    print(f"   historical signals whose class changed: {len(changed)} of {len(signals)}")
    for name, b, f in changed:
        print(f"     {b} -> {f}: {name}")
        fails.append(f"historical class changed: {name}")
    return fails


def main():
    corpus = json.load(open(CORPUS))
    issues = corpus["litellm_project_issues"]
    fails = ledger_part(issues) + rate_limit_part(issues, corpus["triaged_signals"])
    shutil.rmtree(_TMP, ignore_errors=True)
    print("\n" + ("PASS" if not fails else "FAIL:\n  " + "\n  ".join(fails)))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
