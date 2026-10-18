#!/usr/bin/env python3
"""Run a pool of prod jobs as GitHub-workflow batches: plan, dispatch, approve, watch, resume.

One job = one state directory (default ~/.local/state/prod-batch-chain/<job>/):
  job.json       config (see SKILL.md): repo, workflow, fixed inputs, ids input, environment,
                 ssh target, container prefix, speed, window end
  pool.json      [{"id": ..., "min": <audio or work minutes>, ...}, ...]
  ledger.jsonl   append-only: planned / dispatched / approved / result / stop events
  approval.json  the operator's go, written by `approve-scope` ONLY after the operator said go
  HOLD           exists = never dispatch or approve; checked before every mutating step

Mutating steps (dispatch, approve) need a valid approval.json and no HOLD, every time. A run is
matched to its dispatch by creation time + event + actor, never by "newest run": anything else
dispatched in the same window makes the match ambiguous and the step refuses.

Exit: 0 ok (for `run`: the pool is done) · 1 refused / nothing fits · 2 run not successful ·
3 problem seen in logs · 4 usage
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

STATE_ROOT = Path(os.environ.get("PROD_BATCH_CHAIN_HOME", "~/.local/state/prod-batch-chain")).expanduser()
PROBLEM = re.compile(r"Traceback \(most recent call last\)|Killed process|MemoryError|OOMKilled")


# ---------------------------------------------------------------- state
class Job:
    def __init__(self, name: str) -> None:
        self.dir = STATE_ROOT / name
        if not (self.dir / "job.json").is_file():
            sys.exit(f"no job '{name}': create {self.dir}/job.json (see SKILL.md)")
        self.cfg = json.loads((self.dir / "job.json").read_text())
        self.ledger_path = self.dir / "ledger.jsonl"

    def pool(self) -> list[dict]:
        return json.loads((self.dir / "pool.json").read_text())

    def ledger(self) -> list[dict]:
        if not self.ledger_path.exists():
            return []
        return [json.loads(ln) for ln in self.ledger_path.read_text().splitlines() if ln.strip()]

    def log(self, **event: object) -> None:
        event = {"ts": now().isoformat(timespec="seconds"), **event}
        with self.ledger_path.open("a") as f:
            f.write(json.dumps(event) + "\n")
        print(f"[{event['ts']}] " + " ".join(f"{k}={v}" for k, v in event.items() if k not in ("ts", "ids")))

    def held(self) -> bool:
        return (self.dir / "HOLD").exists()

    def approval(self) -> tuple[bool, str]:
        p = self.dir / "approval.json"
        if not p.exists():
            return False, "no approval.json (the operator has not given a go for this job)"
        a = json.loads(p.read_text())
        if now() > dt.datetime.fromisoformat(a["until"]):
            return False, f"approval expired at {a['until']}"
        used = sum(1 for e in self.ledger()
                   if e["event"] == "dispatched" and not e.get("adopted") and e["ts"] >= a["given"])
        if used >= a["max_batches"]:
            return False, f"approval covered {a['max_batches']} batch(es); {used} dispatched since"
        return True, f"approval: \"{a['said']}\" (until {a['until']}, {used}/{a['max_batches']} used)"

    def done_ids(self) -> set[str]:
        """Ids in a batch that succeeded, or one still in flight (never re-plan those)."""
        batches: dict[str, dict] = {}
        for e in self.ledger():
            if e["event"] == "dispatched":
                batches[str(e["run_id"])] = {"ids": e["ids"], "result": None}
            elif e["event"] == "result" and str(e["run_id"]) in batches:
                batches[str(e["run_id"])]["result"] = e["conclusion"]
        out: set[str] = set()
        for b in batches.values():
            if b["result"] in (None, "success"):
                out |= set(b["ids"])
        return out

    def in_flight(self) -> str | None:
        runs = [str(e["run_id"]) for e in self.ledger() if e["event"] == "dispatched"]
        finished = {str(e["run_id"]) for e in self.ledger() if e["event"] == "result"}
        open_runs = [r for r in runs if r not in finished]
        return open_runs[-1] if open_runs else None


def now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def sh(cmd: list[str], check: bool = True) -> str:
    r = subprocess.run(cmd, capture_output=True, text=True)
    if check and r.returncode != 0:
        raise RuntimeError(f"{' '.join(cmd[:4])}… exit {r.returncode}: {r.stderr.strip()[:400]}")
    return r.stdout


def ssh(job: Job, remote: str) -> str:
    c = job.cfg
    cmd = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15"]
    if c.get("ssh_key"):
        cmd += ["-i", os.path.expanduser(c["ssh_key"]), "-o", "IdentitiesOnly=yes"]
    return sh(cmd + [c["ssh"], remote], check=False)


def gh_json(args: list[str]) -> object:
    return json.loads(sh(["gh", *args]) or "null")


# ---------------------------------------------------------------- planning
def plan_batch(job: Job, at: dt.datetime | None = None) -> tuple[list[dict], str]:
    c = job.cfg
    at = at or now()
    done = job.done_ids()
    held = set(c.get("held_ids", []))
    left = sorted((x for x in job.pool() if x["id"] not in done | held), key=lambda x: -x["min"])
    if not left:
        return [], "pool done"
    end_h, end_m = map(int, c["window_end_utc"].split(":"))
    end = at.replace(hour=end_h, minute=end_m, second=0, microsecond=0)
    if end <= at:
        end += dt.timedelta(days=1)
    wall_left = (end - at).total_seconds() / 60 - c.get("margin_min", 15)
    cap = min(c.get("max_batch_wall_min", 320), wall_left) * c["speed_work_per_wall"]
    batch: list[dict] = []
    for x in left:
        if sum(y["min"] for y in batch) + x["min"] <= cap:
            batch.append(x)
    work = sum(x["min"] for x in batch)
    if not batch:
        return [], f"nothing fits before {c['window_end_utc']} UTC: {len(left)} left, {sum(x['min'] for x in left)/60:.1f} h of work"
    eta = at + dt.timedelta(minutes=work / c["speed_work_per_wall"])
    return batch, (
        f"{len(batch)} items, {work/60:.1f} h of work (cap {cap/60:.1f} h), est. wall "
        f"{work / c['speed_work_per_wall'] / 60:.1f} h -> ends ~{eta:%H:%M} UTC; left after: {len(left) - len(batch)}"
    )


def busy(job: Job) -> list[str]:
    rx = job.cfg.get("busy_container_regex")
    if not rx:
        return []
    names = ssh(job, "docker ps --format '{{.Names}}'").split()
    return [n for n in names if re.search(rx, n)]


# ---------------------------------------------------------------- run matching
def match_run(runs: list[dict], since: dt.datetime, actor: str) -> list[dict]:
    """Runs this dispatch could have created: workflow_dispatch, by us, created after `since`."""
    out = []
    for r in runs:
        created = dt.datetime.fromisoformat(r["createdAt"].replace("Z", "+00:00"))
        if r.get("event") == "workflow_dispatch" and created >= since and r.get("actor") == actor:
            out.append(r)
    return out


def find_dispatched_run(job: Job, since: dt.datetime) -> str:
    c = job.cfg
    me = sh(["gh", "api", "user", "-q", ".login"]).strip()
    for _ in range(12):
        time.sleep(10)
        runs = gh_json(["run", "list", "-R", c["repo"], "--workflow", c["workflow"], "--limit", "20",
                        "--json", "databaseId,createdAt,event,status"])
        cands = []
        for r in runs:  # type: ignore[union-attr]
            created = dt.datetime.fromisoformat(r["createdAt"].replace("Z", "+00:00"))
            if r["event"] == "workflow_dispatch" and created >= since:
                actor = sh(["gh", "api", f"repos/{c['repo']}/actions/runs/{r['databaseId']}", "-q", ".actor.login"]).strip()
                cands.append({**r, "actor": actor})
        mine = match_run(cands, since, me)
        if len(mine) == 1:
            return str(mine[0]["databaseId"])
        if len(mine) > 1:
            raise RuntimeError(f"ambiguous: {len(mine)} runs of {c['workflow']} dispatched by {me} since {since:%H:%M:%S}: "
                               + ", ".join(str(r["databaseId"]) for r in mine) + " — refusing to guess")
    raise RuntimeError(f"no run of {c['workflow']} by {me} appeared within 2 min of the dispatch")


# ---------------------------------------------------------------- commands
def gate(job: Job) -> None:
    if job.held():
        print(f"HOLD: {job.dir/'HOLD'} exists — not dispatching or approving. `unhold` to resume.")
        sys.exit(1)
    ok, why = job.approval()
    if not ok:
        print(f"REFUSED: {why}")
        sys.exit(1)
    print(why)


def cmd_plan(job: Job, _: argparse.Namespace) -> int:
    batch, msg = plan_batch(job)
    print(msg)
    b = busy(job)
    if b:
        print(f"busy on the box: {', '.join(b)} (dispatch would refuse)")
    if job.in_flight():
        print(f"in flight: run {job.in_flight()} (dispatch would refuse)")
    if batch:
        print("ids: " + " ".join(x["id"] for x in batch))
    return 0 if batch else 1


def cmd_dispatch(job: Job, args: argparse.Namespace) -> int:
    gate(job)
    if job.in_flight():
        print(f"REFUSED: run {job.in_flight()} is still open in the ledger")
        return 1
    if busy(job):
        print(f"REFUSED: busy on the box: {', '.join(busy(job))}")
        return 1
    batch, msg = plan_batch(job)
    print(msg)
    if not batch:
        return 1
    c = job.cfg
    ids = [x["id"] for x in batch]
    fields = [f"{k}={v}" for k, v in c["inputs"].items()] + [f"{c['ids_input']}={c.get('ids_separator', ' ').join(ids)}"]
    cmd = ["gh", "workflow", "run", c["workflow"], "-R", c["repo"], "--ref", c.get("ref", "main")]
    for f in fields:
        cmd += ["-f", f]
    if args.dry_run:
        print("DRY-RUN would run: " + " ".join(cmd[:8]) + f" … ({len(ids)} ids)")
        return 0
    since = now() - dt.timedelta(seconds=5)
    sh(cmd)
    run_id = find_dispatched_run(job, since)
    job.log(event="dispatched", run_id=run_id, n=len(ids), work_min=sum(x["min"] for x in batch), ids=ids)
    print(f"https://github.com/{c['repo']}/actions/runs/{run_id}")
    return 0


def cmd_approve(job: Job, args: argparse.Namespace) -> int:
    run_id = args.run_id or job.in_flight()
    if not run_id:
        print("REFUSED: no open run in the ledger")
        return 1
    if run_id not in {str(e["run_id"]) for e in job.ledger() if e["event"] == "dispatched"}:
        print(f"REFUSED: run {run_id} is not in this job's ledger (`adopt` it first)")
        return 1
    c = job.cfg
    for _ in range(int(args.wait_s / 15) + 1):
        gate(job)  # re-checked on every poll: a HOLD placed while waiting stops the approval
        pend = gh_json(["api", f"repos/{c['repo']}/actions/runs/{run_id}/pending_deployments"])
        envs = [p["environment"] for p in pend or []]  # type: ignore[union-attr]
        if envs:
            if [e["name"] for e in envs] != [c["environment"]]:
                print(f"REFUSED: run {run_id} waits on {[e['name'] for e in envs]}, expected [{c['environment']}]")
                return 1
            if args.dry_run:
                print(f"DRY-RUN would approve run {run_id} for {c['environment']} (id {envs[0]['id']})")
                return 0
            sh(["gh", "api", "-X", "POST", f"repos/{c['repo']}/actions/runs/{run_id}/pending_deployments",
                "-F", f"environment_ids[]={envs[0]['id']}", "-f", "state=approved",
                "-f", f"comment={c.get('approval_comment', 'prod-batch-chain')}: {json.loads((job.dir/'approval.json').read_text())['said']}"])
            states = gh_json(["api", f"repos/{c['repo']}/actions/runs/{run_id}/approvals"])
            if not any(a["state"] == "approved" for a in states or []):  # type: ignore[union-attr]
                print(f"approval POST returned but run {run_id} shows no approval")
                return 1
            job.log(event="approved", run_id=run_id, environment=c["environment"])
            return 0
        status = gh_json(["run", "view", run_id, "-R", c["repo"], "--json", "status"])["status"]  # type: ignore[index]
        if status in ("in_progress", "completed"):
            print(f"run {run_id} is {status}: no gate to approve")
            return 0
        time.sleep(15)
    print(f"run {run_id}: no pending deployment after {args.wait_s}s")
    return 1


def cmd_watch(job: Job, args: argparse.Namespace) -> int:
    run_id = args.run_id or job.in_flight()
    if not run_id:
        print("no open run")
        return 1
    c = job.cfg
    container = f"{c.get('container_prefix', '')}{run_id}"
    deadline = time.time() + args.max_hours * 3600
    while time.time() < deadline:
        v = gh_json(["run", "view", run_id, "-R", c["repo"], "--json", "status,conclusion"])
        if v["status"] == "completed":  # type: ignore[index]
            concl = v["conclusion"]  # type: ignore[index]
            job.log(event="result", run_id=run_id, conclusion=concl)
            return 0 if concl == "success" else 2
        if c.get("container_prefix"):
            hit = ssh(job, f"docker logs {container} 2>&1 | grep -m1 -E '{PROBLEM.pattern}'").strip()
            if hit:
                job.log(event="stop", run_id=run_id, reason=f"problem in {container} logs: {hit[:160]}")
                return 3
        time.sleep(args.poll_s)
    print(f"watch bound ({args.max_hours} h) reached; run {run_id} still open — re-run `watch`")
    return 1


def cmd_run(job: Job, args: argparse.Namespace) -> int:
    """The loop: watch whatever is open, then plan/dispatch/approve/watch until done or refused."""
    while True:
        if job.in_flight():
            rc = cmd_watch(job, argparse.Namespace(run_id=None, max_hours=args.max_hours, poll_s=args.poll_s))
            if rc != 0:
                print("STOP: last batch did not succeed (see ledger)")
                return rc
            for _ in range(40):  # let the job container tear down before the next dispatch
                if not busy(job):
                    break
                time.sleep(30)
        if not (set(x["id"] for x in job.pool()) - job.done_ids() - set(job.cfg.get("held_ids", []))):
            print("pool done")  # the chain finished its work: success, not a refusal
            return 0
        rc = cmd_dispatch(job, argparse.Namespace(dry_run=False))
        if rc != 0:
            return rc
        rc = cmd_approve(job, argparse.Namespace(run_id=None, wait_s=900, dry_run=False))
        if rc != 0:
            return rc


def cmd_adopt(job: Job, args: argparse.Namespace) -> int:
    ids = Path(args.ids_file).read_text().split()
    pool = {x["id"]: x for x in job.pool()}
    missing = [i for i in ids if i not in pool]
    if missing:
        print(f"REFUSED: {len(missing)} ids not in pool.json, e.g. {missing[:3]}")
        return 1
    job.log(event="dispatched", run_id=args.run_id, n=len(ids), work_min=sum(pool[i]["min"] for i in ids), ids=ids, adopted=True)
    if args.result:
        job.log(event="result", run_id=args.run_id, conclusion=args.result)
    return 0


def cmd_approve_scope(job: Job, args: argparse.Namespace) -> int:
    a = {"said": args.said, "given": now().isoformat(timespec="seconds"),
         "until": (now() + dt.timedelta(hours=args.hours)).isoformat(timespec="seconds"),
         "max_batches": args.max_batches}
    (job.dir / "approval.json").write_text(json.dumps(a, indent=1) + "\n")
    print(f"recorded: {a}")
    return 0


def cmd_hold(job: Job, args: argparse.Namespace) -> int:
    (job.dir / "HOLD").write_text(f"{now().isoformat(timespec='seconds')} {args.reason}\n")
    job.log(event="hold", reason=args.reason)
    return 0


def cmd_unhold(job: Job, _: argparse.Namespace) -> int:
    (job.dir / "HOLD").unlink(missing_ok=True)
    job.log(event="unhold")
    return 0


def cmd_status(job: Job, _: argparse.Namespace) -> int:
    print(f"job dir: {job.dir}")
    print(f"HOLD: {'yes — ' + (job.dir/'HOLD').read_text().strip() if job.held() else 'no'}")
    print(job.approval()[1])
    pool = job.pool()
    done = job.done_ids()
    print(f"pool: {len(pool)} items, {sum(x['min'] for x in pool)/60:.1f} h; done or in flight: {len(done & {x['id'] for x in pool})}")
    print(f"in flight: {job.in_flight() or 'none'}")
    for e in job.ledger()[-8:]:
        print("  " + " ".join(f"{k}={v}" for k, v in e.items() if k != "ids"))
    batch, msg = plan_batch(job)
    print(f"next: {msg}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("job")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status")
    sub.add_parser("plan")
    d = sub.add_parser("dispatch"); d.add_argument("--dry-run", action="store_true")
    a = sub.add_parser("approve"); a.add_argument("--run-id"); a.add_argument("--wait-s", type=int, default=900); a.add_argument("--dry-run", action="store_true")
    w = sub.add_parser("watch"); w.add_argument("--run-id"); w.add_argument("--max-hours", type=float, default=8); w.add_argument("--poll-s", type=int, default=60)
    r = sub.add_parser("run"); r.add_argument("--max-hours", type=float, default=8); r.add_argument("--poll-s", type=int, default=60)
    ad = sub.add_parser("adopt"); ad.add_argument("--run-id", required=True); ad.add_argument("--ids-file", required=True); ad.add_argument("--result")
    s = sub.add_parser("approve-scope"); s.add_argument("--said", required=True); s.add_argument("--hours", type=float, required=True); s.add_argument("--max-batches", type=int, required=True)
    h = sub.add_parser("hold"); h.add_argument("--reason", required=True)
    sub.add_parser("unhold")
    args = p.parse_args()
    job = Job(args.job)
    fn = {"status": cmd_status, "plan": cmd_plan, "dispatch": cmd_dispatch, "approve": cmd_approve,
          "watch": cmd_watch, "run": cmd_run, "adopt": cmd_adopt, "approve-scope": cmd_approve_scope,
          "hold": cmd_hold, "unhold": cmd_unhold}[args.cmd]
    try:
        return fn(job, args)
    except RuntimeError as e:
        print(f"ERROR: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
