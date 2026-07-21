// Phase 1 — the review + feedback loop (RFC-0002). Cut PR is already open.
// Reviewer reviews the WHOLE PR → posts a Review-API review (human-facing) AND
// returns structured items → orchestrator dispatches blocking items back to the
// fixer → revise → push → re-review. Bounded; then operator merges.

import { Octokit } from "@octokit/rest";
import { Worker } from "../worker/types.js";
import { makeReviewer } from "../worker/reviewer.js";
import { AppConfig, getInstallationToken, installationOctokit, loadReviewerConfig } from "../github/appAuth.js";
import { getOpenBatchPr, getPrDiff, postReview } from "../github/prOps.js";
import { ensureClone, ensureFixesBranch, pytest, commitAndPush, checkoutDir, readRepoContext } from "../git/repo.js";
import { setFlow, comment } from "../github/issueOps.js";
import { FLOW } from "../labels.js";

const MAX_ROUNDS = 3;
type Repo = { owner: string; repo: string };

export async function runReview(
  gh: Octokit, repo: Repo, cfg: AppConfig, worker: Worker,
  reviewerApiKey: string, reviewerModel: string, involved: number[],
): Promise<void> {
  const pr = await getOpenBatchPr(gh, repo);
  if (!pr) { console.error("[review] no open batch PR — run `cutpr` first"); return; }
  const reviewer = makeReviewer(reviewerApiKey, reviewerModel);
  const reviewerGh = installationOctokit(loadReviewerConfig()); // separate identity → formal reviews
  const setAll = (flow: string) => Promise.all(involved.map((n) => setFlow(gh, repo, n, flow)));

  // make the checkout available so the reviewer can read the WHOLE repo for context
  await ensureClone(repo.owner, repo.repo, await getInstallationToken(cfg));
  await ensureFixesBranch();

  for (let round = 1; round <= MAX_ROUNDS; round++) {
    const diff = await getPrDiff(gh, repo, pr.number);
    const rev = await reviewer.review(diff, pr.number, readRepoContext());
    const blocking = rev.items.filter((i) => i.severity === "blocking");
    console.error(`[review] round ${round}: ${rev.verdict}, ${blocking.length} blocking`);

    await postReview(reviewerGh, repo, pr.number, rev.verdict,
      `🤖 reviewer (${reviewerModel}) — round ${round}\n\n${rev.summary}`,
      blocking.map((i) => ({ path: i.path, line: i.line, body: i.instruction })));

    if (rev.verdict === "approve") {
      await setAll(FLOW.inReview);
      await comment(gh, repo, pr.number, `✅ reviewer approved (round ${round}). **Ready for operator merge.**`);
      console.error("[review] APPROVED — awaiting operator merge");
      return;
    }

    // request_changes → revise the fixes branch to address blocking items
    await setAll(FLOW.changesRequested);
    const token = await getInstallationToken(cfg);
    await ensureClone(repo.owner, repo.repo, token);
    await ensureFixesBranch();
    const before = await pytest();
    const instr = blocking.map((i) => `- ${i.path}:${i.line} — ${i.instruction}`).join("\n");
    await worker.fix({
      kind: "fix", issueNumber: pr.number, title: "Revise to address PR review",
      body: `Apply these review changes to the code:\n${instr}`, area: "backend", worktreeDir: checkoutDir(),
    });
    const after = await pytest();
    const newFails = [...after.failures].filter((f) => !before.failures.has(f));
    if (after.broke || newFails.length) {
      await setAll(FLOW.stuck);
      await comment(gh, repo, pr.number, `🤖 revision broke tests (${after.broke ? "collection" : newFails.join(", ")}) — needs a human.`);
      return;
    }
    const fresh = await getInstallationToken(cfg);
    const landed = await commitAndPush(repo.owner, repo.repo, fresh, `revise: address review round ${round}`);
    if (!landed.ok) { await setAll(FLOW.stuck); return; }
    console.error(`[review] revised + pushed ${landed.sha}; re-reviewing`);
  }

  await setAll(FLOW.stuck);
  await comment(gh, repo, (await getOpenBatchPr(gh, repo))!.number, `🤖 ${MAX_ROUNDS} review rounds without approval — needs a human.`);
}
