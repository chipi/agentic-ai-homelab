// HIDDEN GRADER ORACLE — bug #251 (fix 78a79e8). Dynamic-import inside the test so
// that at base (scripts/lib/image-bytes.ts absent) the missing module throws a
// FAILING ASSERTION (not a suite load-error), which the grader counts as red.
import { describe, it, expect } from 'vitest';
describe('isJpegBytes (#251 oracle)', () => {
  it('discriminates JPEG SOI magic from PNG magic', async () => {
    const mod = await import('./image-bytes');   // absent at base -> throws here -> test fails
    expect(mod.isJpegBytes(Buffer.from([0xff, 0xd8, 0xff, 0xe0]))).toBe(true);
    expect(mod.isJpegBytes(Buffer.from([0x89, 0x50, 0x4e, 0x47]))).toBe(false);
    expect(mod.isJpegBytes(Buffer.from([0xff, 0xd8]))).toBe(false);
  });
});
