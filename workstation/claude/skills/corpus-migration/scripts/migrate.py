#!/usr/bin/env python3
"""Corpus migrations on a prod box: preflight → dry run → gated apply (background, logged) → verify → ownership.

One job = ~/.local/state/corpus-migration/<job>/job.json (see SKILL.md) + ledger.jsonl + saved outputs.

  migrate.py JOB status | preflight | dry-run | apply --said "..." | watch | verify | ownership [--fix --said "..."]

- preflight (read-only): free disk >= need_gb, no busy container (a reprocess/sweep), not within
  guard_min of the nightly, and the pending list EQUALS expect_pending (an unexpected migration
  stops everything — ask its owner).
- dry-run: the CLI's own --dry-run; output saved; send its counts/refusals to the migration's owner
  before apply.
- apply: re-runs preflight, needs --said (the operator's words), starts the run in the background
  inside the container (an ssh drop cannot kill it), records the log path and the undo steps.
- watch: tails the log until the process ends; verify: `upgrade verify`; ownership: files under the
  corpus not owned by the corpus owner since the apply started (--fix chowns them, gated).

Exit: 0 ok · 1 refused / check failed · 4 usage
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import shlex
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(os.environ.get("CORPUS_MIGRATION_HOME", "~/.local/state/corpus-migration")).expanduser()


class Job:
    def __init__(self, name: str) -> None:
        self.dir = ROOT / name
        if not (self.dir / "job.json").is_file():
            sys.exit(f"no job '{name}': create {self.dir}/job.json (see SKILL.md)")
        self.c = json.loads((self.dir / "job.json").read_text())

    def log(self, **e: object) -> None:
        e = {"ts": now().isoformat(timespec="seconds"), **e}
        with (self.dir / "ledger.jsonl").open("a") as f:
            f.write(json.dumps(e) + "\n")
        print(f"[{e['ts']}] " + " ".join(f"{k}={v}" for k, v in e.items() if k != "ts"))

    def last(self, event: str) -> dict | None:
        p = self.dir / "ledger.jsonl"
        if not p.exists():
            return None
        hits = [json.loads(ln) for ln in p.read_text().splitlines() if f'"event": "{event}"' in ln]
        return hits[-1] if hits else None

    def ssh(self, remote: str, timeout: int = 600) -> subprocess.CompletedProcess[str]:
        cmd = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15"]
        if self.c.get("ssh_key"):
            cmd += ["-i", os.path.expanduser(self.c["ssh_key"]), "-o", "IdentitiesOnly=yes"]
        return subprocess.run(cmd + [self.c["ssh"], remote], capture_output=True, text=True, timeout=timeout)

    def cli(self, args: str) -> str:
        c = self.c
        return f"docker exec {c['container']} {c['cli']} {args} --corpus-dir {shlex.quote(c['corpus_dir_in_container'])}"

    def save(self, name: str, text: str) -> Path:
        p = self.dir / f"{now():%Y%m%dT%H%M%SZ}-{name}.txt"
        p.write_text(text)
        return p


def now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def pending(text: str) -> list[str]:
    block = text.split("Pending", 1)[1] if "Pending" in text else ""
    return re.findall(r"^\s*-\s*(\d{4}_[a-z0-9_]+)", block, re.M)


def cmd_status(job: Job, _: argparse.Namespace) -> int:
    r = job.ssh(job.cli("upgrade status"))
    print("\n".join(ln for ln in (r.stdout + r.stderr).splitlines() if "otel" not in ln))
    return r.returncode


def preflight(job: Job) -> list[str]:
    c = job.c
    bad = []
    df = job.ssh(f"df -BG --output=avail $(readlink -f {shlex.quote(c['corpus_dir_on_host'])}) | tail -1").stdout.strip()
    free = int(df.rstrip("G") or 0)
    print(f"free disk: {free} GB (need {c['need_gb']})")
    if free < c["need_gb"]:
        bad.append(f"only {free} GB free, need {c['need_gb']} (each run snapshots the corpus)")
    names = job.ssh("docker ps --format '{{.Names}}'").stdout.split()
    busy = [n for n in names if re.search(c["busy_container_regex"], n)]
    print(f"busy containers: {busy or 'none'}")
    if busy:
        bad.append(f"busy: {busy} — another job is rewriting the corpus")
    h, m = map(int, c["nightly_utc"].split(":"))
    t = now()
    nightly = t.replace(hour=h, minute=m, second=0, microsecond=0)
    gaps = [abs((nightly + dt.timedelta(days=d) - t).total_seconds()) / 60 for d in (-1, 0, 1)]
    print(f"nightly {c['nightly_utc']} UTC: {min(gaps):.0f} min away (guard {c['guard_min']})")
    if min(gaps) < c["guard_min"]:
        bad.append(f"within {c['guard_min']} min of the {c['nightly_utc']} UTC nightly")
    st = job.ssh(job.cli("upgrade status"))
    pend = pending(st.stdout + st.stderr)
    print(f"pending: {pend}  expected: {c['expect_pending']}")
    if pend != c["expect_pending"]:
        bad.append(f"pending {pend} != expected {c['expect_pending']} — stop and ask the migrations' owner")
    return bad


def cmd_preflight(job: Job, _: argparse.Namespace) -> int:
    bad = preflight(job)
    for b in bad:
        print(f"FAIL: {b}")
    print("PREFLIGHT " + ("FAIL" if bad else "PASS"))
    return 1 if bad else 0


def cmd_dry_run(job: Job, _: argparse.Namespace) -> int:
    r = job.ssh(job.cli("upgrade run --dry-run"), timeout=3600)
    text = "\n".join(ln for ln in (r.stdout + r.stderr).splitlines() if "otel_init" not in ln)
    p = job.save("dry-run", text)
    print(text)
    job.log(event="dry-run", exit=r.returncode, saved=str(p))
    print(f"\nsaved: {p}\nSend the counts and refusals to the migrations' owner BEFORE apply.")
    return r.returncode


def cmd_apply(job: Job, a: argparse.Namespace) -> int:
    if not job.last("dry-run"):
        print("REFUSED: no dry-run recorded for this job")
        return 1
    bad = preflight(job)
    if bad:
        print("REFUSED:\n  " + "\n  ".join(bad))
        return 1
    c = job.c
    ts = f"{now():%Y%m%dT%H%M%SZ}"
    log = f"/tmp/upgrade-{ts}.log"
    marker = f"/tmp/upgrade-{ts}.start"
    snap = f" --snapshot-dir {shlex.quote(c['snapshot_dir'])}" if c.get("snapshot_dir") else ""
    run = f"{c['cli']} upgrade run --yes --corpus-dir {shlex.quote(c['corpus_dir_in_container'])}{snap}"
    remote = (f"touch {marker} && docker exec -d {c['container']} sh -c "
              + shlex.quote(f"touch {marker}; {run} > {log} 2>&1; echo EXIT=$? >> {log}"))
    if a.dry_run:
        print(f"DRY-RUN would run on {c['ssh']}:\n  {remote}")
        return 0
    r = job.ssh(remote)
    if r.returncode != 0:
        print(f"start failed: {r.stderr.strip()}")
        return 1
    job.log(event="apply-started", said=a.said, log=log, marker=marker, expect=c["expect_pending"],
            undo=c.get("undo", "see the migrations' docs"))
    print(f"running in {c['container']}; `watch` follows {log}")
    return 0


def cmd_watch(job: Job, a: argparse.Namespace) -> int:
    s = job.last("apply-started")
    if not s:
        print("no apply recorded")
        return 1
    c = job.c
    seen = 0
    deadline = time.time() + a.max_hours * 3600
    while time.time() < deadline:
        out = job.ssh(f"docker exec {c['container']} cat {s['log']} 2>/dev/null").stdout.splitlines()
        for ln in out[seen:]:
            if "otel_init" not in ln:
                print(ln)
        seen = len(out)
        done = [ln for ln in out if ln.startswith("EXIT=")]
        if done:
            rc = int(done[-1].split("=")[1])
            job.log(event="apply-finished", exit=rc, log=s["log"])
            return 0 if rc == 0 else 1
        time.sleep(a.poll_s)
    print("watch bound reached; still running — run `watch` again")
    return 1


def cmd_verify(job: Job, _: argparse.Namespace) -> int:
    r = job.ssh(job.cli("upgrade verify"), timeout=3600)
    text = "\n".join(ln for ln in (r.stdout + r.stderr).splitlines() if "otel_init" not in ln)
    p = job.save("verify", text)
    print(text)
    job.log(event="verify", exit=r.returncode, saved=str(p))
    return r.returncode


def cmd_ownership(job: Job, a: argparse.Namespace) -> int:
    s = job.last("apply-started")
    if not s:
        print("no apply recorded")
        return 1
    c = job.c
    find = (f"docker exec {c['container']} find {shlex.quote(c['corpus_dir_in_container'])} -newer {s['marker']} "
            f"! -user {c['owner_uid']} -print")
    files = job.ssh(find, timeout=3600).stdout.split("\n")
    files = [f for f in files if f.strip()]
    print(f"{len(files)} files written since the apply and not owned by uid {c['owner_uid']}")
    for f in files[:20]:
        print(f"  {f}")
    if not files:
        print("OWNERSHIP PASS")
        return 0
    if not a.fix:
        print("OWNERSHIP FAIL — re-run with --fix --said '<operator go>' to chown them")
        return 1
    if not a.said:
        print("REFUSED: --fix needs --said")
        return 1
    fix = (f"docker exec {c['container']} find {shlex.quote(c['corpus_dir_in_container'])} -newer {s['marker']} "
           f"! -user {c['owner_uid']} -exec chown {c['owner_uid']}:{c['owner_gid']} {{}} +")
    r = job.ssh(fix, timeout=3600)
    job.log(event="ownership-fixed", n=len(files), said=a.said, exit=r.returncode)
    return r.returncode


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("job")
    sub = p.add_subparsers(dest="cmd", required=True)
    for n in ("status", "preflight", "dry-run", "verify"):
        sub.add_parser(n)
    ap = sub.add_parser("apply"); ap.add_argument("--said", required=True); ap.add_argument("--dry-run", action="store_true")
    w = sub.add_parser("watch"); w.add_argument("--max-hours", type=float, default=6); w.add_argument("--poll-s", type=int, default=60)
    o = sub.add_parser("ownership"); o.add_argument("--fix", action="store_true"); o.add_argument("--said")
    a = p.parse_args()
    job = Job(a.job)
    return {"status": cmd_status, "preflight": cmd_preflight, "dry-run": cmd_dry_run, "apply": cmd_apply,
            "watch": cmd_watch, "verify": cmd_verify, "ownership": cmd_ownership}[a.cmd](job, a)


if __name__ == "__main__":
    sys.exit(main())
