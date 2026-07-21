// Flow A — Triage (RFC-0002 MVP). bug-labeled issue → triager (cheap LLM,
// structured verdict) → orchestrator applies area/sev/flow labels + posts a
// recommendation. Exercises: App+webhook, worker invocation, STRUCTURED OUTPUT
// on a cheap model (the bake-off's key axis), the label state machine.

import { Octokit } from "@octokit/rest";
import { Worker } from "../worker/types.js";
import { AREA, SEV, FLOW, ENTRY_LABEL } from "../labels.js";
import { setFlow, addLabels, comment } from "../github/issueOps.js";

export async function runTriage(
  gh: Octokit,
  repo: { owner: string; repo: string },
  worker: Worker,
  issue: { number: number; title: string; body: string; labels: string[] },
): Promise<void> {
  if (!issue.labels.includes(ENTRY_LABEL)) return; // bug-only
  await setFlow(gh, repo, issue.number, FLOW.triaging);

  const verdict = await worker.triage({
    kind: "triage",
    issueNumber: issue.number,
    title: issue.title,
    body: issue.body,
  });

  await addLabels(gh, repo, issue.number, [AREA[verdict.area], SEV[verdict.severity]]);

  if (!verdict.actionable) {
    await setFlow(gh, repo, issue.number, FLOW.needsInfo);
    await comment(gh, repo, issue.number,
      `🤖 triage (${worker.harness}): needs info before I can attempt this.\n\n> ${verdict.needsInfo}`);
    return;
  }

  // Advisory only — the operator gates go/no-go by adding flow:approved.
  await comment(gh, repo, issue.number,
    `🤖 triage (${worker.harness}) — **${verdict.area} / ${verdict.severity}**\n\n` +
    `**Hypothesis:** ${verdict.hypothesis}\n\n` +
    `**Recommendation:** ${verdict.recommend ? "attempt a fix" : "skip / needs a human"}.\n\n` +
    `_Add \`${FLOW.approved}\` to send this to the fleet._`);
  // stays in flow:triaging until the operator approves
}
