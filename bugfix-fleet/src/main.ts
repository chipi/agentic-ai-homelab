// MVP entry — one-shot poll (no webhook yet). Ensures the managed labels exist,
// then runs Flow A (triage) over every open `bug` issue that hasn't been triaged.
// Run: node --env-file=.env dist/main.js
//
// Worker backend chosen by HARNESS: direct | opencode | pi.

import { installationOctokit, loadAppConfig } from "./github/appAuth.js";
import { makeDirectWorker } from "./worker/directAdapter.js";
import { makeOrchestrator } from "./orchestrator.js";
import { ALL_MANAGED_LABELS, ENTRY_LABEL } from "./labels.js";
import { Worker } from "./worker/types.js";

type Repo = { owner: string; repo: string };

async function ensureLabels(gh: any, repo: Repo): Promise<void> {
  for (const l of ALL_MANAGED_LABELS) {
    try {
      await gh.issues.getLabel({ ...repo, name: l.name });
    } catch {
      await gh.issues.createLabel({ ...repo, ...l }).catch(() => {});
    }
  }
}

function buildWorker(): Worker {
  const harness = process.env.HARNESS ?? "direct";
  const common = {
    apiKey: process.env.OPENROUTER_API_KEY!,
    triageModel: process.env.TRIAGE_MODEL!,
    fixModel: process.env.FIX_MODEL!,
  };
  // opencode/pi adapters land next; until then everything runs on the direct baseline.
  if (harness === "direct") return makeDirectWorker(common);
  console.error(`[main] HARNESS=${harness} adapter not wired yet — using direct baseline`);
  return makeDirectWorker(common);
}

async function main(): Promise<void> {
  const repo: Repo = { owner: process.env.TARGET_OWNER!, repo: process.env.TARGET_REPO! };
  const gh = installationOctokit(loadAppConfig());
  const worker = buildWorker();
  const orch = makeOrchestrator(gh, repo, worker);

  console.error(`[main] ${repo.owner}/${repo.repo} · harness=${worker.harness} · triage=${process.env.TRIAGE_MODEL}`);
  await ensureLabels(gh, repo);

  const { data } = await gh.issues.listForRepo({ ...repo, labels: ENTRY_LABEL, state: "open" });
  const issues = data.filter((i: any) => !i.pull_request);
  console.error(`[main] ${issues.length} open bug issue(s)`);

  for (const i of issues) {
    const labels = (i.labels as any[]).map((l) => (typeof l === "string" ? l : l.name));
    if (labels.some((l) => l.startsWith("flow:"))) {
      console.error(`  #${i.number} already in-flow — skip`);
      continue;
    }
    console.error(`\n=== triage #${i.number}: ${i.title} ===`);
    await orch.onIssueLabeled(
      { number: i.number, title: i.title, body: i.body ?? "", labels },
      ENTRY_LABEL,
    );
  }
  console.error("\n[main] done.");
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
