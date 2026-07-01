#!/usr/bin/env python3
"""fleet-stats — per-subagent invocation + token/cost breakdown from a Claude Code
transcript. Proves the cost-spread of a model-tiered subagent fleet, fully local
(no Grafana / OTEL needed).

v2 descends into the session's subagents/ transcripts, so nested escalations (an
executor consulting the opus advisor) land in the right model tier instead of being
invisible. See "How nesting is counted" in SKILL.md.

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


def load(path):
    try:
        fh = open(path)
    except OSError:
        return
    with fh:
        for line in fh:
            try:
                yield json.loads(line)
            except Exception:
                continue


def own_context(path):
    """A subagent's own final-context size + model, from its own transcript. A
    top-level result's totalTokens equals its last assistant turn's full context
    (input + cache + output); we reproduce that here for nested agents, whose
    parent often never persisted a result summary. Returns (tokens, model)."""
    tok, model = 0, None
    for o in load(path):
        msg = o.get("message")
        if isinstance(msg, dict) and msg.get("role") == "assistant":
            if msg.get("model"):
                model = msg["model"]
            u = msg.get("usage") or {}
            if isinstance(u, dict):
                tok = (u.get("input_tokens", 0) + u.get("cache_creation_input_tokens", 0)
                       + u.get("cache_read_input_tokens", 0) + u.get("output_tokens", 0))
    return tok, model


def collect(path):
    """One dict per subagent invocation — top-level and nested. Nested advisor
    escalations live in <session>/subagents/ and never appear in the main
    transcript, so we walk that dir and link each back to its parent."""
    calls, id2type = [], {}

    # 1. top-level invocations — authoritative totalTokens from the main transcript,
    #    read exactly as v1 did (unchanged numbers for the orchestrator's own calls).
    top_ids = set()
    for o in load(path):
        tur = o.get("toolUseResult")
        if isinstance(tur, dict) and tur.get("agentType"):
            aid = tur.get("agentId")
            top_ids.add(aid)
            id2type[aid] = tur["agentType"]
            calls.append({
                "agent": tur["agentType"], "model": tier(tur.get("resolvedModel")),
                "tok": tur.get("totalTokens", 0) or 0,
                "tools": tur.get("totalToolUseCount", 0) or 0,
                "ms": tur.get("totalDurationMs", 0) or 0,
                "nested": False, "parent": "main",
            })

    # 2. nested invocations — each agent-*.jsonl in subagents/ that isn't top-level.
    #    Tokens/model come from its own transcript; meta.toolUseId links it to the
    #    parent that spawned it.
    sub_dir = (path[:-6] if path.endswith(".jsonl") else path) + "/subagents"
    if not os.path.isdir(sub_dir):
        return calls, id2type

    metas = {}  # agentId -> (agentType, toolUseId)
    for m in glob.glob(sub_dir + "/agent-*.meta.json"):
        aid = os.path.basename(m)[len("agent-"):-len(".meta.json")]
        try:
            d = json.load(open(m))
        except Exception:
            d = {}
        metas[aid] = (d.get("agentType"), d.get("toolUseId"))
        id2type.setdefault(aid, d.get("agentType"))

    # tool_use id -> owning agentId ("main" = root transcript), to resolve parents
    tooluse_owner = {}

    def index(f, owner):
        for o in load(f):
            msg = o.get("message")
            content = msg.get("content") if isinstance(msg, dict) else None
            if isinstance(content, list):
                for blk in content:
                    if isinstance(blk, dict) and blk.get("type") == "tool_use":
                        tooluse_owner[blk["id"]] = owner

    index(path, "main")
    agent_files = glob.glob(sub_dir + "/agent-*.jsonl")
    for f in agent_files:
        index(f, os.path.basename(f)[len("agent-"):-len(".jsonl")])

    for f in agent_files:
        aid = os.path.basename(f)[len("agent-"):-len(".jsonl")]
        if aid in top_ids:
            continue  # top-level — already counted from the main transcript
        atype, tid = metas.get(aid, (None, None))
        tok, model = own_context(f)
        parent_id = tooluse_owner.get(tid, "main")
        calls.append({
            "agent": atype or "?", "model": tier(model), "tok": tok,
            "tools": 0, "ms": 0, "nested": True,
            "parent": "main" if parent_id == "main" else id2type.get(parent_id, "?"),
        })
    return calls, id2type


def main():
    path = find_transcript()
    if not path:
        print("fleet-stats: no transcript found")
        return
    print(f"fleet-stats — {os.path.basename(path)}\n")

    calls, _ = collect(path)
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

    nested = [c for c in calls if c["nested"]]
    print("\n── escalation ──")
    print(f"  {len(nested)}/{len(calls)} calls were nested (executor→advisor sidechains)")
    for c in nested:
        print(f"    {c['parent']} → {c['agent']} ({c['model']}, {c['tok']:,} tok)")

    print("\n── delegation diagram (mermaid) ──")
    print("```mermaid")
    print("flowchart TD")
    print("  main([orchestrator])")
    edges = defaultdict(int)
    for c in calls:
        edges[(c["parent"], c["agent"], c["nested"])] += 1
    for (src, tgt, is_nested), n in sorted(edges.items()):
        arrow = "-.escalate.->" if is_nested else "-->"
        print(f"  {src} {arrow}|x{n}| {tgt}")
    print("```")


if __name__ == "__main__":
    main()
