#!/usr/bin/env python3
"""Push one bake-off run to self-hosted Langfuse: a trace + per-LLM-call
generations (parsed from the harness's own output) + a passed score.

Handles the three output shapes:
  claude   — one result object: total_cost_usd, usage.{input,output}_tokens
  opencode — event stream: step_finish events with part.tokens / part.cost
  pi       — event stream: message_end(assistant) with message.usage.{input,output,cost}

Usage: langfuse_push.py BUG HARNESS MODEL VERDICT COST TURNS LATENCY HARNESS_JSON
Env: LANGFUSE_HOST, LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY
"""
import sys, os, json, uuid, base64, urllib.request, datetime

bug, harness, model, verdict, cost, turns, latency, hjson = sys.argv[1:9]
HOST = os.environ.get("LANGFUSE_HOST", "http://homelab:4000").rstrip("/")
PK, SK = os.environ.get("LANGFUSE_PUBLIC_KEY"), os.environ.get("LANGFUSE_SECRET_KEY")
if not (PK and SK):
    print("langfuse: no creds (LANGFUSE_PUBLIC_KEY/SECRET_KEY) — skipping"); sys.exit(0)

now = datetime.datetime.now(datetime.timezone.utc).isoformat()
tid = str(uuid.uuid4())
passed = 1 if verdict.startswith("PASS") else 0
fcost = float(cost or 0)

RUN_IDX = os.environ.get("BAKEOFF_RUN_IDX", "1")
batch = [{"id": str(uuid.uuid4()), "type": "trace-create", "timestamp": now, "body": {
    "id": tid, "name": f"bakeoff/{bug}/{harness}", "timestamp": now,
    "userId": harness,          # Langfuse "Users" view → filter requests by harness
    "sessionId": bug,           # groups the 3 harnesses for one bug side-by-side
    "environment": "bakeoff",
    "tags": ["bakeoff", harness, model, bug, f"run:{RUN_IDX}"],
    "metadata": {"verdict": verdict, "cost_usd": fcost, "turns": int(float(turns or 0)),
                 "latency_s": int(float(latency or 0)), "model": model, "run_idx": RUN_IDX},
    "input": bug, "output": verdict}}]

def gen(name, ti, to, c):
    b = {"id": str(uuid.uuid4()), "traceId": tid, "name": name, "model": model, "environment": "bakeoff",
         "usage": {"input": int(ti or 0), "output": int(to or 0), "total": int((ti or 0) + (to or 0)), "unit": "TOKENS"}}
    if c: b["metadata"] = {"cost_usd": float(c)}
    batch.append({"id": str(uuid.uuid4()), "type": "generation-create", "timestamp": now, "body": b})

try:
    lines = [json.loads(l) for l in open(hjson) if l.strip()]
except Exception:
    lines = []

if len(lines) == 1 and "total_cost_usd" in lines[0]:            # claude
    u = lines[0].get("usage", {})
    gen("claude", u.get("input_tokens"), u.get("output_tokens"), lines[0].get("total_cost_usd"))
else:                                                            # opencode / pi event streams
    step = 0
    for e in lines:
        p = e.get("part", {})
        if e.get("type") == "step_finish" and isinstance(p.get("tokens"), dict):
            step += 1; t = p["tokens"]; gen(f"step{step}", t.get("input"), t.get("output"), p.get("cost"))
        m = e.get("message", {})
        if e.get("type") == "message_end" and m.get("role") == "assistant" and m.get("usage"):
            step += 1; u = m["usage"]; gen(f"msg{step}", u.get("input"), u.get("output"), (u.get("cost") or {}).get("total"))

batch.append({"id": str(uuid.uuid4()), "type": "score-create", "timestamp": now, "body": {
    "id": str(uuid.uuid4()), "traceId": tid, "name": "passed", "value": passed, "dataType": "NUMERIC"}})

req = urllib.request.Request(HOST + "/api/public/ingestion",
    data=json.dumps({"batch": batch}).encode(), method="POST")
req.add_header("Content-Type", "application/json")
req.add_header("Authorization", "Basic " + base64.b64encode(f"{PK}:{SK}".encode()).decode())
try:
    r = urllib.request.urlopen(req, timeout=15)
    print(f"langfuse: {r.status} trace={tid[:8]} ({len(batch)-2} generations)")
except Exception as ex:
    print(f"langfuse push failed: {ex}")
