// The orchestrator — DETERMINISTIC control loop (RFC-0002). It reacts to GitHub
// state and drives the flows; LLMs are only inside worker.triage/fix. No LLM
// decides the pipeline.
//
// MVP: reacts to two signals (webhook or poll):
//   • issue gains `bug`              → Flow A (triage)
//   • issue gains `flow:approved`    → Flow B (fix)
// Phase 1 adds the PR-review + feedback loop.

import { Octokit } from "@octokit/rest";
import { Worker } from "./worker/types.js";
import { AppConfig } from "./github/appAuth.js";
import { runTriage } from "./flows/triage.js";
import { runFix } from "./flows/fix.js";
import { ENTRY_LABEL, FLOW, AREA } from "./labels.js";

type Repo = { owner: string; repo: string };

export interface Orchestrator {
  onIssueLabeled(issue: IssueView, label: string): Promise<void>;
}

export interface IssueView {
  number: number;
  title: string;
  body: string;
  labels: string[];
}

export function makeOrchestrator(gh: Octokit, repo: Repo, cfg: AppConfig, worker: Worker): Orchestrator {
  return {
    async onIssueLabeled(issue, label) {
      // Flow A: a bug appeared and hasn't been triaged yet.
      if (label === ENTRY_LABEL && !issue.labels.some((l) => l.startsWith("flow:"))) {
        await runTriage(gh, repo, worker, issue);
        return;
      }
      // Flow B: operator approved → dispatch to the routed specialist.
      if (label === FLOW.approved) {
        const area = (Object.entries(AREA).find(([, v]) => issue.labels.includes(v))?.[0] ?? "backend") as
          "backend" | "ui" | "infra" | "docs";
        await runFix(gh, repo, cfg, worker, { ...issue, area });
        return;
      }
    },
  };
}
