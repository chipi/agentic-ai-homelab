#!/usr/bin/env python3
"""A stand-in for the Google endpoints case 1's MCP flows call (www.googleapis.com: Drive v3 files.list/get/export, Tasks v1 list),
for the throwaway proof only (README "Case 1 read servers (MCP)"). It evaluates the one query shape the flows send, answers fixture
files, requires a bearer header, refuses every write, and keeps a log of what it was asked at GET /__log. Stdlib only.

  stub_google.py FOLDER_ID DOC_ID LIST_ID
"""
import json
import re
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlparse

FOLDER, DOC, LIST = sys.argv[1], sys.argv[2], sys.argv[3]
G = "application/vnd.google-apps.document"
LINK = "https://docs.google.com/document/d/%s/edit?usp=drivesdk"
FILES = {
    "docA": dict(name="Meeting 2026-11-20 pricing", mimeType=G, parents=[FOLDER], text="We agreed the pricing review moves to December.\nOwner: Ana."),
    "docB": dict(name="Meeting 2026-11-24 roadmap", mimeType=G, parents=[FOLDER], text="Roadmap: the new dashboard ships in Q1. O'Brien owns the quote \"fast\" and a back\\slash."),
    "mdC": dict(name="notes.md", mimeType="text/markdown", parents=[FOLDER], text="# Notes\nPricing tiers draft."),
    "big": dict(name="Big minutes", mimeType=G, parents=[FOLDER], text="pricing " + "x" * 80000),
    "outside": dict(name="Private salary sheet", mimeType=G, parents=["otherfolder"], text="SECRET salaries, pricing too"),
    "trash": dict(name="Trashed pricing", mimeType=G, parents=[FOLDER], text="pricing", trashed=True),
    DOC: dict(name="homelab n8n decisions", mimeType=G, parents=["rootfolder"], text="Decisions\nDecision: pricing stays flat in 2027.\n"),
}
TASKS = [
    {"id": "t1", "title": "Send the pricing deck", "due": "2026-12-01T00:00:00.000Z", "notes": "who: Ana\nflotilla delivery: d1\n" + "n" * 600, "status": "needsAction"},
    {"id": "t2", "title": "Book the roadmap review", "status": "needsAction", "webViewLink": "https://tasks.google.com/task/abc"},
]
LOG = []


def meta(i):
    f = FILES[i]
    return {"id": i, "name": f["name"], "mimeType": f["mimeType"], "parents": f["parents"], "webViewLink": LINK % i,
            "modifiedTime": "2026-11-2%sT10:00:00.000Z" % (len(i) % 10)}


def match_q(q):
    """The one query shape the flow sends: '<F>' in parents and fullText contains '<s>' and trashed = false (\\ and ' escaped)."""
    m = re.fullmatch(r"'([^']+)' in parents and fullText contains '((?:[^'\\]|\\.)*)' and trashed = false", q)
    if not m:
        return None
    folder, term = m.group(1), re.sub(r"\\(.)", r"\1", m.group(2)).lower()
    return [i for i, f in FILES.items() if folder in f["parents"] and not f.get("trashed") and (term in f["text"].lower() or term in f["name"].lower())]


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def send(self, code, body, ctype="application/json"):
        raw = body if isinstance(body, bytes) else (body if isinstance(body, str) else json.dumps(body)).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        u = urlparse(self.path)
        qs = {k: v[0] for k, v in parse_qs(u.query).items()}
        if u.path == "/__log":
            return self.send(200, LOG)
        LOG.append({"path": u.path, "query": qs, "auth": bool(re.match(r"Bearer \S+", self.headers.get("Authorization") or ""))})
        if not LOG[-1]["auth"]:
            return self.send(401, {"error": {"code": 401, "message": "no bearer"}})
        p = unquote(u.path)
        if p == "/drive/v3/files":
            ids = match_q(qs.get("q", ""))
            if ids is None:
                return self.send(400, {"error": {"code": 400, "message": "Invalid Value (q)"}})
            lim = int(qs.get("pageSize", "100"))
            return self.send(200, {"files": [meta(i) for i in ids][:lim]})
        m = re.fullmatch(r"/drive/v3/files/([^/]+)(/export)?", p)
        if m and m.group(1) in FILES:
            i = m.group(1)
            if m.group(2):
                if FILES[i]["mimeType"] != G or qs.get("mimeType") != "text/plain":
                    return self.send(403, {"error": {"code": 403, "message": "Export only supports Docs Editors files"}})
                return self.send(200, FILES[i]["text"], "text/plain")
            if qs.get("alt") == "media":
                if FILES[i]["mimeType"] == G:
                    return self.send(403, {"error": {"code": 403, "message": "Only files with binary content can be downloaded"}})
                return self.send(200, FILES[i]["text"], "text/plain")
            return self.send(200, meta(i))
        if m:
            return self.send(404, {"error": {"code": 404, "message": "File not found"}})
        if p == "/tasks/v1/lists/%s/tasks" % LIST:
            return self.send(200, {"kind": "tasks#tasks", "items": TASKS})
        return self.send(404, {"error": {"code": 404, "message": "no such endpoint " + p}})

    def do_POST(self):
        self.send(405, {"error": {"code": 405, "message": "the stub is read-only"}})

    do_PUT = do_PATCH = do_DELETE = do_POST


ThreadingHTTPServer(("0.0.0.0", 8080), H).serve_forever()
