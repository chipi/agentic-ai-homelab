#!/usr/bin/env python3
"""Report what is configured, before a sweep discovers it the expensive way.

Never prints a key. Length and shape only — enough to tell "set" from "set to
the placeholder" from "not set", which is the distinction that actually costs
you a failed run halfway through.

    make env-check
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import ROOT, env_float, env_int, load_dotenv  # noqa: E402

PROVIDER_KEYS = ("ANTHROPIC_API_KEY", "OPENROUTER_API_KEY", "OPENAI_API_KEY")


def main() -> int:
    argparse.ArgumentParser(description=__doc__.splitlines()[0]).parse_args()
    env_file = ROOT / ".env"
    loaded = load_dotenv()
    print(f".env: {'loaded ' + str(loaded) + ' var(s)' if env_file.is_file() else 'NOT PRESENT'}"
          f"   ({env_file})")
    if not env_file.is_file():
        print("      cp .env.example .env   then fill in the keys you need\n")

    print("\nprovider keys")
    any_key = False
    for name in PROVIDER_KEYS:
        raw = os.environ.get(name, "")
        if not raw:
            state = "not set"
        elif len(raw) < 20:
            state = f"SET BUT SUSPICIOUS ({len(raw)} chars — placeholder?)"
        else:
            any_key = True
            state = f"set ({len(raw)} chars, ends …{raw[-4:]})"
        print(f"  {name:22} {state}")
    if not any_key:
        print("\n  No usable provider key. `provider: echo` still works offline —")
        print("  that is enough to prove the plumbing, not to evaluate a model.")

    print("\nsystem under test")
    ref = os.environ.get("EVAL_BUILD_REF", "")
    print(f"  EVAL_BUILD_REF         {ref or '(unset — falls back to this tree’s git SHA)'}")

    print("\nspend and retries")
    cap = env_float("EVAL_MAX_COST_USD")
    print(f"  EVAL_MAX_COST_USD      " + (f"${cap:.2f} — mid-run abort" if cap
                                          else "NONE — a sweep can bill without limit"))
    print(f"  EVAL_MAX_RETRIES       {env_int('EVAL_MAX_RETRIES', 3)}")
    print(f"  EVAL_CONCURRENCY       {env_int('EVAL_CONCURRENCY', 1)}")

    if cap is None and any_key:
        # Only a failure when it can actually cost something. A fresh drop-in
        # with no keys runs `provider: echo` offline, where a cap is moot —
        # failing there would train people to ignore this command.
        print("\n  A provider key is set and EVAL_MAX_COST_USD is NOT.")
        print("  The cap is the only thing between a wrong price and an unbounded bill.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
