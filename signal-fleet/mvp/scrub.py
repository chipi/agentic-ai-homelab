"""Reproducible fixture scrubber — makes reference fixtures safe to commit to the
PUBLIC repo (EVAL.md data-hygiene; supersedes freeze.py's IPv4-only redaction).

Two tiers:
  1. SECRETS — hard-redacted to <redacted-*>. These must NEVER be in a fixture; if
     `scan()` finds one, that is a FAILURE (the CLI exits non-zero). Belt-and-braces.
  2. IDENTIFIERS — real production identifiers (domains, operator paths/handle, host
     topology, git shas, long hashes) mapped to stable synthetic equivalents. These
     are NOT secret, but a public eval corpus should not be tied to live products or
     internal infra. The mapping preserves SHAPE + SEMANTICS, so the triager reasons
     over the same evidence and the eval's dispositions are unchanged.

Determinism: pure regex, idempotent (scrubbing twice == once), value-only — probe
TABLE KEYS are never rewritten (the scorer matches them byte-for-byte; freeze.py).

  python3 scrub.py path/to/fixture.json ...   # scrub in place
  python3 scrub.py --scan path/to/fixture.json ...   # audit only, non-zero on secrets
  python3 scrub.py --dir <reference_dir>      # scrub every *.json in a dir
"""
import json
import re
import sys

# ── tier 1: secrets (hard-redact; presence = failure) ───────────────────────
SECRETS = [
    (re.compile(r"sk-or-v1-[a-f0-9]{16,}"), "<redacted-openrouter-key>"),
    (re.compile(r"sk-[A-Za-z0-9]{20,}"), "<redacted-api-key>"),
    (re.compile(r"glsa_[A-Za-z0-9_]{16,}"), "<redacted-grafana-token>"),
    (re.compile(r"Bearer\s+[A-Za-z0-9._\-]{16,}"), "Bearer <redacted-token>"),
    (re.compile(r"eyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+"), "<redacted-jwt>"),
    (re.compile(r"AKIA[0-9A-Z]{16}"), "<redacted-aws-key>"),
    (re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}"), "<redacted-gh-token>"),
    # emails — but NOT package@version (domain must start with a letter, not a digit)
    (re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z][A-Za-z0-9.\-]*\.[A-Za-z]{2,}\b"), "<email>"),
]

# ── tier 2: identifiers (map to stable synthetic; shape/semantics preserved) ─
# order matters — most specific first.
IDENTIFIERS = [
    # IPs (freeze.py already does v4; keep idempotent + add v6)
    (re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}\b"), "<ip>"),
    (re.compile(r"\b(?:[0-9a-fA-F]{0,4}:){3,7}[0-9a-fA-F]{0,4}\b(?=.*::|.*:[0-9a-f])"), "<ip6>"),
    # real production domains (operator products) -> synthetic, consistent mapping
    (re.compile(r"\b(?:www\.)?orrerylearn\.com\b"), "example-orrery.test"),
    (re.compile(r"\bclose ?listening\.app\b", re.I), "example-cl.test"),
    (re.compile(r"\buptimerobot(\.com)?\b", re.I), "example-monitor"),
    # tailnet + internal hostnames
    (re.compile(r"\b[a-z0-9-]+\.tail[0-9a-f]+\.ts\.net\b"), "<node>.ts.net"),
    (re.compile(r"\bhomelab\.local\b"), "<host>.local"),
    # operator home paths + handle
    (re.compile(r"/(?:Users|home)/markodragoljevic\b"), "/home/dev"),
    (re.compile(r"\bchipi\b"), "acme"),
    # internal topology (instance/cluster/container names seen in log streams)
    (re.compile(r"\bprod-podcast\b"), "prod-host"),
    (re.compile(r'\b(instance|container|server_name)(["\s:=]+)[A-Za-z0-9_.\-]+'),
     lambda m: f"{m.group(1)}{m.group(2)}<host>"),
    # git build refs
    (re.compile(r"\b(gha|sha)-[0-9a-f]{7,40}\b"), r"\1-<sha>"),
    # long hex ids (trace_id 32, stream_id 48/64) — non-secret but genericize
    (re.compile(r"\b[0-9a-f]{32,64}\b"), "<hex>"),
]


def _apply(s, rules):
    for rx, repl in rules:
        s = rx.sub(repl, s)
    return s


def scrub_str(s):
    return _apply(_apply(s, SECRETS), IDENTIFIERS)


def scrub(obj):
    """Recurse, scrubbing both keys and values with the SAME deterministic rules.
    Keys must be scrubbed too (a probe-table key can embed a trace_id) — but doing
    it identically on both sides keeps the frozen key matching the key the scorer
    rebuilds from the scrubbed signal at replay, so table lookups still hit."""
    if isinstance(obj, str):
        return scrub_str(obj)
    if isinstance(obj, dict):
        return {scrub_str(k) if isinstance(k, str) else k: scrub(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [scrub(x) for x in obj]
    return obj


def scan(obj):
    """Return a list of secret hits (post-nothing) anywhere in the object. Empty =
    clean. Used as the commit gate."""
    hits = []

    def walk(o):
        if isinstance(o, str):
            for rx, _ in SECRETS:
                for m in rx.finditer(o):
                    hits.append(m.group(0)[:12] + "…")
        elif isinstance(o, dict):
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for x in o:
                walk(x)
    walk(obj)
    return hits


def _scrub_file(path):
    d = json.load(open(path))
    scrubbed = scrub(d)
    leftover = scan(scrubbed)
    with open(path, "w") as f:
        json.dump(scrubbed, f, indent=2, ensure_ascii=False)
    return leftover


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    scan_only = "--scan" in sys.argv
    if "--dir" in sys.argv:
        import os
        d = args[0]
        args = [os.path.join(d, f) for f in sorted(os.listdir(d)) if f.endswith(".json")]
    bad = 0
    for path in args:
        if scan_only:
            hits = scan(json.load(open(path)))
            print(f"{'SECRET!' if hits else 'clean  '} {path}"
                  + (f"  {hits}" if hits else ""))
            bad += bool(hits)
        else:
            leftover = _scrub_file(path)
            print(f"scrubbed {path}" + (f"  ⚠ SECRETS REMAIN {leftover}" if leftover else ""))
            bad += bool(leftover)
    raise SystemExit(1 if bad else 0)
