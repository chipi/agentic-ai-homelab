---
name: ci-watch
description: Watch every GitHub check on one commit until it settles — one line per check as it lands, the failing job's log on the first failure, cancelled checks reported as NOT RUN (never as a pass), and a GREEN / RED / INCOMPLETE verdict. Resolves short SHAs, bounded, read-only. Use after every push, when asked "is main green", "watch CI", "did my fix's job actually run", or "why did CI fail".
---

# ci-watch

After a push, the job is not done until CI on that commit is green. This watches it the same
way every time, so the failures that happened when the loop was hand-written cannot recur:

| What went wrong (2026-10-16, podcast_scraper) | What the script does |
| --- | --- |
| A short SHA on `/commits/{sha}/check-runs` returns **422**; the hand loop swallowed it and saw "no checks" for 30 minutes | Resolves the full SHA first, via `git rev-parse` or the commits API; an unknown ref exits 4 at once |
| The monitor expired at 30 minutes and nobody re-armed it | Stops before the deadline with `RE-ARM ci-watch` and exit 3 |
| A fix's `app-unit` job was **cancelled** twice before it ran, and a cancelled check read as "done" | Prints `NOT RUN — cancelled; the next commit on <branch> is <sha>`; the verdict is INCOMPLETE, never GREEN |
| The cause of a red job took several commands to find | Prints the failing job's log tail on the first failure, `##[error]` lines first |

## Run it under the Monitor tool

```text
Monitor(command: "python3 ~/.claude/skills/ci-watch/scripts/ci_watch.py <sha> --repo owner/name",
        description: "CI on <sha>", timeout_ms: 1800000)
```

- Each stdout line is one event: `watching …`, then `name: conclusion` per check, a log tail
  block on the first failure, and one `VERDICT …` line.
- `--timeout-min` (default 25) keeps it under the Monitor's 30-minute cap. **On exit 3, start it
  again**: a long suite (a 2-hour device tier, a 6-hour reprocess) needs several arms.
- The SHA defaults to `HEAD`; `--repo` defaults to the current directory's GitHub repo.

| Exit | Verdict | Meaning |
| --- | --- | --- |
| 0 | GREEN | every check succeeded, was skipped or neutral |
| 1 | RED | a check failed or timed out; the log tail is above |
| 2 | INCOMPLETE | nothing failed, but something did not run (cancelled, stale) |
| 3 | INCOMPLETE | the deadline came first; re-arm |
| 4 | — | bad ref or repo |

The classification is the one podcast_scraper's `.github/workflows/ci-gate.yml` uses: failure
and timed_out are RED, cancelled is unresolved.

## Rules that go with it

- **Report the verdict line, not a feeling.** "CI is green" needs `VERDICT GREEN` from this
  script (or the gate) in the same sentence.
- **Do not push a docs-only commit while your fix's run is still pending.** On a branch with a
  `concurrency` group, a newer push replaces a *pending* run of the same workflow. Its jobs end
  up cancelled, never run, and the fix stays unproven. Wait until the fix's run has started
  (`in_progress`); a running run keeps going on main.
- **A cancelled check is not a pass.** If the next commit on the branch contains yours, its run
  is the proof: watch that SHA.
- **On RED, open the tail it printed and fix the cause before anything else.** A rerun is only
  for a measured transient (a registry 429, a runner lost); say which.

## Passes locally, times out in CI

The shared runner can be many times slower than a laptop. On 2026-10-16 a vitest file took 42 s
in CI against ~1 s locally, and its tests hit the 5 s default.

1. Read the durations from the job log (the per-file time vitest and pytest print) and compare
   with a local run of the same file.
2. **Fix the cause first.** Build fixtures once (describe level, module fixtures), not per test.
   Use less data. Avoid real I/O and real timers.
3. Raise a timeout only when the work *is* the test, and write the measured reason beside it
   (`// CI ran this file 42 s, ~4.5 s a test against the 5 s default`). A bare bigger number is
   suppression.

## Not covered

- It reads one commit's checks. It does not trigger reruns or cancel anything, and never will:
  those are writes.
- Workflows that start later through `workflow_run` (a gate that waits for others) can appear
  after everything else has finished. If the verdict lands while a gate is still to come, the
  next arm picks it up.
- The log tail is the job log only; artifacts (test reports, screenshots) are not fetched.
