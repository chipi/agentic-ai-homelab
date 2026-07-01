---
name: repro-first
description: For a real bug, write a failing test (or fixture / matrix row) that reproduces it BEFORE fixing — the test becomes the regression guard. Use when starting on a reported bug, a production incident, or any "it's broken" investigation. Enforces reproduce-before-fix and never-invent-root-causes.
---

# repro-first

A real bug gets a failing test that reproduces it *before* the fix lands. The
test is the regression guard for next time. **No fix without a repro.**

## Steps

1. **Reproduce locally first.** Pull evidence for THIS specific failure — the
   actual error, log, stack trace, or input. Don't theorize a root cause from
   "usually it's X"; get the real signal for this run.
2. **Write the failing test** at the right layer — unit test, integration case,
   fixture, or a matrix row — that fails *because of* the bug. Run it; confirm it
   fails for the expected reason (red for the right cause, not a typo).
3. **Fix** the code.
4. **Confirm green + no collateral.** The new test passes, and the surrounding
   suite still passes — run the gate that covers the change, not the whole world.
5. **Keep the test.** It ships with the fix in the same change. Don't delete it,
   don't mark it skip — it's the guard for the next regression.

## Non-negotiables this enforces

- **Real bug → repro before fix** (rule #34): the failing test lands with the fix.
- **Never invent root causes** (rule #5): evidence for this run before a theory.
- **Reproduce locally before pushing** (rule #11).
