---
name: ship
description: The pre-push ritual — rebase onto the trunk, run the right validation gates, confirm green, show the diff, push (no approval needed, main included), then watch CI on what was pushed until it settles. Covers feature branches with PRs and the direct-to-main path for small fixes on trunk-based repos. Enforces always-rebase-before-push, green-local-then-push and verify-after-push. Use when about to push anything — a branch, a PR, or a commit straight to main.
---

# ship

The disciplined path from "work is done" to "pushed and green", so nothing lands unrebased,
unvalidated or unwatched. **No push needs the operator's approval, main included** (operator,
2026-11-26: "lets allow agents to push to main"; feature branches since 2026-11-23). What still
needs a per-instance go is a force push other than `--force-with-lease` of a feature branch, and a
branch delete; the command-ask-guard hook asks for those.

## Pick the path

| Path | When |
| --- | --- |
| **A. Feature branch + PR** | the default; anything that wants review; any repo without a trunk-based habit |
| **B. Direct to main** | a repo that works trunk-based, or a change that wants no review: a small fix, a red main after a merge, a doc fix |

A repo whose main is protected (required reviews or checks) takes path A whatever the change.

## Steps (both paths)

1. **Branch check.**
   - *A:* on a feature branch, never `main`; confirm what it is ahead of.
   - *B:* confirm the local commits about to land (`git log origin/main..HEAD`), and that
     nothing unrelated rides along.
2. **Secrets.** Run `~/.claude/skills/secrets-scan/scripts/scan.sh --push` (the `secrets-scan` skill) over what the push sends. `SECRETS SCAN: FAIL` blocks the push.
3. **Rebase onto the trunk.** `git fetch origin main && git rebase origin/main`. Resolve
   conflicts; never leave a merge commit. Every push, not just the first. If the rebase pulled in
   code (not only docs) that touches what you changed, re-run the affected gates.
4. **Run the right gates, not the heaviest.** Run the validation that covers the change:
   `docs-preflight` for docs, the repo's own gate target, the specific tests. Reproduce green
   locally; don't push and let CI find it. End each gate with an unambiguous PASS/FAIL, quoted
   in the report.
5. **Show what ships.** `git status`, plus `git --no-pager diff origin/main...HEAD --stat`, plus
   the commit log about to land. Summarize it.
6. **No approval step** (2026-11-26). Push once steps 1–5 are green; report what landed.
7. **Push.**
   - *A:* `git push --force-with-lease origin <branch>` if the branch is already on the remote,
     else `git push -u origin <branch>`. Name the remote and the branch: the command-ask-guard
     hook asks for `--force-with-lease` when it cannot see a feature branch as the destination.
     PRs default to ready, not draft, unless asked otherwise.
   - *B:* `git push origin HEAD:main`. If it is rejected because main moved, fetch, rebase and
     re-check step 3; never force main.
8. **Watch what you pushed.** Load `ci-watch` and run it on the pushed SHA under the Monitor
   tool, re-arming on expiry until it prints a verdict.
   - **`VERDICT RED`:** read the tail it printed and fix the cause now. Red main is yours to fix
     first.
   - **`INCOMPLETE` with `NOT RUN — cancelled`:** your checks did not run. Watch the commit that
     superseded them instead (it contains yours), or wait and re-run; never report it as green.
   - **The order rule:** don't push a docs-only commit while your fix's run is still pending, or
     that run is cancelled before it starts.

## Non-negotiables this enforces

- **Pushes need no approval, main included; force pushes and branch deletes do** (rule #1).
  Never force main.
- **Always rebase onto the trunk before pushing** (rule #2).
- **Red required CI = fix until green** (rule #3). "Green" means a `VERDICT GREEN` line from
  `ci-watch` (or the repo's gate), cited.
- **Green local, then push** (rule #11): reproduce failures locally first.
