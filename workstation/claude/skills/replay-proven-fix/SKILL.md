---
name: replay-proven-fix
description: Prove a behaviour change on real history before it ships. Freeze real evidence into a corpus, replay it through the old code (from git, never re-implemented) and the new code, check the replay is faithful, mutation-test the replay, read the changed cases against explicit links, then gate it. Use for any change to decision logic (dedup, routing, alert rules, classifiers, filters) in any project (Python or TypeScript, homelab fleet, Close Listening, Orrery). Complements repro-first, which covers a single bug's failing test.
---

# replay-proven-fix

The operator's standing requirement for a behaviour change: *a replayed test case
with the input, today's output, the problem, and the output after the fix.* This
skill is that loop, plus the traps found while running it (homelab, 2026-09-30 →
10-02).

`repro-first` covers "one bug, one failing test". This skill is for changes to
**decisions over many inputs**, where the risk is what else moves.

## The loop

1. **Find it in real data, with counts.** "10,764 of 11,700 rows repeat", not "lots of noise". Query the real system; never estimate.
2. **Freeze the evidence** into a committed corpus: snapshots, payloads, and the external state the decision reads (e.g. GitHub issue states). Scrub secrets and user ids. History moves on; the corpus keeps the replay reproducible.
3. **Write the fix.** Prefer a deterministic rule over a prompt or a threshold tweak.
4. **Write the replay:** old code vs new code over the corpus.
   - **The old code comes from git at the commit before the fix.** Never re-implement "how it used to work" by hand.
     - Python: `scripts/new_replay.py` scaffolds this.
     - Any language: `eval "$(scripts/baseline_worktree.sh <BASE_REV>)"` checks the old code out into `$BASELINE_DIR`; run the replay there and in the working tree.
   - **First check the baseline reproduces the recorded history.** If it can't, the replay isn't faithful, and nothing it says about the fix counts.
   - **Write explicit pass criteria and exit non-zero on failure.** Include the *invariant* ("nothing outside the bug changes"), not only the headline ("the 6 alerts became 1").
   - **Stub external writes; serve reads from the corpus.** A replay never sends anything.
5. **Mutation-check the replay.** Break the fix in the plausible ways it could be wrong, and confirm the replay fails each time:
   ```bash
   python3 ~/.claude/skills/replay-proven-fix/scripts/mutate.py \
     --file path/to/module.py --find '<exact fix text>' --replace '<broken version>' \
     --precheck 'python3 -m py_compile path/to/module.py' -- <replay command>
   ```
   - **Exit codes:** 0 = killed (good), 1 = survived (the replay proves nothing; add the missing check), 2 = setup or invalid mutant. The file is always restored, verified by sha256.
   - **Read WHY it failed.** A mutant can fail for the wrong reason, e.g. a syntax error your edit introduced; `--precheck` catches that.
6. **Read the changed cases, not just the totals,** and judge them against **explicit links, not titles or names**. For example:
   - a duplicate link (GitHub GraphQL `ClosedEvent.duplicateOf`);
   - the stored signal or row behind the case;
   - an id that may have been reused.
7. **Gate it:** add the replay to the project's deploy or CI gate list, plus focused unit tests. Run every gate.
8. **Commit with the numbers:** input, before, after, the mutants and their results. **If a later finding contradicts what an earlier commit message claimed, say so in the next commit message.** Push and deploy only with the operator's go.
9. **Verify live.** "The replay passed" is not "it works in production". After deploying, exercise the real path: one real input pushed through by hand, or the real decision run read-only against live state with writes intercepted. If a deploy step loaded its own script before the pull (bash reads it first), run any newly added gate by hand once.
10. **Document:** update the project's design guide (why) and runbook (how), and list what is still not covered.

## Traps (each happened, 2026-09-30 → 10-02)

| Trap | What happened | Guard |
|---|---|---|
| a replay with no "nothing else changes" check | a disk-alert replay passed a version that still fanned out | step 4 invariant + a step 5 mutant for each failure shape |
| a mutant that fails for the wrong reason | a `sed` edit broke the syntax; "failed" proved nothing | `mutate.py --precheck`; read the tail |
| a replay over an empty corpus | a scaffold replayed 0 items and printed PASS | `new_replay.py` refuses an empty corpus (exit 1) |
| aggregate numbers passed, but the cases were wrong | 13 recurrences routed into a catch-all bucket | step 6 |
| cases judged by titles | moves called "wrong" that GitHub's duplicate links showed were right; one was a reused id | step 6: explicit links |
| a new gate not run by the first deploy | the deploy script was read before the pull | step 9 |
| "it should work in prod" | n/a — run the live read-only check every time | step 9 |

## Not covered

- **Choosing the corpus:** it has to contain the cases that matter. A replay over unrepresentative data proves the wrong thing. Say what the corpus does not contain.
- **Stochastic logic** (LLM decisions): replay the deterministic parts. For the model, use a frozen fixture set with a scorer, not this loop.
