---
name: baseline-diff
description: Compare a branch against its trunk base by running the same make targets in both (a detached worktree at the merge base, never a stash), each tree with its own src/ first on PYTHONPATH, and print a target × {base, branch} PASS/FAIL table plus the error lines that exist only on the branch. Use when a gate fails on a branch and the question is "did my branch cause this", after a rebase onto a new trunk, or before calling any failure "pre-existing".
---

# baseline-diff

A red gate on a branch is the branch's until shown otherwise. The proof is the same targets run on
what the branch started from. That proof was hand-rolled each round of the podcast_scraper
infra split (2026-10-14 to 10-17) as `cifast.sh`, `cifast_rest.sh` and `mypy_both.sh`, plus a
by-eye comparison of 1.5 MB logs. Two traps it kept hitting:

- **A stash is not a baseline.** It leaves the session's committed work in the tree (the
  2026-08-03 incident). The base here is `merge-base(--base, HEAD)` checked out on its own.
- **Worktrees share one editable install.** Without `PYTHONPATH=<tree>/src`, both trees import
  whichever checkout the venv was installed from, and the comparison compares nothing.

## Run it

```bash
cd <branch worktree>
python3 ~/.claude/skills/baseline-diff/scripts/baseline_diff.py --base origin/main type test-unit lint
python3 ~/.claude/skills/baseline-diff/scripts/baseline_diff.py --remove     # when done
```

- Targets run in order, base then branch, every one even after a failure. Each finished run prints
  one `done` line, so it can be watched with the Monitor tool. A `tail -f` path is printed for
  each log.
- The base worktree is `$TMPDIR/baseline-diff-<repo>`. It is reused while the merge base is
  unchanged. If the branch has a `.venv` and the base has none, the base gets a symlink to the
  same one. Nothing is installed.
- `--env K=V` passes extra env to both trees. `--logs DIR` keeps logs somewhere specific.

## Reading the verdict

| verdict | meaning |
| --- | --- |
| PASS | both trees pass |
| FAIL BRANCH ONLY | the base passes: the branch caused it. Fix it. |
| FAIL BOTH + NEW ON BRANCH | already red on base, and the branch adds error lines base does not have |
| FAIL BOTH | the same error lines in both trees: not added by the branch, and **still not a pass** |
| FIXED ON BRANCH | base fails, the branch passes |

Exit 1 when any target is FAIL BRANCH ONLY or FAIL BOTH + NEW ON BRANCH, else 0. Error lines are
compared with numbers masked: counts, timings and line numbers differ between trees for reasons
that are not new errors. The original line is what gets printed.

A FAIL BOTH is evidence for a sentence like "main at b0edbb94 shows the identical mypy error".
It is not permission to leave the gate red. Whether to fix it in this branch is the operator's
call. Report it, don't bury it.

## Tested 2026-10-17

- Synthetic repo, one target per verdict: all five verdicts and both exit codes came out as
  expected, and the branch log shows `PYTHONPATH=<branch>/src`.
- podcast_scraper PR 2138 (`acdfed1b`) against `b0edbb94` with `make type`: FAIL BOTH, 0 lines
  only on the branch. That matches the by-hand finding (same `test_app_episodes.py:307` error on
  main). The first version called it NEW ON BRANCH because mypy's "checked 2356 / 2322 source
  files" differed when the branch deleted files. That is why numbers are masked.

## Not covered

- Masking numbers means an error that differs from a base error only in a number (same message,
  another line) counts as old. Read the branch log when the verdict is FAIL BOTH on a file the
  branch touched.
- Error lines are found with a keyword regex (`error`, `FAILED`, `Traceback`, …). A tool that
  reports failure without those words shows a FAIL with no listed lines. The exit codes are still
  right.
- It runs `make` only, not arbitrary commands. Flaky targets give flaky verdicts: re-run a FAIL
  BRANCH ONLY before trusting it.
