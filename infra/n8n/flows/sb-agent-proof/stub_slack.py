#!/usr/bin/env python3
"""Slack's stand-in for the proof of the second brain agent, throwaway, stdlib only.

  stub_slack.py HTTP_PORT WS_PORT

Web API (bearer token in SLACK_TOKEN, the app-level one for apps.connections.open in SLACK_APP_TOKEN):
  apps.connections.open     -> {ok, url: ws://<WS_HOST>:WS_PORT/link}
  conversations.replies     -> the thread set by /__set {"threads": {"<root ts>": [messages]}} (oldest first, as Slack gives it)
  chat.postMessage          -> recorded, answers {ok, ts}
Socket Mode server on WS_PORT: sends `hello` on connect, then the envelopes the test injects; records every frame the client sends back (acks).
Steering (POST, JSON): /__set {"threads": ..., "reset_log": true}, /__event {"event": {...}, "event_id": "Ev..", "retry_attempt": 0}
(wraps it in an events_api envelope, as Slack does, with the bot's id in authorizations), /__disconnect {"reason": "refresh_requested"}.
GET /__log: every call, envelope sent and ack received, in order; GET /__state: connections opened so far and whether one is open."""
import base64
import hashlib
import hmac
import json
import os
import socket
import struct
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

HTTP_PORT, WS_PORT = int(sys.argv[1]), int(sys.argv[2])
WS_HOST = os.environ.get("WS_HOST", "127.0.0.1")
WS_PUBLIC_PORT = int(os.environ.get("WS_PUBLIC_PORT", WS_PORT))   # the port the client reaches (a published one)
BOT = os.environ.get("BOT_USER", "U0BOT00001")
LOCK = threading.Lock()
LOG = []
S = {"threads": {}, "n": 0, "opened": 0, "conn": None, "env": 0, "mode": "", "fail_opens": 0}


def send_frame(sock, opcode, data):
    n = len(data)
    head = bytes([0x80 | opcode]) + (bytes([n]) if n < 126 else b"~" + struct.pack(">H", n) if n < 65536 else b"\x7f" + struct.pack(">Q", n))
    sock.sendall(head + data)


def recv_exact(sock, n):
    b = b""
    while len(b) < n:
        c = sock.recv(n - len(b))
        if not c:
            raise EOFError
        b += c
    return b


def read_frame(sock):
    b1, b2 = recv_exact(sock, 2)
    n = b2 & 0x7F
    if n == 126:
        n = struct.unpack(">H", recv_exact(sock, 2))[0]
    elif n == 127:
        n = struct.unpack(">Q", recv_exact(sock, 8))[0]
    mask = recv_exact(sock, 4) if b2 & 0x80 else b""
    data = recv_exact(sock, n)
    if mask:
        data = bytes(c ^ mask[i % 4] for i, c in enumerate(data))
    return b1 & 0x0F, data


def ws_session(sock):
    if S["mode"] == "no_handshake":   # a socket that connects and never opens (through a proxy, say)
        time.sleep(40)
        sock.close()
        return
    req = b""
    while b"\r\n\r\n" not in req:
        req += sock.recv(4096)
    key = [l.split(b":", 1)[1].strip() for l in req.split(b"\r\n") if l.lower().startswith(b"sec-websocket-key")][0]
    acc = base64.b64encode(hashlib.sha1(key + b"258EAFA5-E914-47DA-95CA-C5AB0DC85B11").digest())
    sock.sendall(b"HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Accept: " + acc + b"\r\n\r\n")
    with LOCK:
        S["conn"] = sock
        LOG.append({"call": "ws_connected"})
        send_frame(sock, 1, json.dumps({"type": "hello", "num_connections": 1, "connection_info": {"app_id": "A0STUB"}}).encode())
        if S["mode"] == "close_after_hello":   # as Slack does at too_many_websockets: hello, then the socket is closed
            sock.close()
            S["conn"] = None
            LOG.append({"call": "ws_closed"})
            return
    try:
        while True:
            op, data = read_frame(sock)
            if op == 8:
                break
            if op == 9:
                send_frame(sock, 10, data)
            elif op == 1:
                with LOCK:
                    LOG.append({"call": "ack", "frame": json.loads(data)})
    except (EOFError, OSError, ValueError):
        pass
    with LOCK:
        if S["conn"] is sock:
            S["conn"] = None
        LOG.append({"call": "ws_closed"})
    try:
        sock.close()
    except OSError:
        pass


