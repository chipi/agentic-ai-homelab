---
name: perf-diagnose
description: Diagnose a slow or stalled endpoint or job from evidence — observability first, then a local reproduction (including a GIL-contention bench that times the request path idle, under in-process CPU load, and with the load in a child process), then a before/after proof against the old code. Use when "an endpoint hangs / times out / is slow on prod", "the smoke failed after a restart", "the API is slow while X runs", or before claiming a performance fix works.
---

# perf-diagnose

A stall has a cause you can measure. This is the order that found one fast (podcast_scraper,
2026-10-16), written down so the next one does not start from scratch. The ladder ends where
`replay-proven-fix` begins.

## 1. Read what production already recorded (no SSH yet)

- Load `o11y-review` for the window: logs, errors and traces around the stall.
- Look for: the exact request that did not answer (an access-log line missing is itself the
  signal), what else was running then (warmers, migrations, backfills), and per-step timings
  if the service logs them.
- Write down what is known and what is not, before forming a theory (rule: never invent root
  causes).

## 2. Name the candidate mechanism

| Symptom | Usual mechanism | How to tell |
| --- | --- | --- |
| A request that is fast alone does not answer while a background job runs, then answers in seconds | **GIL starvation**: a CPU-bound thread in the same Python process; a syscall-heavy request gives up the GIL on every call and queues to get it back | step 3 bench |
| Every request waits the same long time, then all answer together | a lock or single-flight around a cold build | grep for locks / `single_flight` on the path; time with the job off |
| Only under many concurrent requests | worker pool or connection pool exhausted | count workers; the access log's concurrency |
| Box-wide slowness, every process | CPU or memory saturation (other agents' runs, an OOM loop) | `uptime`, `ps aux \| sort -nrk3 \| head` |

## 3. Reproduce locally

For GIL starvation, the bench times a probe (what the request does) idle, under the suspected
load in-process, and with the load in a child process:

```bash
python3 ~/.claude/skills/perf-diagnose/scripts/contention_bench.py --demo   # see the effect
<project>/.venv/bin/python ~/.claude/skills/perf-diagnose/scripts/contention_bench.py \
  --path <repo>/src --probe pkg.mod:walk_like_the_request --load pkg.mod:score_like_the_warmer
```

Both functions take no arguments; write two small wrappers in the scratchpad if needed.

- **Read the verdict:**
  - `GIL STARVATION` when the in-process run is at least 5x idle and the child run is under 2x;
  - `CONTENTION` when it is slower but the child doesn't clear it; check the core count;
  - `NO CONTENTION`: look elsewhere.
- **Measured example:** a 161-file walk took 1.4 ms idle, 129 ms with reel-clip scoring
  in-process, and 1.6 ms with the scoring in a child. On prod, the same walk behind 243 s of
  in-process scoring gave no answer within the smoke's 45 s.

**The fix for GIL starvation** is to move the CPU work out of the serving process, not to make
the smoke wait:
- run it as a `python -m` child (not `multiprocessing`, which re-imports the parent's
  `__main__`);
- pass inputs and results over a pipe, and fall back in-process if the child cannot run.

## 4. Prove it — before and after, on the old code from git

- **Old vs new:** use `replay-proven-fix`. `eval "$(~/.claude/skills/replay-proven-fix/scripts/baseline_worktree.sh <BASE_REV>)"`
  checks the old code out, then time both on the same data in fresh processes.
  - Cold first runs are what a restart pays; warm repeats can hit caches the old code had.
- **Equivalence:** prove the results did not change, not only the speed: a replay comparing
  outputs, then mutants that the replay kills.
- **The fix stays proven:** commit a test that would fail if the work moved back in-process,
  for example by making the in-process path raise inside the test.

## 5. After the deploy

The local proof is not the production proof. Name the log line or timing that will show the fix
on prod (e.g. no "isolated … failed" warning, the endpoint answering *during* the warm), and
check it, or hand that exact check to whoever deploys.

## Optional: a live profile (needs approval)

`py-spy dump --pid <pid>` / `py-spy record --gil` shows which thread holds the GIL in the live
process, read-only. **py-spy is a new dependency**: ask before installing it anywhere, and never
into a project venv shared with other worktrees.

## Not covered

- Native-code hot loops (numpy, Rust bindings) release the GIL; the bench will say
  `NO CONTENTION` for them. Look at CPU saturation instead.
- Async event-loop blocking (a sync call inside `async def`) is a different mechanism. Probe it
  with an async request under the same load.
