#!/usr/bin/env python3
"""Stand-ins for the proof of case 1's Slack flows (README "Case 1 Slack flows"), throwaway, stdlib only.

  stub_slack.py slack PORT   Slack's Web API: conversations.history (a mutable fixture, newest first, paged by cursor) and
                             chat.postMessage (recorded). Both require the bearer token in SLACK_TOKEN.
  stub_slack.py hook PORT    flotilla's `ask` hook as internal/hook checks a call: the delivery id pattern, the timestamp's 5-minute
                             window, the signature (flotilla's plumbing/call.py `sign`, the mirror of hook.Sign, from PYTHONPATH),
                             a JSON object with the fields thread, user, text; a delivery seen before answers 200, a new one 202.

Both keep a log at GET /__log and are steered by POST: /__set (slack: {"messages": [...], "page_cap": N, "history_error": "x"|null,
"post_error": "x"|null}), /__add (slack: one message), /__fail (hook: {"status": 500, "times": 1}).
"""
import hmac
import json
import os
import re
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

ROLE, PORT = sys.argv[1], int(sys.argv[2])
LOCK = threading.Lock()
LOG = []
S = {"messages": [], "page_cap": 0, "history_error": None, "post_error": None, "fail": {"status": 0, "times": 0}, "seen": set(), "n": 0}


def cmpkey(ts):
    a, _, b = ts.partition(".")
    return (int(a), int(b.ljust(9, "0")))


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def send(self, code, obj):
        raw = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def body(self):
        return self.rfile.read(int(self.headers.get("Content-Length") or 0))

    def do_GET(self):
        u = urlparse(self.path)
        if u.path == "/__log":
            return self.send(200, LOG)
        if ROLE == "slack" and u.path == "/api/conversations.history":
            return self.history(parse_qs(u.query))
        self.send(404, {"error": "no"})

    def do_POST(self):
        u = urlparse(self.path)
        raw = self.body()
        if u.path == "/__set":
            with LOCK:
                d = json.loads(raw)
                if "messages" in d:
                    S["messages"] = d["messages"]
                for k in ("page_cap", "history_error", "post_error"):
                    if k in d:
                        S[k] = d[k]
                if d.get("reset_log"):
                    LOG.clear()
            return self.send(200, {"ok": True})
        if u.path == "/__add":
            with LOCK:
                S["messages"].append(json.loads(raw))
            return self.send(200, {"ok": True})
        if u.path == "/__fail":
            with LOCK:
                S["fail"] = json.loads(raw)
            return self.send(200, {"ok": True})
        if ROLE == "slack" and u.path == "/api/chat.postMessage":
            return self.post_message(raw)
        if ROLE == "hook" and u.path == "/hooks/ask":
            return self.ask(raw)
        self.send(404, {"error": "no"})

    # ---- Slack ----
    def authed(self):
        return hmac.compare_digest(self.headers.get("Authorization", ""), "Bearer " + os.environ["SLACK_TOKEN"])

    def history(self, q):
        with LOCK:
            one = lambda k, d="": (q.get(k) or [d])[0]
            LOG.append({"call": "history", "auth": self.authed(), "channel": one("channel"), "oldest": one("oldest"), "limit": one("limit"), "cursor": one("cursor")})
            if not self.authed():
                return self.send(200, {"ok": False, "error": "invalid_auth"})
            if S["history_error"]:
                return self.send(200, {"ok": False, "error": S["history_error"]})
            oldest = cmpkey(one("oldest", "0"))
            msgs = sorted((m for m in S["messages"] if cmpkey(m["ts"]) > oldest), key=lambda m: cmpkey(m["ts"]), reverse=True)
            n = int(one("limit", "100"))
            if S["page_cap"]:
                n = min(n, S["page_cap"])
            start = int(one("cursor", "0") or 0)
            page = msgs[start:start + n]
            more = start + n < len(msgs)
            out = {"ok": True, "messages": page, "has_more": more}
            if more:
                out["response_metadata"] = {"next_cursor": str(start + n)}
            return self.send(200, out)

    def post_message(self, raw):
        with LOCK:
            d = json.loads(raw or b"{}")
            LOG.append({"call": "post", "auth": self.authed(), "body": d, "ctype": self.headers.get("Content-Type", "")})
            if not self.authed():
                return self.send(200, {"ok": False, "error": "invalid_auth"})
            if S["post_error"]:
                return self.send(200, {"ok": False, "error": S["post_error"]})
            S["n"] += 1
            return self.send(200, {"ok": True, "channel": d.get("channel"), "ts": "1800000000.%06d" % S["n"], "message": {"text": d.get("text")}})

    # ---- flotilla's hook ----
    def ask(self, raw):
        import call  # flotilla's plumbing/call.py: its `sign` mirrors internal/hook.Sign
        h = self.headers
        ts, delivery, sig = h.get("X-Flotilla-Timestamp", ""), h.get("X-Flotilla-Delivery", ""), h.get("X-Flotilla-Signature", "")
        why = None
        if not re.fullmatch(r"[A-Za-z0-9._:-]{1,128}", delivery):
            why = "delivery id"
        elif not re.fullmatch(r"-?[0-9]+", ts) or abs(time.time() - int(ts)) > 300:
            why = "timestamp window"
        elif not hmac.compare_digest(sig, "sha256=" + call.sign(os.environ["HOOK_SECRET"], ts, delivery, raw)):
            why = "bad signature"
        elif len(raw) > 4096:
            why = "too big"
        rec = {"call": "ask", "delivery": delivery, "ts": ts, "sig_ok": why is None, "raw": raw.decode("utf-8", "replace")}
        with LOCK:
            LOG.append(rec)
            if why:
                rec["code"] = 401
                return self.send(401, {"error": why})
            if S["fail"]["times"] > 0:
                S["fail"]["times"] -= 1
                rec["code"] = S["fail"]["status"]
                return self.send(S["fail"]["status"], {"error": "stub failure"})
            try:
                b = json.loads(raw)
                assert isinstance(b, dict)
                assert re.fullmatch(r"[0-9.]{1,32}", b.get("thread", ""))
                assert len(b.get("user", "")) <= 40 and len(b.get("text", "")) <= 2000
            except Exception:
                rec["code"] = 400
                return self.send(400, {"error": "fields"})
            code = 200 if delivery in S["seen"] else 202
            S["seen"].add(delivery)
            rec["code"] = code
            return self.send(code, {"case": "stub", "replay": code == 200})


ThreadingHTTPServer(("0.0.0.0", PORT), H).serve_forever()
