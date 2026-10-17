---
name: ship
description: The pre-push ritual — rebase onto the trunk, run the right validation gates, confirm green, show the diff, push only with the operator's approval, then watch CI on what was pushed until it settles. Covers feature branches with PRs and the direct-to-main path for small fixes on trunk-based repos. Enforces never-push-without-approval, always-rebase-before-push, green-local-then-push and verify-after-push. Use when about to push anything — a branch, a PR, or a commit straight to main.
---

# ship

The disciplined path from "work is done" to "pushed and green", so nothing lands unrebased,
unvalidated, unapproved or unwatched. **A push is shared state and needs the operator's
approval** (below: per push, or for an arc when the operator grants it that way).

## Pick the path

| Path | When |
| --- | --- |
| **A. Feature branch + PR** | the default; anything that wants review; any repo without a trunk-based habit |
| **B. Direct to main** | a repo that works trunk-based *and* the operator has said so for this kind of change: a small fix, a red main after a merge, a doc fix, or an arc where the operator said "push everything when done" |

Path B is never self-granted. Without the operator's word for this repo and arc, use A.

## Steps (both paths)

1. **Branch check.**
   - *A:* on a feature branch, never `main`; confirm what it is ahead of.
   - *B:* confirm the local commits about to land (`git log origin/main..HEAD`), and that
     nothing unrelated rides along.
2. **Secrets.** Run the `secrets-scan` skill over the diff. A hit blocks the push.
3. **Rebase onto the trunk.** `git fetch origin main && git rebase origin/main`. Resolve
   conflicts; never leave a merge commit. Every push, not just the first. If the rebase pulled in
   code (not only docs) that touches what you changed, re-run the affected gates.
4. **Run the right gates, not the heaviest.** Run the validation that covers the change:
   `docs-preflight` for docs, the repo's own gate target, the specific tests. Reproduce green
   locally; don't push and let CI find it. End each gate with an unambiguous PASS/FAIL, quoted
   in the report.
5. **Show what ships.** `git status`, plus `git --no-pager diff origin/main...HEAD --stat`, plus
   the commit log about to land. Summarize it.
6. **Approval.**
   - *Per push* by default: wait for "push" / "ship it" / "go". Approval for a previous push
     does not carry to this one.
   - *Per arc* only when the operator granted it that way ("push everything when done", "stop
     asking me per commit"). That covers this arc's pushes, never the next arc's. Never ask per
     commit inside it.
7. **Push.**
   - *A:* `git push --force-with-lease` if the branch is already on the remote, else
     `git push -u origin <branch>`. PRs default to ready, not draft, unless asked otherwise.
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

- **Never push without explicit approval** (rule #1): per push, unless the operator granted an
  arc.
- **Always rebase onto the trunk before pushing** (rule #2).
- **Red required CI = fix until green** (rule #3). "Green" means a `VERDICT GREEN` line from
  `ci-watch` (or the repo's gate), cited.
- **Green local, then push** (rule #11): reproduce failures locally first.
