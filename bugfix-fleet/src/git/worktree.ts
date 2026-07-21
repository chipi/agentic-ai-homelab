// Git worktree mechanics — each fix runs in an ISOLATED worktree so concurrent
// jobs never collide (RFC-0002). Fixes land on the long-lived `fixes` branch
// via serial merges; a conflict → the caller marks the issue flow:stuck.
//
// STATUS: skeleton — shells out to git. Assumes a local clone of the target repo
// at REPO_CHECKOUT (set in .env); worktrees are created under REPO_CHECKOUT/.wt/.

import { execFile } from "node:child_process";
import { promisify } from "node:util";
import * as path from "node:path";

const exec = promisify(execFile);
const CHECKOUT = () => process.env.REPO_CHECKOUT ?? "";
const FIXES_BRANCH = "fixes";

async function git(cwd: string, ...args: string[]): Promise<string> {
  const { stdout } = await exec("git", args, { cwd, env: { ...process.env, GIT_CONFIG_GLOBAL: "/dev/null" } });
  return stdout.trim();
}

/** Create a throwaway worktree branched off `fixes`, run `fn`, then remove it. */
export async function withWorktree<T>(
  _repo: { owner: string; repo: string },
  slug: string,
  fn: (worktreeDir: string) => Promise<T>,
): Promise<T> {
  const root = CHECKOUT();
  const wt = path.join(root, ".wt", slug);
  await git(root, "fetch", "origin", FIXES_BRANCH).catch(() => {});
  await git(root, "worktree", "add", "-B", `wt/${slug}`, wt, `origin/${FIXES_BRANCH}`)
    .catch(async () => { await git(root, "worktree", "add", "-B", `wt/${slug}`, wt, "origin/main"); });
  try {
    return await fn(wt);
  } finally {
    await git(root, "worktree", "remove", "--force", wt).catch(() => {});
  }
}

/** Run the target repo's tests in the worktree (the deterministic pre-land gate).
 *  TODO: make the command repo-configurable; sandbox uses pytest. */
export async function runLocalTests(worktreeDir: string): Promise<boolean> {
  try {
    await exec("python", ["-m", "pytest", "-q"], { cwd: worktreeDir });
    return true;
  } catch {
    return false;
  }
}

/** Merge the worktree branch onto `fixes` (serial). Returns the new sha or a
 *  conflict flag for the caller to mark flow:stuck. */
export async function commitToFixes(
  _repo: { owner: string; repo: string },
  slug: string,
  message: string,
): Promise<{ ok: boolean; sha?: string }> {
  const root = CHECKOUT();
  try {
    await git(root, "checkout", FIXES_BRANCH);
    await git(root, "merge", "--squash", `wt/${slug}`);
    await git(root, "commit", "-m", message);
    const sha = await git(root, "rev-parse", "--short", "HEAD");
    await git(root, "push", "origin", FIXES_BRANCH);
    return { ok: true, sha };
  } catch {
    await git(root, "merge", "--abort").catch(() => {});
    return { ok: false };
  }
}
