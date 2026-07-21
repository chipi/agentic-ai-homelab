// Git plumbing for Flow B (MVP, serial). Operates directly in REPO_CHECKOUT on
// the long-lived `fixes` branch — no worktrees yet (worktrees are for
// CONCURRENCY, a later phase; the MVP processes one fix at a time).
// Push auth uses a fresh installation token in the remote URL.

import { execFile } from "node:child_process";
import { promisify } from "node:util";
import * as fs from "node:fs";

const exec = promisify(execFile);
const FIXES = "fixes";
const ENV = { ...process.env, GIT_CONFIG_GLOBAL: "/dev/null" };

export function checkoutDir(): string {
  const d = process.env.REPO_CHECKOUT;
  if (!d) throw new Error("REPO_CHECKOUT not set");
  return d;
}

async function git(cwd: string, ...args: string[]): Promise<string> {
  const { stdout } = await exec("git", args, { cwd, env: ENV });
  return stdout.trim();
}

function authUrl(owner: string, repo: string, token: string): string {
  return `https://x-access-token:${token}@github.com/${owner}/${repo}.git`;
}

/** Clone the target if absent, else refresh; always (re)point origin at a fresh
 *  token URL so pushes authenticate. */
export async function ensureClone(owner: string, repo: string, token: string): Promise<void> {
  const dir = checkoutDir();
  const url = authUrl(owner, repo, token);
  if (!fs.existsSync(`${dir}/.git`)) {
    await fs.promises.mkdir(dir, { recursive: true });
    await exec("git", ["clone", url, dir], { env: ENV });
  } else {
    await git(dir, "remote", "set-url", "origin", url);
    await git(dir, "fetch", "origin");
  }
}

/** Check out the long-lived `fixes` branch (create from main if it doesn't exist). */
export async function ensureFixesBranch(): Promise<void> {
  const dir = checkoutDir();
  try {
    await git(dir, "fetch", "origin", FIXES);
    await git(dir, "checkout", "-B", FIXES, `origin/${FIXES}`);
  } catch {
    await git(dir, "fetch", "origin", "main");
    await git(dir, "checkout", "-B", FIXES, "origin/main");
  }
}

/** The deterministic pre-land gate. */
export async function runTests(): Promise<boolean> {
  try {
    await exec("python3", ["-m", "pytest", "-q"], { cwd: checkoutDir(), env: ENV });
    return true;
  } catch {
    return false;
  }
}

/** Commit whatever the worker changed and push to `fixes`. */
export async function commitAndPush(
  owner: string,
  repo: string,
  token: string,
  message: string,
): Promise<{ ok: boolean; sha?: string }> {
  const dir = checkoutDir();
  try {
    await git(dir, "add", "-A");
    await git(dir, "-c", "user.email=bot@homelab.local", "-c", "user.name=bugfix-fleet",
      "commit", "-m", message);
    const sha = await git(dir, "rev-parse", "--short", "HEAD");
    await git(dir, "remote", "set-url", "origin", authUrl(owner, repo, token));
    await git(dir, "push", "origin", FIXES);
    return { ok: true, sha };
  } catch {
    return { ok: false };
  }
}
