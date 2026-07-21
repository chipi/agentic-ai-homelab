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

/** Check out the long-lived `fixes` branch (create from main if it doesn't exist),
 *  with a clean working tree so each fix starts from a known base. */
export async function ensureFixesBranch(): Promise<void> {
  const dir = checkoutDir();
  let base = "origin/main";
  try {
    await git(dir, "fetch", "origin", FIXES);
    base = `origin/${FIXES}`;
  } catch {
    await git(dir, "fetch", "origin", "main");
  }
  await git(dir, "checkout", "-B", FIXES, base);
  await git(dir, "reset", "--hard", base);
  await git(dir, "clean", "-fd");
}

/** Read the repo's fixable source files for reviewer CONTEXT — so it reasons
 *  about the whole code (e.g. api.py's RESPONSE_FORMAT), not just the diff. */
export function readRepoContext(): { path: string; content: string }[] {
  const dir = checkoutDir();
  const out: { path: string; content: string }[] = [];
  const srcDir = `${dir}/src`;
  if (fs.existsSync(srcDir)) {
    for (const f of fs.readdirSync(srcDir)) {
      if (f.endsWith(".py")) out.push({ path: `src/${f}`, content: fs.readFileSync(`${srcDir}/${f}`, "utf8") });
    }
  }
  for (const rf of ["README.md", "docker-compose.yml"]) {
    if (fs.existsSync(`${dir}/${rf}`)) out.push({ path: rf, content: fs.readFileSync(`${dir}/${rf}`, "utf8") });
  }
  return out;
}

export interface TestOutcome {
  failures: Set<string>; // failing test node ids
  broke: boolean; // collection/import error — no recognizable summary
}

/** Run pytest and report which tests fail (for the regression-aware gate). */
export async function pytest(): Promise<TestOutcome> {
  let out = "";
  try {
    const r = await exec("python3", ["-m", "pytest", "-q", "--tb=no"], { cwd: checkoutDir(), env: ENV });
    out = r.stdout;
  } catch (e: any) {
    out = `${e.stdout ?? ""}${e.stderr ?? ""}`;
  }
  const failures = new Set<string>();
  for (const line of out.split("\n")) {
    const m = line.match(/^FAILED\s+(\S+)/);
    if (m) failures.add(m[1]);
  }
  const broke = !/\d+ (passed|failed)/.test(out);
  return { failures, broke };
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
