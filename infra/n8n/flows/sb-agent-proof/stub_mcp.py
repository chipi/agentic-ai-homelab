#!/usr/bin/env python3
"""A stand-in for the case 1 docs and tasks MCP servers (the proof of the second brain agent), throwaway, stdlib only.
  stub_mcp.py docs|tasks PORT      streamable-HTTP MCP at POST /mcp, bearer token in MCP_TOKEN (else 403, as n8n's MCP trigger does).
docs has tools search {query} and read {id} over two made-up documents; tasks has list over two made-up tasks. Results are JSON text, the
shape the real servers give. GET /__log lists the tool calls (tool, arguments)."""
import hmac
import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROLE, PORT = sys.argv[1], int(sys.argv[2])
LOG, LOCK = [], threading.Lock()
DOCS = [
    {"id": "1AtlasChecklist0001", "name": "Atlas rollout launch checklist", "webViewLink": "https://docs.example.test/d/atlas-launch-checklist",
     "text": "The Atlas rollout launches on 14 March. The checklist needs the load test signed off by the platform team and the rollback runbook reviewed by Dana before the date."},
    {"id": "1BorealisPricing0002", "name": "Borealis vendor pricing decision", "webViewLink": "https://docs.example.test/d/borealis-pricing-decision",
     "text": "Decision: we pay Borealis a flat 4200 per month for the support tier, reviewed each September. The premium tier was rejected as too expensive."},
]
TASKS = [
    {"title": "Renew the Fabrikam support contract", "due": "2026-12-15", "notes": "Ask for the multi-year discount first.", "ref": "https://tasks.example.test/t/fabrikam-renewal"},
    {"title": "Draft the onboarding guide for new analysts", "due": "2027-01-10", "notes": "", "ref": "https://tasks.example.test/t/onboarding-guide"},
]
TOOLS = {
    "docs": [
        {"name": "search", "description": "Search the company documents (meeting notes and the decisions doc) for words. Returns documents with id, name, modified and link (webViewLink). Use the id with read.",
         "inputSchema": {"type": "object", "properties": {"query": {"type": "string", "description": "The words to look for"}}, "required": ["query"]}},
        {"name": "read", "description": "Read one document by the id that search returned. Returns its title, link (webViewLink) and text.",
         "inputSchema": {"type": "object", "properties": {"id": {"type": "string", "description": "The document id exactly as search returned it"}}, "required": ["id"]}}],
    "tasks": [{"name": "list", "description": "List the open follow-up tasks: title, due date, notes and ref (a link). Takes no arguments.",
               "inputSchema": {"type": "object", "properties": {}}}],
}


def call(name, a):
    if ROLE == "docs" and name == "search":
        words = [w for w in str(a.get("query", "")).lower().replace("?", " ").split() if len(w) > 2]
        hit = [d for d in DOCS if any(w in (d["name"] + " " + d["text"]).lower() for w in words)]
        return [{"id": d["id"], "name": d["name"], "modified": "2026-11-01T10:00:00Z", "webViewLink": d["webViewLink"]} for d in hit]
    if ROLE == "docs" and name == "read":
        for d in DOCS:
            if d["id"] == a.get("id"):
                return {"title": d["name"], "webViewLink": d["webViewLink"], "text": d["text"]}
        raise ValueError("docs.read: refused: not in the folder")
    if ROLE == "tasks" and name == "list":
        return TASKS
    raise ValueError("unknown tool " + str(name))


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def send(self, code, obj, extra=None):
        raw = json.dumps(obj).encode() if obj is not None else b""
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        if self.path == "/__log":
            return self.send(200, LOG)
        self.send(405, {"error": "post only"})

    def do_DELETE(self):
        self.send(200, None)

    def do_POST(self):
        raw = self.rfile.read(int(self.headers.get("Content-Length") or 0))
        if not hmac.compare_digest(self.headers.get("Authorization", ""), "Bearer " + os.environ["MCP_TOKEN"]):
            return self.send(403, {"error": "Forbidden"})
        try:
            m = json.loads(raw)
        except ValueError:
            return self.send(400, {"error": "json"})
        method, p, rid = m.get("method"), m.get("params") or {}, m.get("id")
        if rid is None:
            return self.send(202, None)
        if method == "initialize":
            res = {"protocolVersion": "2025-06-18", "capabilities": {"tools": {}}, "serverInfo": {"name": "stub-" + ROLE, "version": "0"}}
        elif method == "tools/list":
            res = {"tools": TOOLS[ROLE]}
        elif method == "tools/call":
            with LOCK:
                LOG.append({"tool": p.get("name"), "arguments": p.get("arguments")})
            try:
                res = {"content": [{"type": "text", "text": json.dumps(call(p.get("name"), p.get("arguments") or {}))}], "isError": False}
            except ValueError as e:
                res = {"content": [{"type": "text", "text": "There was an error: " + str(e)}], "isError": True}
        elif method == "ping":
            res = {}
        else:
            return self.send(200, {"jsonrpc": "2.0", "id": rid, "error": {"code": -32601, "message": "no such method"}})
        body = json.dumps({"jsonrpc": "2.0", "id": rid, "result": res}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Mcp-Session-Id", "stub-session")
        out = b"event: message\ndata: " + body + b"\n\n"
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)


ThreadingHTTPServer(("0.0.0.0", PORT), H).serve_forever()