def ws_server():
    srv = socket.socket()
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("0.0.0.0", WS_PORT))
    srv.listen(8)
    while True:
        c, _ = srv.accept()
        threading.Thread(target=ws_session, args=(c,), daemon=True).start()


def push(obj):
    with LOCK:
        c = S["conn"]
        if c is None:
            return False
        LOG.append({"call": "sent", "frame": obj})
        send_frame(c, 1, json.dumps(obj).encode())
        return True


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

    def authed(self, var="SLACK_TOKEN"):
        return hmac.compare_digest(self.headers.get("Authorization", ""), "Bearer " + os.environ[var])

    def do_GET(self):
        u = urlparse(self.path)
        if u.path == "/__log":
            return self.send(200, LOG)
        if u.path == "/__state":
            with LOCK:
                return self.send(200, {"opened": S["opened"], "connected": S["conn"] is not None})
        if u.path == "/api/conversations.replies":
            q = parse_qs(u.query)
            one = lambda k: (q.get(k) or [""])[0]
            with LOCK:
                LOG.append({"call": "replies", "auth": self.authed(), "channel": one("channel"), "ts": one("ts"), "limit": one("limit")})
                if not self.authed():
                    return self.send(200, {"ok": False, "error": "invalid_auth"})
                msgs = S["threads"].get(one("ts"))
                if msgs is None:
                    return self.send(200, {"ok": False, "error": "thread_not_found"})
                return self.send(200, {"ok": True, "messages": msgs, "has_more": False})
        self.send(404, {"error": "no"})

    def do_POST(self):
        u = urlparse(self.path)
        raw = self.rfile.read(int(self.headers.get("Content-Length") or 0))
        if u.path == "/__set":
            d = json.loads(raw)
            with LOCK:
                if "fail_opens" in d:
                    S["fail_opens"] = d["fail_opens"]
                if "mode" in d:
                    S["mode"] = d["mode"]
                if "threads" in d:
                    S["threads"] = d["threads"]
                if d.get("reset_log"):
                    LOG.clear()
            return self.send(200, {"ok": True})
        if u.path == "/__event":
            d = json.loads(raw)
            with LOCK:
                S["env"] += 1
                n = S["env"]
            env = {"envelope_id": "env-%04d" % n, "type": d.get("type", "events_api"), "accepts_response_payload": False,
                   "retry_attempt": d.get("retry_attempt", 0), "retry_reason": "",
                   "payload": {"type": "event_callback", "event_id": d["event_id"], "event": d["event"], "authorizations": [{"user_id": BOT, "is_bot": True}]}}
            return self.send(200, {"ok": push(env), "envelope_id": env["envelope_id"]})
        if u.path == "/__disconnect":
            d = json.loads(raw or b"{}")
            return self.send(200, {"ok": push({"type": "disconnect", "reason": d.get("reason", "refresh_requested"), "debug_info": {}})})
        if u.path == "/api/apps.connections.open":
            with LOCK:
                good = self.authed("SLACK_APP_TOKEN")
                if good and S["fail_opens"] > 0:   # Slack refusing one apps.connections.open (ratelimited)
                    S["fail_opens"] -= 1
                    LOG.append({"call": "open", "auth": True, "failed": True, "t": time.time()})
                    return self.send(200, {"ok": False, "error": "ratelimited"})
                LOG.append({"call": "open", "auth": good, "t": time.time()})
                if not good:
                    return self.send(200, {"ok": False, "error": "invalid_auth"})
                S["opened"] += 1
            return self.send(200, {"ok": True, "url": "ws://%s:%d/link?ticket=stub" % (WS_HOST, WS_PUBLIC_PORT)})
        if u.path == "/api/chat.postMessage":
            d = json.loads(raw or b"{}")
            with LOCK:
                LOG.append({"call": "post", "auth": self.authed(), "body": d, "t": time.time()})
                if not self.authed():
                    return self.send(200, {"ok": False, "error": "invalid_auth"})
                S["n"] += 1
                return self.send(200, {"ok": True, "channel": d.get("channel"), "ts": "1800000000.%06d" % S["n"], "message": {"text": d.get("text")}})
        self.send(404, {"error": "no"})


threading.Thread(target=ws_server, daemon=True).start()
ThreadingHTTPServer(("0.0.0.0", HTTP_PORT), H).serve_forever()
