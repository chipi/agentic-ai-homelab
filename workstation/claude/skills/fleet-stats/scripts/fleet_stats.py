#!/usr/bin/env python3
"""fleet-stats — per-subagent invocation + token/cost breakdown from a Claude Code
transcript. Proves the cost-spread of a model-tiered subagent fleet, fully local
(no Grafana / OTEL needed).

Usage: fleet_stats.py [transcript.jsonl]   # defaults to the latest for this cwd
"""
import json, sys, glob, os
from collections import defaultdict

# Approximate output-blended $/Mtok — UPDATE to current pricing (see the claude-api
# skill). Tokens-per-model is the real signal; dollars are a rough guide.
RATES = {"opus": 15.0, "sonnet": 3.0, "haiku": 0.8, "fable": 3.0}


def find_transcript():
    if len(sys.argv) > 1:
        return sys.argv[1]
    base = os.path.basename(os.getcwd().rstrip("/"))
    for pat in (f"~/.claude/projects/*{base}*/*.jsonl", "~/.claude/projects/*/*.jsonl"):
        cands = glob.glob(os.path.expanduser(pat))
        if cands:
            return max(cands, key=os.path.getmtime)
    return None


def tier(m):
    m = (m or "").lower()
    for t in ("opus", "sonnet", "haiku", "fable"):
        if t in m:
            return t
    return m or "?"


def main():
    path = find_transcript()
    if not path:
        print("fleet-stats: no transcript found")
        return
    print(f"fleet-stats — {os.path.basename(path)}\n")

    calls = []
    for line in open(path):
        try:
            o = json.loads(line)
        except Exception:
            continue
        tur = o.get("toolUseResult")
        if isinstance(tur, dict) and tur.get("agentType"):
            calls.append({
                "agent": tur["agentType"],
                "model": tier(tur.get("resolvedModel")),
                "tok": tur.get("totalTokens", 0) or 0,
                "tools": tur.get("totalToolUseCount", 0) or 0,
                "ms": tur.get("totalDurationMs", 0) or 0,
                "nested": bool(o.get("isSidechain")),
            })

    if not calls:
        print("no subagent invocations in this transcript yet — run a fleet task first.")
        return

    by_agent = defaultdict(lambda: {"n": 0, "tok": 0, "model": "?", "ms": 0})
    by_model = defaultdict(lambda: {"n": 0, "tok": 0})
    for c in calls:
        a = by_agent[c["agent"]]
        a["n"] += 1; a["tok"] += c["tok"]; a["model"] = c["model"]; a["ms"] += c["ms"]
        m = by_model[c["model"]]
        m["n"] += 1; m["tok"] += c["tok"]

    print("── invocations per agent ──")
    for a, d in sorted(by_agent.items(), key=lambda x: -x[1]["tok"]):
        print(f"  {a:16} x{d['n']:<3} {d['model']:7} {d['tok']:>9,} tok  {d['ms']/1000:5.0f}s")

    total = sum(d["tok"] for d in by_model.values()) or 1
    cost_total = 0.0
    print("\n── token + cost spread by model tier ──")
    for m, d in sorted(by_model.items(), key=lambda x: -x[1]["tok"]):
        cost = d["tok"] / 1e6 * RATES.get(m, 0)
        cost_total += cost
        print(f"  {m:7} {d['tok']:>9,} tok ({100*d['tok']/total:4.0f}%)  x{d['n']:<3} ~${cost:.3f}")
    print(f"  {'TOTAL':7} {total:>9,} tok           ~${cost_total:.3f}  (rates approx)")

    nested = sum(1 for c in calls if c["nested"])
    print(f"\n── escalation ──\n  {nested}/{len(calls)} calls were nested (executor→advisor sidechains)")

    print("\n── delegation diagram (mermaid) ──")
    print("```mermaid")
    print("flowchart TD")
    print("  main([orchestrator])")
    edges = defaultdict(int)
    for c in calls:
        edges[(("advisor→" if c["nested"] and c["agent"] == "advisor" else "main"), c["agent"], c["nested"])] += 1
    for (src, tgt, nested), n in edges.items():
        arrow = "-.escalate.->" if nested else "-->"
        s = "executor" if nested else "main"
        print(f"  {s} {arrow}|x{n}| {tgt}")
    print("```")


if __name__ == "__main__":
    main()
