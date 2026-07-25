#!/usr/bin/env python3
"""CI/DORA poller — GitHub Actions API -> VictoriaLogs (ops_event/v1).

Tier-2 of the CI-ops observability design (homelab handover, ADR-119). Tier-1
workflows already push ops_events from inside the runner (they join the tailnet);
this poller covers the ones that DON'T — CI, infra-drift, and DR-drill runs — by
*pulling* the GitHub Actions API and emitting the same `ops_event/v1` schema to
VictoriaLogs, so CI health + DORA metrics sit on the same Grafana pane.

Design notes:
- stdlib only (urllib/json) — no pip deps; runs under launchd on the mini like
  the mini-metrics / dgx-scrape loops.
- The repo has ~7k+ runs, so we NEVER full-scan: a persisted cursor (`since`)
  bounds each query with `created=>{since}`, and a `seen` set of
  `run_id:run_attempt` dedups (VictoriaLogs is append-only). A re-run bumps
  run_attempt -> a new, un-seen event = the flaky signal.
- Tier-1 workflows are skipped here (they'd double-count against the push path).

Config: environment, overlaid by a co-located `.env` (see .env.example).
"""
import json
import os
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))


def load_env():
    """Environment wins; fall back to a co-located .env (KEY=VALUE lines)."""
    cfg = {}
    envfile = os.path.join(HERE, ".env")
    if os.path.exists(envfile):
        with open(envfile) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                # strip a trailing inline comment (whitespace + '#'); our values
                # never contain '#', so this is safe and keeps .env self-documenting
                for i, ch in enumerate(v):
                    if ch == "#" and (i == 0 or v[i - 1] in " \t"):
                        v = v[:i]
                        break
                cfg[k.strip()] = v.strip().strip('"').strip("'")
    cfg.update({k: v for k, v in os.environ.items()})
    return cfg


CFG = load_env()
REPO = CFG.get("GITHUB_REPO", "chipi/podcast_scraper")
TOKEN = CFG.get("GITHUB_TOKEN", "")
VLOGS = CFG.get("VLOGS_URL", "http://localhost:9428").rstrip("/")
INTERVAL = int(CFG.get("POLL_INTERVAL", "900"))          # seconds between polls
LOOKBACK_H = int(CFG.get("LOOKBACK_HOURS", "24"))        # first-run window
OVERLAP_MIN = int(CFG.get("OVERLAP_MINUTES", "120"))     # re-scan window (late completions)
SEEN_TTL_DAYS = int(CFG.get("SEEN_TTL_DAYS", "7"))       # prune dedup set
APP = CFG.get("OPS_APP", "podcast_scraper")
ENV = CFG.get("OPS_ENV", "ci")                           # stream field; Tier-1 deploys use "prod"
STATE_FILE = CFG.get("STATE_FILE", os.path.join(HERE, "state.json"))
ONCE = "--once" in sys.argv or CFG.get("POLL_ONCE") == "1"

# Workflows already covered by the Tier-1 push path — skip so we don't double-count.
SKIP = set(w.strip() for w in CFG.get(
    "SKIP_WORKFLOWS",
    "deploy-prod.yml,deploy-player.yml,backup-corpus-prod.yml,backup-player-appdata-prod.yml",
).split(",") if w.strip())


def classify(path):
    """Map a workflow file path -> ops event_type, or None to skip."""
    base = path.rsplit("/", 1)[-1]
    if not path.startswith(".github/workflows/"):
        return None                      # dynamic/dependabot etc. — not a tracked workflow
    if base in SKIP:
        return None
    low = base.lower()
    if "drift" in low:
        return "drift"
    if "drill" in low:
        return "drill"
    return "ci_run"


def parse_ts(s):
    if not s:
        return None
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def gh_get(path):
    req = urllib.request.Request("https://api.github.com" + path)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    req.add_header("User-Agent", "homelab-ci-ops-poller")
    if TOKEN:
        req.add_header("Authorization", "Bearer " + TOKEN)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def fetch_runs(since_iso):
    """All runs created since `since_iso`, paginated (newest-first from the API)."""
    runs, page = [], 1
    while page <= 20:                    # 20*100 = 2000 run safety cap per poll
        q = f"/repos/{REPO}/actions/runs?created=%3E{since_iso}&per_page=100&page={page}"
        data = gh_get(q)
        batch = data.get("workflow_runs", [])
        runs.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    return runs


