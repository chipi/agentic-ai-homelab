// HIDDEN GRADER ORACLE — bug #251 (fix commit 78a79e8). Never shown to the solver.
//
// Bug: files written with a .jpg extension held non-JPEG (PNG) bytes, which the
// vision API silently rejects. The fix adds scripts/lib/image-bytes.ts exporting
// isJpegBytes() — true iff the buffer starts with the JPEG SOI magic (ff d8 ff).
//
// RED at base 78a79e8^: scripts/lib/image-bytes.ts does not exist, so the import
// fails and every test errors. GREEN once the fix (or an equivalent) lands and
// isJpegBytes correctly discriminates JPEG magic from PNG magic.
//
// PLACEMENT (grader): copy to scripts/lib/image-bytes.test.ts in the worktree at
// grade time (vitest include already covers scripts/**/*.test.ts).
import { describe, it, expect } from 'vitest';
import { isJpegBytes } from './image-bytes';

describe('isJpegBytes (#251 oracle)', () => {
  it('true for real JPEG SOI magic (ff d8 ff …)', () => {
    expect(isJpegBytes(Buffer.from([0xff, 0xd8, 0xff, 0xe0, 0x00, 0x10]))).toBe(true);
  });
  it('false for PNG magic (89 50 4e 47 …) — the #251 failure mode', () => {
    expect(isJpegBytes(Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a]))).toBe(false);
  });
  it('false for a buffer shorter than the magic', () => {
    expect(isJpegBytes(Buffer.from([0xff, 0xd8]))).toBe(false);
  });
});
