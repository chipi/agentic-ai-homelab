// Flow B — Fix (RFC-0002 MVP). flow:approved bug → specialist in an isolated
// git worktree on the long-lived `fixes` branch → fix → LOCAL tests green →
// commit → (open/update the batch PR). Exercises: worktree isolation, a cheap
// model doing real code, the branch model, PR creation.

import { Octokit } from "@octokit/rest";
import { Worker, Area } from "../worker/types.js";
import { FLOW } from "../labels.js";
import { setFlow, comment } from "../github/issueOps.js";
import { withWorktree, commitToFixes, runLocalTests } from "../git/worktree.js";

export async function runFix(
  gh: Octokit,
  repo: { owner: string; repo: string },
  worker: Worker,
  issue: { number: number; title: string; body: string; area: Area },
): Promise<void> {
  await setFlow(gh, repo, issue.number, FLOW.fixing);

  const result = await withWorktree(repo, `fix-${issue.number}`, async (worktreeDir) => {
    const r = await worker.fix({
      kind: "fix", issueNumber: issue.number, title: issue.title,
      body: issue.body, area: issue.area, worktreeDir,
    });
    // deterministic gate — the orchestrator runs tests, not the LLM
    r.testsGreen = await runLocalTests(worktreeDir);
    return r;
  });

  if (!result.testsGreen) {
    await setFlow(gh, repo, issue.number, FLOW.stuck);
    await comment(gh, repo, issue.number,
      `🤖 fix (${worker.harness}): produced a change but **local tests are red** — needs a human.\n\n${result.notes ?? ""}`);
    return;
  }

  // Land it on the long-lived `fixes` branch (serial merge; conflict → stuck).
  const landed = await commitToFixes(repo, `fix-${issue.number}`, `fix #${issue.number}: ${result.summary}`);
  if (!landed.ok) {
    await setFlow(gh, repo, issue.number, FLOW.stuck);
    await comment(gh, repo, issue.number, `🤖 fix (${worker.harness}): conflict landing on \`fixes\` — needs rebase.`);
    return;
  }

  await setFlow(gh, repo, issue.number, FLOW.fixed);
  await comment(gh, repo, issue.number,
    `🤖 fix (${worker.harness}) landed on \`fixes\` as ${landed.sha}.\nFiles: ${result.filesChanged.join(", ")}\n\n_Awaiting the batch PR._`);
}
