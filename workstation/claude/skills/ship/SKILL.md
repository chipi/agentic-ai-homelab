---
name: ship
description: The pre-push ritual — rebase onto the trunk, run the right validation gates, confirm green, show the diff, and push only after explicit approval. Enforces never-push-without-approval, always-rebase-before-push, and green-local-then-push. Use when about to push a feature branch or open a PR. The push itself is gated on explicit approval.
---

# ship

The disciplined path from "work is done" to "pushed" — so nothing lands unrebased,
unvalidated, or unapproved. **The push is shared-state and gated on explicit
approval, every time.**

## Steps

1. **Branch check.** Never push the trunk directly. If on `main`, stop — branch
   first. Confirm the feature branch and what it's ahead of.
2. **Secrets.** Run the `secrets-scan` skill over the diff. A hit blocks the push.
3. **Rebase onto trunk.** `git fetch origin main && git rebase origin/main`.
   Resolve conflicts; never leave a merge commit on a feature branch. Do this
   every push, not just the first.
4. **Run the right gates — not the heaviest.** Run the validation that actually
   covers the change (`docs-preflight` for docs, the relevant `make` target, the
   specific test). Reproduce green locally; don't push-and-let-CI-find-it. End
   each gate with an unambiguous PASS/FAIL.
5. **Show what ships.** `git status` + `git --no-pager diff origin/main...HEAD --stat`
   + the commit log about to land. Summarize it.
6. **Get explicit approval.** Wait for "push" / "ship it" / "go". Approval for a
   previous push does NOT carry to this one.
7. **Push.** `git push --force-with-lease` if the branch is already on the remote
   (post-rebase), else `git push -u origin <branch>`. PRs default to ready, not
   draft, unless asked otherwise.

## Non-negotiables this enforces

- **Never push without explicit approval** (rule #1) — per push, not per session.
- **Always rebase onto the trunk before pushing** (rule #2) — `--force-with-lease`.
- **Red required CI = fix until green** (rule #3).
- **Green local, then push** (rule #11) — reproduce failures locally first.
