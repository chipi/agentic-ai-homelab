#!/usr/bin/env python3
"""signal-fleet test webhook receiver — the homelab entry point for Phase-0
trigger tests.

Captures inbound alert webhooks (Grafana contact point, GlitchTip project alert)
so we can verify the *push* path end-to-end before the real fleet ingress exists.
It is a test harness, not production: it logs each request (method, path, a few
headers, and the JSON body) to stdout and to captures.log, and returns 200.

Stdlib only — no pip install needed on the mini. Run:  python3 receiver.py [port]
Default port 8099. Containers on the mini reach it at host.docker.internal:<port>;
tailnet peers reach it at homelab:<port> (subject to the Tailscale ACL).
"""
import json
import sys
import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

LOG = "captures.log"


class Handler(BaseHTTPRequestHandler):
    def _capture(self):
        n = int(self.headers.get("Content-Length", 0) or 0)
        body = self.rfile.read(n) if n else b""
        try:
            parsed = json.loads(body) if body else None
        except Exception:
            parsed = body.decode("utf-8", "replace")
        rec = {
            "ts": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "method": self.command,
            "path": self.path,
            "ua": self.headers.get("User-Agent"),
            "content_type": self.headers.get("Content-Type"),
            "body": parsed,
        }
        line = json.dumps(rec, ensure_ascii=False)
        print(line, flush=True)
        try:
            with open(LOG, "a") as f:
                f.write(line + "\n")
        except Exception:
            pass
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"ok":true}')

    do_POST = _capture
    do_PUT = _capture

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"signal-fleet test receiver up\n")

    def log_message(self, *args):
        pass  # silence the default per-request logging; we emit our own JSON line


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8099
    print(f"signal-fleet test receiver listening on 0.0.0.0:{port} -> {LOG}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()
