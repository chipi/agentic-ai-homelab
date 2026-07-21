// Thin GitHub issue helpers — the orchestrator advances state by swapping
// flow: labels. All flow: labels are mutually exclusive (setFlow clears others).

import { Octokit } from "@octokit/rest";
import { FLOW } from "../labels.js";

type Repo = { owner: string; repo: string };
const FLOW_LABELS = Object.values(FLOW) as string[];

export async function setFlow(gh: Octokit, repo: Repo, issue: number, flow: string): Promise<void> {
  const { data } = await gh.issues.listLabelsOnIssue({ ...repo, issue_number: issue });
  const current = data.map((l) => l.name);
  for (const l of current) {
    if (FLOW_LABELS.includes(l) && l !== flow) {
      await gh.issues.removeLabel({ ...repo, issue_number: issue, name: l }).catch(() => {});
    }
  }
  await gh.issues.addLabels({ ...repo, issue_number: issue, labels: [flow] });
}

export async function addLabels(gh: Octokit, repo: Repo, issue: number, labels: string[]): Promise<void> {
  await gh.issues.addLabels({ ...repo, issue_number: issue, labels });
}

export async function comment(gh: Octokit, repo: Repo, issue: number, body: string): Promise<void> {
  await gh.issues.createComment({ ...repo, issue_number: issue, body });
}