def to_event(run, event_type):
    created = parse_ts(run.get("created_at"))
    started = parse_ts(run.get("run_started_at"))
    updated = parse_ts(run.get("updated_at"))
    ev = {
        "_time": run.get("updated_at") or run.get("created_at"),
        "schema": "ops_event/v1",
        "event_type": event_type,
        "app": APP,
        "env": ENV,
        "status": run.get("conclusion") or "unknown",
        "workflow": run.get("name"),
        "branch": run.get("head_branch"),
        "event": run.get("event"),
        "sha": (run.get("head_sha") or "")[:7],
        "run_id": str(run.get("id")),
        "attempt": str(run.get("run_attempt")),
        "_msg": f"{event_type} {run.get('conclusion')} {run.get('name')} "
                f"#{run.get('id')}.{run.get('run_attempt')}",
    }
    if started and updated:
        ev["duration_ms"] = str(int((updated - started).total_seconds() * 1000))
    if started and created:
        ev["queue_ms"] = str(int((started - created).total_seconds() * 1000))
    return ev


def emit(events):
    """POST newline-delimited ops_event/v1 to VictoriaLogs jsonline ingest."""
    if not events:
        return
    body = "\n".join(json.dumps(e) for e in events).encode()
    url = (VLOGS + "/insert/jsonline"
           "?_stream_fields=app,env,event_type&_time_field=_time&_msg_field=_msg")
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Content-Type", "application/stream+json")
    with urllib.request.urlopen(req, timeout=30) as r:
        r.read()


def load_state():
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {"since": None, "seen": {}}


def save_state(state):
    tmp = STATE_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(state, f)
    os.replace(tmp, STATE_FILE)


def poll_once(state):
    now = datetime.now(timezone.utc)
    since_dt = parse_ts(state.get("since")) or (now - timedelta(hours=LOOKBACK_H))
    # re-scan an overlap window to catch runs that completed after we last saw them
    since_dt = min(since_dt, now - timedelta(minutes=OVERLAP_MIN))
    since_iso = since_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    seen = state.get("seen", {})
    runs = fetch_runs(since_iso)
    events, emitted = [], 0
    for run in runs:
        if run.get("status") != "completed":
            continue                     # no conclusion yet — pick it up next poll
        et = classify(run.get("path", ""))
        if et is None:
            continue
        key = f"{run.get('id')}:{run.get('run_attempt')}"
        if key in seen:
            continue
        events.append(to_event(run, et))
        seen[key] = run.get("created_at")
        emitted += 1

    emit(events)

    # prune dedup set; advance cursor to now minus the overlap window
    cutoff = (now - timedelta(days=SEEN_TTL_DAYS))
    seen = {k: v for k, v in seen.items()
            if (parse_ts(v) or now) >= cutoff}
    state["seen"] = seen
    state["since"] = (now - timedelta(minutes=OVERLAP_MIN)).strftime("%Y-%m-%dT%H:%M:%SZ")
    save_state(state)
    print(f"[{now.isoformat(timespec='seconds')}] scanned={len(runs)} "
          f"emitted={emitted} seen={len(seen)}", flush=True)


def main():
    if not TOKEN:
        print("WARN: GITHUB_TOKEN not set — API is rate-limited to 60 req/h "
              "unauthenticated and private repos are invisible. Set it in .env.",
              file=sys.stderr, flush=True)
    while True:
        try:
            poll_once(load_state())
        except urllib.error.HTTPError as e:
            print(f"HTTPError {e.code}: {e.reason}", file=sys.stderr, flush=True)
        except Exception as e:                       # keep the daemon alive
            print(f"poll error: {e!r}", file=sys.stderr, flush=True)
        if ONCE:
            break
        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()
