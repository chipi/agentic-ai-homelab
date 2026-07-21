// PR operations for Phase 1 — the batch PR (fixes → main) + the whole-PR review.

import { Octokit } from "@octokit/rest";

type Repo = { owner: string; repo: string };
const FIXES = "fixes";

/** The single open batch PR (fixes → main), if any. */
export async function getOpenBatchPr(gh: Octokit, repo: Repo): Promise<any | null> {
  const { data } = await gh.pulls.list({ ...repo, state: "open", head: `${repo.owner}:${FIXES}`, base: "main" });
  return data[0] ?? null;
}

/** Open the batch PR covering everything accumulated on `fixes`. */
export async function openBatchPr(gh: Octokit, repo: Repo, issueNumbers: number[]): Promise<any> {
  const existing = await getOpenBatchPr(gh, repo);
  if (existing) return existing;
  const body =
    `Batch fix PR from the autonomous fleet.\n\nCloses: ${issueNumbers.map((n) => `#${n}`).join(", ")}\n\n` +
    `_Reviewed by the fleet's reviewer; awaiting operator merge._`;
  const { data } = await gh.pulls.create({
    ...repo, head: FIXES, base: "main",
    title: `fleet: batch bug fixes (${issueNumbers.map((n) => `#${n}`).join(", ")})`,
    body,
  });
  return data;
}

/** The unified diff of a PR (what the reviewer reads). */
export async function getPrDiff(gh: Octokit, repo: Repo, pull: number): Promise<string> {
  const res = await gh.pulls.get({ ...repo, pull_number: pull, mediaType: { format: "diff" } });
  return res.data as unknown as string;
}

/** Post a whole-PR review via the Review API.
 *  NB: a single App identity can't formally APPROVE / REQUEST_CHANGES its OWN
 *  PR (GitHub 422). So we post a COMMENT review; the verdict lives in the body
 *  and drives the fleet's internal loop. A separate reviewer identity (e.g.
 *  Claude's own App) would unlock the formal review state — Phase 2. */
export async function postReview(
  gh: Octokit,
  repo: Repo,
  pull: number,
  verdict: "approve" | "request_changes",
  body: string,
  items: { path: string; line: number; body: string }[],
): Promise<void> {
  const itemList = items.length
    ? "\n\n**Blocking items:**\n" + items.map((c) => `- \`${c.path}:${c.line}\` — ${c.body}`).join("\n")
    : "";
  const full = `**Verdict: ${verdict.toUpperCase()}**\n\n${body}${itemList}`;
  await gh.pulls.createReview({ ...repo, pull_number: pull, event: "COMMENT", body: full });
}
