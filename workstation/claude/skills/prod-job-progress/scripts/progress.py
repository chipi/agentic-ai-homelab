#!/usr/bin/env python3
"""Progress + ETA of a running job container on a remote box, read-only, with no silent zeros.

Counts the job's OWN output files written since its container started (one --done-glob per
finished item, e.g. "*.gi.json"), against the worklist size (--expected). A zero is never reported
as "no progress": the same scan also counts every file written since the start and the container's
log lines, and a zero with activity elsewhere comes out as INCONCLUSIVE (the glob or the directory
is probably wrong), which is what a zero-result search usually means.

Usage:
  progress.py --ssh deploy@prod-podcast --key ~/.ssh/podcast_prod_operator \
      --container podcast-reprocess-39026409470 --dir /srv/podcast-scraper/corpus \
      --done-glob '*.gi.json' --expected 21

Exit: 0 report printed · 1 container not found · 2 INCONCLUSIVE
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import shlex
import subprocess
import sys

REMOTE = r"""
set -u
C=$1; DIR=$2; GLOB=$3; PAT=$4
st=$(docker inspect -f '{{.State.StartedAt}}' "$C" 2>/dev/null) || { echo '{"found": false}'; exit 0; }
status=$(docker inspect -f '{{.State.Status}} {{.State.ExitCode}}' "$C")
mark=$(mktemp); touch -d "$st" "$mark"
done_list=$(find "$DIR" -name "$GLOB" -newer "$mark" -printf '%T@ %p\n' 2>/dev/null | sort -n)
done_n=$(printf '%s' "$done_list" | grep -c . || true)
any_n=$(find "$DIR" -type f -newer "$mark" 2>/dev/null | wc -l)
first=$(printf '%s\n' "$done_list" | head -1 | cut -d' ' -f1)
last=$(printf '%s\n' "$done_list" | tail -1 | cut -d' ' -f1)
logs=$(docker logs "$C" 2>&1)
log_n=$(printf '%s\n' "$logs" | wc -l)
err_n=$(printf '%s\n' "$logs" | grep -cE "$PAT" || true)
last_log=$(printf '%s\n' "$logs" | tail -1 | cut -c1-160)
rm -f "$mark"
python3 - "$st" "$status" "$done_n" "$any_n" "$first" "$last" "$log_n" "$err_n" "$last_log" <<'PY'
import json, sys
k = ["started", "status", "done", "any_files", "first_done", "last_done", "log_lines", "problem_lines", "last_log"]
v = dict(zip(k, sys.argv[1:]))
for n in ("done", "any_files", "log_lines", "problem_lines"):
    v[n] = int(v[n] or 0)
print(json.dumps({"found": True, **v}))
PY
"""


def parse_ts(s: str) -> dt.datetime:
    s = s.strip().replace("Z", "+00:00")
    if "." in s:  # docker gives nanoseconds; Python takes microseconds
        head, frac = s.split(".", 1)
        tz = frac[frac.find("+"):] if "+" in frac else ""
        s = f"{head}.{frac[:6]}{tz}"
    return dt.datetime.fromisoformat(s)


def report(r: dict, expected: int | None, now: dt.datetime) -> tuple[str, int]:
    if not r.get("found"):
        return "container not found (finished and removed? wrong name?)", 1
    started = parse_ts(r["started"])
    elapsed_h = (now - started).total_seconds() / 3600
    lines = [f"container {r['status']}, started {started:%H:%M} UTC ({elapsed_h:.1f} h ago)",
             f"last log line: {r['last_log']}",
             f"problem lines (Traceback/Killed/ERROR pattern): {r['problem_lines']}"]
    done = r["done"]
    if done == 0:
        if r["any_files"] or r["log_lines"] > 50:
            lines.append(f"done: 0 by the glob, but {r['any_files']} files were written and {r['log_lines']} log lines "
                         "logged since the start — INCONCLUSIVE: the glob or directory is probably wrong, not the job")
            return "\n".join(lines), 2
        lines.append(f"done: 0, and nothing else written ({r['log_lines']} log lines) — no output yet")
        return "\n".join(lines), 0
    first = dt.datetime.fromtimestamp(float(r["first_done"]), dt.timezone.utc)
    last = dt.datetime.fromtimestamp(float(r["last_done"]), dt.timezone.utc)
    lines.append(f"done: {done}{f' of {expected}' if expected else ''} (first {first:%H:%M}, last {last:%H:%M} UTC)")
    rate_h = done / max(elapsed_h, 1e-6)
    lines.append(f"rate: {rate_h:.1f}/h over the whole run")
    if expected and expected > done:
        eta = now + dt.timedelta(hours=(expected - done) / rate_h)
        lines.append(f"ETA (count-based, assumes the rest are like the done ones): ~{eta:%H:%M} UTC")
        lines.append("caveat: items differ in size; weight by the pool's minutes when they do")
    return "\n".join(lines), 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--ssh", required=True)
    p.add_argument("--key")
    p.add_argument("--container", required=True)
    p.add_argument("--dir", required=True)
    p.add_argument("--done-glob", required=True)
    p.add_argument("--expected", type=int)
    p.add_argument("--problem-pattern", default=r"Traceback \(most recent call last\)|Killed process| ERROR ")
    p.add_argument("--json", action="store_true")
    a = p.parse_args()
    cmd = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15"]
    if a.key:
        cmd += ["-i", os.path.expanduser(a.key), "-o", "IdentitiesOnly=yes"]
    remote_args = " ".join(shlex.quote(x) for x in (a.container, a.dir, a.done_glob, a.problem_pattern))
    out = subprocess.run(cmd + [a.ssh, f"bash -s -- {remote_args}"], input=REMOTE, capture_output=True, text=True)
    if out.returncode != 0 or not out.stdout.strip():
        print(f"ssh failed (exit {out.returncode}): {out.stderr.strip()[:300]}")
        return 1
    r = json.loads(out.stdout.strip().splitlines()[-1])
    if a.json:
        print(json.dumps(r))
    text, rc = report(r, a.expected, dt.datetime.now(dt.timezone.utc))
    print(text)
    return rc


if __name__ == "__main__":
    sys.exit(main())
