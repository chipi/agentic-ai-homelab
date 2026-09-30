"""Replay eval for the "looks resolved" nudge (#10) against real ground truth.

Ground truth: the 2026-09-30 triage of every open issue in agentic-ai-homelab, done
with evidence per issue (alert state, metrics, logs), BEFORE any issue was closed.
It closed 30 as resolved and kept 14 as real. Of those, the fleet filed 28 resolved
and 5 real — the population the nudge acts on (it never touches hand-filed issues).

The replay evaluates stale.is_stale() for each of them as the world stood at
2026-09-30T08:00Z: the fleet's ledgers up to then, which Grafana alerts were firing
at that moment, and which human comments existed.

  baseline  no nudge exists: every resolved issue stays open and silent (today)
  fix       nudge resolved ones; must not nudge a real one — or, where it does,
            the case must be a named, known blind spot

  python3 eval_stale_replay.py                    # report; exit 1 on an unexplained miss
  python3 eval_stale_replay.py --build FILED_TSV DISPOSITIONS_TSV ANNOTATIONS_JSON INPUTS_JSON
"""
import csv
import json
import os
import sys

import filing
import stale

CORPUS = os.path.join(os.path.dirname(__file__), "..", "reference-stale", "replay-2026-09-30.json")
REPO = "chipi/agentic-ai-homelab"

# Known blind spots: real issues the nudge WILL flag, and why. Kept visible, not hidden.
KNOWN_BLIND = {
    17: "LiteLLM 429s kept happening (2,105 log lines to 09-29) but never reached the fleet: "
        "LiteLLM's GlitchTip project did not exist until 2026-09-30",
    28: "same broken path: the MISSING-key 401s (102 since 09-24) never reached the fleet",
}


def build(filed_tsv, dispositions_tsv, annotations_json, inputs_json, out=CORPUS):
    with open(inputs_json) as f:
        inp = json.load(f)
    T = inp["T"]
    ledger = [r for r in csv.DictReader(open(filed_tsv), delimiter="\t") if r["repo"] == REPO]
    disp = list(csv.DictReader(open(dispositions_tsv), delimiter="\t"))
    names = {}
    for d in disp:
        names.setdefault(d["fingerprint"], (d["source"], d["alertname"]))
    want_fp, want_ak = set(), set()
    for n in inp["candidates"]:
        fps, aks = stale.issue_signals(ledger, REPO, n, names)
        want_fp |= fps
        want_ak |= aks
    occ = [(d["ts"], d["fingerprint"], d["source"], d["alertname"]) for d in disp
           if d["ts"] <= T and (d["fingerprint"] in want_fp
                                or filing.alert_key(REPO, d["source"], d["alertname"]) in want_ak)]
    # Grafana alerts firing at T: open Alerting interval in the state history
    ann = sorted(json.load(open(annotations_json)), key=lambda x: x["time"])
    t_ms = int(stale._ts(T).timestamp() * 1000)
    state = {}
    for a in ann:
        if a["time"] <= t_ms:
            state[a["alertName"]] = a["newState"]
    firing = sorted(n for n, s in state.items() if s.startswith("Alerting"))
    os.makedirs(os.path.dirname(out), exist_ok=True)
    json.dump({"built_from": "filed.tsv + dispositions.tsv (mini), Grafana alert state history, "
                             "GitHub comments; ground truth = 2026-09-30 evidence triage",
               "T": T, "ledger": [{k: r.get(k, "") for k in ("fingerprint", "repo", "issue")} for r in ledger],
               "names": {fp: list(v) for fp, v in names.items() if fp in want_fp},
               "occurrences": occ, "firing_at_T": firing,
               "comments": inp["comments"], "resolved": inp["resolved"], "real": inp["real"],
               "candidates": inp["candidates"]}, open(out, "w"), indent=1, ensure_ascii=False)
    print(f"corpus: {len(inp['candidates'])} issues, {len(occ)} occurrences, "
          f"{len(firing)} alerts firing at T -> {out}")


def run(corpus):
    T = stale._ts(corpus["T"])
    names = {fp: tuple(v) for fp, v in corpus["names"].items()}
    resolved, real = set(corpus["resolved"]), set(corpus["real"])
    rows, tp, fn, fp_known, fp_unexplained = [], 0, 0, 0, 0
    for n in corpus["candidates"]:
        fps, aks = stale.issue_signals(corpus["ledger"], REPO, n, names)
        seen = stale.last_seen(fps, aks, REPO, corpus["occurrences"], set(corpus["firing_at_T"]), T)
        human = [c["t"] for c in corpus["comments"].get(str(n), []) if not c["fleet"]]
        nudge = stale.is_stale(seen, human, T)
        truth = "resolved" if n in resolved else "real"
        if truth == "resolved":
            verdict = "✓ nudged" if nudge else "✗ missed"
            tp += nudge
            fn += not nudge
        else:
            if not nudge:
                verdict = "✓ left alone"
            elif n in KNOWN_BLIND:
                verdict = "! nudged (known blind spot)"
                fp_known += 1
            else:
                verdict = "✗ WRONGLY nudged"
                fp_unexplained += 1
        age = f"{(T - seen).days}d" if seen else "never"
        rows.append((n, truth, age, "firing" if seen == T else "", verdict))
    print("Stale-nudge replay — as of 2026-09-30T08:00Z, before the triage closed anything")
    print("baseline (today): no nudge — 28 resolved fleet issues sat open and silent\n")
    print(f"  {'issue':>6}  {'truth':<9} {'quiet':>6} {'':<7} fix")
    for n, truth, age, firing, verdict in sorted(rows, key=lambda r: (r[1], r[0])):
        print(f"  #{n:<5}  {truth:<9} {age:>6} {firing:<7} {verdict}")
    print(f"\n  resolved nudged {tp}/{tp + fn}; real left alone {len(real & set(corpus['candidates'])) - fp_known - fp_unexplained}"
          f"/{len(real & set(corpus['candidates']))}; known blind spots {fp_known}; unexplained wrong nudges {fp_unexplained}")
    for n, why in KNOWN_BLIND.items():
        print(f"  blind spot #{n}: {why}")
    return fn, fp_unexplained


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--build":
        build(*sys.argv[2:6])
        raise SystemExit(0)
    with open(CORPUS) as f:
        c = json.load(f)
    missed, wrong = run(c)
    raise SystemExit(1 if wrong else 0)
