"""Tiny stub outbox for the DEPLOYED worker to drain (host-side, stdlib only).

Serves the app↔infra seam: GET /internal/outbox/pending returns queued envelopes ONCE
(then empties, so the worker doesn't re-send on every poll), POST /status records the
write-back. Envelopes are loaded from OUTBOX_ENVELOPES (a JSON file path) at startup.

    OUTBOX_ENVELOPES=/path/envs.json python3 stub_outbox_host.py 8092
"""
import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

_PENDING = []
_STATUS = []


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _j(self, code, obj):
        b = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        if self.path.startswith("/internal/outbox/pending"):
            global _PENDING
            batch, _PENDING = _PENDING, []   # serve once
            return self._j(200, {"envelopes": batch})
        if self.path == "/status":
            return self._j(200, {"reported": _STATUS})
        return self._j(404, {})

    def do_POST(self):
        n = int(self.headers.get("Content-Length", "0"))
        body = json.loads(self.rfile.read(n) or b"{}")
        if "/status" in self.path:
            eid = self.path.split("/")[3]
            _STATUS.append((eid, body.get("status")))
            print("STATUS", eid, body.get("status"), flush=True)
            return self._j(200, {"ok": True})
        return self._j(404, {})


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8092
    path = os.environ.get("OUTBOX_ENVELOPES", "")
    if path and os.path.exists(path):
        _PENDING = json.load(open(path))
    print(f"stub outbox on :{port} with {len(_PENDING)} envelope(s)", flush=True)
    ThreadingHTTPServer(("0.0.0.0", port), H).serve_forever()
