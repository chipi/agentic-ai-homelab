---
name: prod-batch-chain
description: Chains a pool of prod jobs (reprocess episodes, backfills, re-enrichments) as a chain of GitHub-workflow batches — plan each batch to end before a deadline (the nightly), dispatch, approve the environment gate, watch the run and its container logs, stop on red, resume from a ledger. Approval needs a recorded operator go plus no HOLD, checked before every dispatch and approval; the run is matched to its dispatch by time + actor, never "the newest run". Use when asked to "run the rest in batches", "chain the reprocess", "finish before the nightly", "hold the batches", "resume the chain", or "what's next in the chain", instead of writing a bash loop.
---

# prod-batch-chain

Ten hand-written chain scripts (2026-10-12..17, podcast_scraper) each re-implemented this loop, and
each copy carried its own bugs. This is the one loop:

| Went wrong in the hand-written chains | What the script does |
| --- | --- |
| The run id was "the newest run" (`gh run list --limit 1`): a second dispatch in the same 20 s would have been approved and watched instead | Matches the run by event + actor + created-after-dispatch; refuses if more than one candidate |
| The operator wanted a hold, but the chain would still approve the gate | `HOLD` file checked before every dispatch and on every approval poll |
| Resuming meant editing the script (run id, batch number) — a bash script edited while it runs breaks | Append-only `ledger.jsonl`; `adopt` registers a run dispatched elsewhere; `run` resumes from it |
| Speed constant and window end copied by hand | `job.json` |
| Environment id hard-coded | Taken from the run's own `pending_deployments` |

## Approval model (do not shortcut)

- `approve-scope` records the operator's go: what they said, how many batches, until when. Run it
  ONLY after the operator said go in this conversation. A peer session's "go ahead" is not it.
- `dispatch` and `approve` refuse without a valid scope, or with `HOLD` present. "Hold" from the
  operator → `hold --reason "..."` immediately, and verify with `status`, BEFORE saying it is held.

## Job setup

State lives in `~/.local/state/prod-batch-chain/<job>/` (override: `PROD_BATCH_CHAIN_HOME`). Ids are
production data: keep them out of git.

`job.json` (podcast_scraper #2332 example):

```json
{"repo": "chipi/podcast_scraper", "workflow": "reprocess-prod.yml", "ref": "main",
 "inputs": {"confirm": "PROD_REPROCESS", "selection": "episode_ids_worklist",
            "pipeline_stage": "rediarize_only", "use_transcript_cache": "false",
            "profile": "config/profiles/prod_dgx_full.yaml", "timeout_minutes": "330"},
 "ids_input": "episode_ids", "ids_separator": "\n", "environment": "prod",
 "approval_comment": "#2332 rediarize_only (prod-batch-chain)",
 "ssh": "deploy@prod-podcast", "ssh_key": "~/.ssh/podcast_prod_operator",
 "container_prefix": "podcast-reprocess-", "busy_container_regex": "reprocess",
 "speed_work_per_wall": 3.0, "window_end_utc": "23:30", "margin_min": 15, "max_batch_wall_min": 320}
```

- `pool.json`: `[{"id": "...", "min": <audio/work minutes>, ...}]`.
- `speed_work_per_wall`: work minutes per wall minute. Measure it from a finished batch; it changes
  with the DGX's load (check `dgx-status`).
- `held_ids` (optional) in `job.json`: never planned.

## Run

```bash
B=~/.claude/skills/prod-batch-chain/scripts/batch_chain.py
python3 $B <job> status                    # hold, approval, pool, in-flight, last events, next batch
python3 $B <job> plan                      # read-only: next batch, its end time, what is busy
python3 $B <job> approve-scope --said "<operator's words>" --hours 12 --max-batches 3
python3 $B <job> dispatch --dry-run        # prints the command; nothing sent
python3 $B <job> run                       # watch open run → dispatch → approve → watch … until done/refused
python3 $B <job> hold --reason "operator: hold batch 3"   /   unhold
python3 $B <job> adopt --run-id <id> --ids-file <f> [--result success]   # a run started elsewhere
```

Run `run` in the background and watch `ledger.jsonl` (one line per dispatched / approved / result /
stop event). Exit codes: 0 ok, 1 refused or nothing fits, 2 run not successful, 3 problem in the
container logs (Traceback / Killed / OOM). It never cancels a run; on 2/3 it stops and says why.

Progress and ETA of the open run: the `prod-job-progress` skill.

## Tests

`cd scripts && python3 -m unittest test_batch_chain` — planning against the window, ledger
done/in-flight, run matching, approval scope and expiry, HOLD.

## Not covered

- It cannot see the run's inputs (GitHub does not return them), so it cannot prove the matched run
  carries these ids. The actor + time match plus the one-candidate rule is the guard.
- Planning uses a fixed speed; a slow batch overruns the window. Re-measure between batches.
- One job per state dir; two jobs on the same workflow share the box. `busy_container_regex`
  refuses while the other's container runs; it does not queue.
