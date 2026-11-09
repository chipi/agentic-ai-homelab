"""Tiny stdlib HTTP helpers (no requests dependency)."""
import base64
import json
import urllib.parse
import urllib.request


LAST_HEADERS = {}   # the last response's headers, lower-cased; triage reads the gateway's deployment id from it


def _open(req, timeout):
    global LAST_HEADERS
    with urllib.request.urlopen(req, timeout=timeout) as r:
        LAST_HEADERS = {k.lower(): v for k, v in r.headers.items()}
        return r.read().decode("utf-8", "replace")


def get_json(url, user=None, pw=None, headers=None, timeout=12):
    req = urllib.request.Request(url)
    if user is not None:
        tok = base64.b64encode(f"{user}:{pw}".encode()).decode()
        req.add_header("Authorization", "Basic " + tok)
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    return json.loads(_open(req, timeout))


def get_text(url, params=None, headers=None, timeout=12):
    if params:
        url = url + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url)
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    return _open(req, timeout)


def post_form_text(url, form, headers=None, timeout=12):
    data = urllib.parse.urlencode(form).encode()
    req = urllib.request.Request(url, data=data)
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    return _open(req, timeout)


def post_json(url, payload, headers=None, timeout=60):
    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data)
    req.add_header("Content-Type", "application/json")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    return json.loads(_open(req, timeout))
