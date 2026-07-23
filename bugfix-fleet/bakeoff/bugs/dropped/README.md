# Dropped bugs

Bugs removed from the active bake-off set, with the reason. Kept (not deleted)
so the decision is auditable.

## orrery-image-bytes (fix 78a79e8) — dropped: no solution-agnostic oracle

The oracle-coupling audit (2026-07-23) flagged this as the only structure-coupled
oracle in the set. Root problem: this "bug" is really a **feature-add** — the fix
introduces a *new* JPEG-magic-byte detector (`scripts/lib/image-bytes.ts`, new at
fix) and wires it into the data audit. There is no pre-existing public interface
whose *behavior* changed, so any oracle must either:

- couple to the fix's internal structure (import the new `isJpegBytes` module by
  path + name) — which wrongly FAILs a correct fix that structures the code
  differently (observed: glm-5.2 implemented correct SOI detection inline in
  `scripts/vision/anthropic.ts` and the coupled oracle could not see it); or
- drive the heavy `scripts/validate-data.ts` audit end-to-end — which is
  unusable here because it exits non-zero at base for unrelated reasons (the
  `.jpg` binaries are absent/LFS in the worktree → hundreds of
  "manifest entry references missing file" errors that drown the mime signal,
  and a planted test file can't be placed).

A valid bake-off oracle must test observable behavior through a stable interface.
image-bytes has neither a shipped behavioral test nor a stable entrypoint, so it
is dropped rather than graded on structure. The remaining 5 bugs all ship their
own behavioral tests against modules that existed at base.
