#!/usr/bin/env python3
"""Does CPU work in the same process starve a request? Time a probe three ways.

    contention_bench.py --probe MOD:FN --load MOD:FN [--threads 1] [--samples 30] [--path DIR]...
    contention_bench.py --demo

PROBE is what a request does (no arguments; e.g. a corpus walk, a route's helper). LOAD is the
background work suspected of holding the GIL (no arguments; called in a loop). The probe is timed:

  1. idle;
  2. with LOAD running in N threads of THIS process (what an in-process warmer or worker does);
  3. with LOAD running in a CHILD process (the fix: its own interpreter, its own GIL).

If (2) is many times (1) and (3) is close to (1), the stall is GIL starvation and moving the work
out of the process fixes it. A probe that does many small syscalls suffers most: it gives the GIL
up on each one and then queues for it behind the CPU-bound thread.

Measured on prod's pattern (podcast_scraper, 2026-10-16): a 161-file walk took 1.4 ms idle,
129 ms with reel-clip scoring in-process (median of 53), and 1.6 ms with the scoring in a child.

--path adds import roots (e.g. a repo's ``src``); run it with the project's interpreter.
Prints one line per mode and a verdict. Writes nothing outside a temp dir (``--demo`` only).
"""

from __future__ import annotations

import argparse
import importlib
import os
import statistics
import subprocess
import sys
import tempfile
import threading
import time
from typing import Callable


def resolve(spec: str) -> Callable[[], object]:
    mod, _, fn = spec.partition(":")
    if not fn:
        raise SystemExit(f"--probe/--load take MODULE:FUNCTION, got {spec!r}")
    return getattr(importlib.import_module(mod), fn)


def time_probe(probe: Callable[[], object], samples: int) -> list[float]:
    out = []
    for _ in range(samples):
        t = time.perf_counter()
        probe()
        out.append(time.perf_counter() - t)
    return out


def with_threads(probe: Callable[[], object], load: Callable[[], object], n: int, samples: int) -> list[float]:
    stop = threading.Event()

    def spin() -> None:
        while not stop.is_set():
            load()

    workers = [threading.Thread(target=spin, daemon=True) for _ in range(n)]
    for w in workers:
        w.start()
    time.sleep(0.2)  # let the load reach steady state
    try:
        return time_probe(probe, samples)
    finally:
        stop.set()
        for w in workers:
            w.join(timeout=30)


def with_child(probe: Callable[[], object], load_spec: str, n: int, samples: int, paths: list[str]) -> list[float]:
    code = (
        "import importlib, sys\n"
        f"sys.path[:0] = {paths!r}\n"
        f"m, _, f = {load_spec!r}.partition(':')\n"
        "fn = getattr(importlib.import_module(m), f)\n"
        "while True:\n    fn()\n"
    )
    env = dict(os.environ)
    children = [subprocess.Popen([sys.executable, "-c", code], env=env) for _ in range(n)]
    try:
        time.sleep(1.0)  # interpreter start + import
        for c in children:
            if c.poll() is not None:
                raise SystemExit(f"load child exited early (code {c.returncode}); check --load and --path")
        return time_probe(probe, samples)
    finally:
        for c in children:  # only the processes this run started
            c.terminate()
        for c in children:
            try:
                c.wait(timeout=10)
            except subprocess.TimeoutExpired:
                c.kill()


def fmt(xs: list[float]) -> str:
    return f"median {statistics.median(xs) * 1000:.1f} ms, max {max(xs) * 1000:.1f} ms, n={len(xs)}"


# --- demo: a syscall-heavy probe against a pure-Python load ----------------------------------

_DEMO_DIR = ""


def demo_probe() -> None:
    for d, _, files in os.walk(_DEMO_DIR):
        for f in files:
            os.stat(os.path.join(d, f))


def demo_load() -> None:
    total = 0
    for i in range(200_000):
        total += i * i % 7


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--probe")
    ap.add_argument("--load")
    ap.add_argument("--threads", type=int, default=1)
    ap.add_argument("--samples", type=int, default=30)
    ap.add_argument("--path", action="append", default=[])
    ap.add_argument("--demo", action="store_true", help="a 300-file walk against a busy loop")
    args = ap.parse_args(argv)
    sys.path[:0] = args.path

    global _DEMO_DIR
    tmp = None
    if args.demo:
        tmp = tempfile.TemporaryDirectory(prefix="contention-demo-")
        _DEMO_DIR = tmp.name
        for i in range(300):
            open(os.path.join(_DEMO_DIR, f"f{i}.txt"), "w").close()
        here = os.path.dirname(os.path.abspath(__file__))
        sys.path.insert(0, here)
        os.environ["CONTENTION_DEMO_DIR"] = _DEMO_DIR
        args.probe, args.load, args.path = "contention_bench:demo_probe", "contention_bench:demo_load", [here]
    if not (args.probe and args.load):
        ap.error("--probe and --load are required (or --demo)")

    probe, load = resolve(args.probe), resolve(args.load)
    if args.demo:
        sys.modules["contention_bench"]._DEMO_DIR = _DEMO_DIR  # type: ignore[attr-defined]
    probe()  # warm the page cache and imports once, untimed

    idle = time_probe(probe, args.samples)
    print(f"idle:                {fmt(idle)}", flush=True)
    inproc = with_threads(probe, load, args.threads, args.samples)
    print(f"load IN-process x{args.threads}:  {fmt(inproc)}", flush=True)
    child = with_child(probe, args.load, args.threads, args.samples, args.path)
    print(f"load in a CHILD x{args.threads}:  {fmt(child)}", flush=True)

    base, a, b = statistics.median(idle), statistics.median(inproc), statistics.median(child)
    ratio_in, ratio_child = a / base, b / base
    if ratio_in >= 5 and ratio_child < 2:
        verdict = "GIL STARVATION: in-process load slows the probe; a child process removes it"
    elif ratio_in >= 2:
        verdict = "CONTENTION: in-process load slows the probe (check CPU count before blaming the GIL)"
    else:
        verdict = "NO CONTENTION: the load does not explain the stall; look elsewhere"
    print(f"VERDICT {verdict} (in-process {ratio_in:.1f}x idle, child {ratio_child:.1f}x idle)", flush=True)
    if tmp:
        tmp.cleanup()
    return 0


if __name__ == "__main__":
    if os.environ.get("CONTENTION_DEMO_DIR"):
        _DEMO_DIR = os.environ["CONTENTION_DEMO_DIR"]
    sys.exit(main(sys.argv[1:]))
