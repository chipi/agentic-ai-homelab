// Flow B — Fix (RFC-0002 MVP, serial). flow:approved bug → checkout the `fixes`
// branch → specialist edits the code → LOCAL pytest green → commit + push to
// `fixes`. No worktrees yet (serial processing; worktrees = concurrency, later).
// Exercises: a cheap model editing real code, the branch model, the test gate.

import { Octokit } from "@octokit/rest";
import { Worker, Area } from "../worker/types.js";
import { FLOW } from "../labels.js";
import { setFlow, comment } from "../github/issueOps.js";
import { AppConfig, getInstallationToken } from "../github/appAuth.js";
import { ensureClone, ensureFixesBranch, pytest, commitAndPush, checkoutDir } from "../git/repo.js";

export async function runFix(
  gh: Octokit,
  repo: { owner: string; repo: string },
  cfg: AppConfig,
  worker: Worker,
  issue: { number: number; title: string; body: string; area: Area },
): Promise<void> {
  await setFlow(gh, repo, issue.number, FLOW.fixing);

  const token = await getInstallationToken(cfg);
  await ensureClone(repo.owner, repo.repo, token);
  await ensureFixesBranch();

  // Regression-aware gate: capture the failing set BEFORE the change (fixes may
  // already contain earlier fixes; other bugs are still red — that's expected).
  const before = await pytest();

  const result = await worker.fix({
    kind: "fix", issueNumber: issue.number, title: issue.title,
    body: issue.body, area: issue.area, worktreeDir: checkoutDir(),
  });

  const after = await pytest();
  const newFails = [...after.failures].filter((f) => !before.failures.has(f));
  const fixed = [...before.failures].filter((f) => !after.failures.has(f));
  const accept = !after.broke && newFails.length === 0 && fixed.length > 0;

  if (!accept) {
    const why = after.broke ? "the change broke test collection"
      : newFails.length ? `it broke: ${newFails.join(", ")}`
      : "it fixed nothing (no failing test turned green)";
    await setFlow(gh, repo, issue.number, FLOW.stuck);
    await comment(gh, repo, issue.number,
      `🤖 fix (${worker.harness}): rejected — ${why}. Needs a human.\n\nFiles: ${result.filesChanged.join(", ")}`);
    return;
  }

  const fresh = await getInstallationToken(cfg);
  const landed = await commitAndPush(repo.owner, repo.repo, fresh, `fix #${issue.number}: ${result.summary}`);
  if (!landed.ok) {
    await setFlow(gh, repo, issue.number, FLOW.stuck);
    await comment(gh, repo, issue.number, `🤖 fix (${worker.harness}): couldn't land on \`fixes\` (conflict?) — needs a human.`);
    return;
  }

  await setFlow(gh, repo, issue.number, FLOW.fixed);
  await comment(gh, repo, issue.number,
    `🤖 fix (${worker.harness}) — **turned green:** ${fixed.join(", ")}; broke nothing. ` +
    `Landed on \`fixes\` as \`${landed.sha}\`.\n\n` +
    `**Change:** ${result.summary}\n**Files:** ${result.filesChanged.join(", ")}\n\n_Awaiting the batch PR._`);
}
