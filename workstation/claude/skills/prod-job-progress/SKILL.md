---
name: prod-job-progress
description: Progress and ETA of a running job container on a remote box (a prod reprocess batch, a backfill, a migration) — counts the job's own output files written since the container started against the worklist, last log line, Traceback/Killed counts, rate and ETA. Never reports a zero as "no progress": a zero with other files or log lines written comes out INCONCLUSIVE (wrong glob or directory). Read-only. Use when asked "how is it going", "what's the ETA", "is the batch stuck", "how far along is X", before answering from an ad-hoc ssh/grep.
---

# prod-job-progress

Progress questions were answered with hand-typed `ssh … find -newer … | wc -l` and
`docker logs | grep` one-liners. On 2026-10-17 one of them used a pattern the pipeline never logs,
returned 0, and was one step from being reported as "batch 1 made no progress": it had finished 14
episodes. A zero from a search is evidence about the search (rule 0.16). This script makes the
check every time: when the done-count is 0 it also counts every file written and every log line
since the container started, and calls the result INCONCLUSIVE when those are not zero.

## Run

```bash
P=~/.claude/skills/prod-job-progress/scripts/progress.py
python3 $P --ssh deploy@prod-podcast --key ~/.ssh/podcast_prod_operator \
  --container podcast-reprocess-<run_id> --dir /srv/podcast-scraper/corpus \
  --done-glob '*.gi.json' --expected <worklist size>
```

- `--done-glob`: one file per FINISHED item, written last in the item's pipeline. For podcast_scraper
  reprocess: `*.gi.json` for any stage that cascades GI; `*.asr.json` only for stages that
  re-transcribe (`full`, `retranscript_only`); `rediarize_only` writes no `.asr.json`.
- `--expected`: the worklist size (`prod-batch-chain status` shows each batch's `n`).
- `--problem-pattern`: default `Traceback`, `Killed process`, ` ERROR `.

Exit: 0 report, 1 container not found (finished and removed, or wrong name), 2 INCONCLUSIVE.

## Reading it

- The ETA is count-based and assumes the remaining items are like the done ones. A batch sorted
  largest-first finishes its long items first, so its count-based ETA is pessimistic early on. Say so
  when you quote it, or weight by the pool's minutes.
- `problem lines` > 0: open them (`docker logs <c> 2>&1 | grep -n -A20 Traceback`) before saying
  anything about the job.
- For the pipeline's own view, use the Close Listening Obs MCP (`obs_events` with
  `event_type=pipeline_stage`, `obs_surface pipeline`) as a second, independent count.

## Tests

`cd scripts && python3 -m unittest test_progress`. Live check 2026-10-17 on prod batch 2
(run 39026409470): `done: 9 of 21`. With a deliberately wrong glob: `INCONCLUSIVE … 791 files were
written and 2318 log lines`, exit 2.

## Not covered

- Jobs that rewrite files in place without a per-item marker file: pick a marker the job writes once
  per item, or the count means nothing.
- A container that already exited and was removed (`--rm`) cannot be measured. Use the workflow run's
  result and the ledger instead.
