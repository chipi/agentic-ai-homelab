#!/usr/bin/env python3
"""Check a message to another session before it is sent: no placeholders, every state claim proven.

  lint_msg.py MESSAGE_FILE [--proof WORD='shell command'] [--allow TOKEN] [--not-a-claim WORD]

Refuses (exit 1) when the message still holds a placeholder — <ids>, {ids}, $IDS, TODO, XXX, TBD,
or a bare ALL_CAPS_TOKEN outside backticks (the 2026-10-17 message carried "BATCH2_IDS" instead of
the 21 ids) — or when it states a state word (held, paused, stopped, deployed, applied, pushed,
merged, approved, released, verified, green, passed, running, done) without a --proof for that
word whose command exits 0 right now (the same day's message said "I am holding it" while the
chain would still approve). On success prints SENDABLE and the message, to paste into SendMessage.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

STATE_WORDS = ["held", "holding", "on hold", "paused", "stopped", "deployed", "applied", "pushed", "merged",
               "approved", "released", "verified", "green", "passed", "running", "done", "fixed", "live"]
PLACEHOLDERS = [
    (re.compile(r"<[A-Za-z][A-Za-z0-9 _-]{1,40}>"), "angle-bracket placeholder"),
    (re.compile(r"\{\{?[A-Za-z_][A-Za-z0-9_.]*\}?\}"), "brace placeholder"),
    (re.compile(r"\$\{?[A-Z_][A-Z0-9_]{2,}\}?"), "shell variable"),
    (re.compile(r"\b(TODO|TBD|XXX|FIXME|PLACEHOLDER)\b"), "marker"),
]
CAPS_TOKEN = re.compile(r"\b[A-Z][A-Z0-9]*_[A-Z0-9_]+\b")
CODE_SPAN = re.compile(r"`[^`]*`|```.*?```", re.S)


def placeholders(text: str, allow: set[str]) -> list[str]:
    hits = []
    for rx, kind in PLACEHOLDERS:
        hits += [f"{kind}: {m.group(0)}" for m in rx.finditer(text) if m.group(0) not in allow]
    bare = CODE_SPAN.sub(" ", text)
    hits += [f"bare ALL_CAPS token (placeholder? wrap a real name in backticks, or --allow it): {m.group(0)}"
             for m in CAPS_TOKEN.finditer(bare) if m.group(0) not in allow]
    return hits


def claims(text: str, not_claims: set[str]) -> dict[str, str]:
    """state word -> first sentence using it (negated uses like 'not deployed' are claims too)."""
    out: dict[str, str] = {}
    for sentence in re.split(r"(?<=[.!?\n])\s+", text):
        for w in STATE_WORDS:
            if w not in not_claims and re.search(rf"\b{re.escape(w)}\b", sentence, re.I) and w not in out:
                out[w] = sentence.strip()[:160]
    return out


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("message")
    p.add_argument("--proof", action="append", default=[], help="WORD='command' (exit 0 = the claim holds)")
    p.add_argument("--allow", action="append", default=[], help="a token that is a real name, not a placeholder")
    p.add_argument("--not-a-claim", action="append", default=[], help="a state word used descriptively")
    a = p.parse_args()
    text = Path(a.message).read_text()
    problems = placeholders(text, set(a.allow))
    proofs: dict[str, str] = {}
    for pr in a.proof:
        word, _, cmd = pr.partition("=")
        proofs[word.strip().lower()] = cmd
    for word, sentence in claims(text, {w.lower() for w in a.not_a_claim}).items():
        cmd = proofs.get(word)
        if not cmd:
            problems.append(f"claim '{word}' has no --proof: \"{sentence}\"")
            continue
        r = subprocess.run(["/usr/bin/env", "bash", "-c", cmd], capture_output=True, text=True)
        if r.returncode != 0:
            problems.append(f"claim '{word}' proof FAILED (exit {r.returncode}): {cmd}\n    {r.stdout.strip()[-200:]} {r.stderr.strip()[-200:]}")
        else:
            print(f"proof ok: {word} <- {cmd}")
    if problems:
        print("REFUSED — fix before sending:")
        for x in problems:
            print(f"  - {x}")
        return 1
    print("SENDABLE\n" + "-" * 60 + "\n" + text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
