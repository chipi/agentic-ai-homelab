// MVP entry — one-shot poll (no webhook yet). Ensures the managed labels exist,
// then runs Flow A (triage) over every open `bug` issue that hasn't been triaged.
// Run: node --env-file=.env dist/main.js
//
// Worker backend chosen by HARNESS: direct | opencode | pi.

import { installationOctokit, loadAppConfig } from "./github/appAuth.js";
import { makeDirectWorker } from "./worker/directAdapter.js";
import { makeOrchestrator } from "./orchestrator.js";
import { ALL_MANAGED_LABELS, ENTRY_LABEL, FLOW } from "./labels.js";
import { Worker } from "./worker/types.js";
import { openBatchPr } from "./github/prOps.js";
import { runReview } from "./flows/review.js";
import { setFlow } from "./github/issueOps.js";

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

async function listBugIssues(gh: any, repo: Repo) {
  const { data } = await gh.issues.listForRepo({ ...repo, labels: ENTRY_LABEL, state: "open" });
  return (data as any[]).filter((i) => !i.pull_request).map((i) => ({
    number: i.number, title: i.title, body: i.body ?? "",
    labels: (i.labels as any[]).map((l) => (typeof l === "string" ? l : l.name)),
  }));
}

async function main(): Promise<void> {
  const cmd = process.argv[2] ?? "poll";
  const repo: Repo = { owner: process.env.TARGET_OWNER!, repo: process.env.TARGET_REPO! };
  const cfg = loadAppConfig();
  const gh = installationOctokit(cfg);
  const worker = buildWorker();
  console.error(`[main] cmd=${cmd} · ${repo.owner}/${repo.repo} · harness=${worker.harness}`);
  await ensureLabels(gh, repo);
  const issues = await listBugIssues(gh, repo);

  if (cmd === "poll") {
    const orch = makeOrchestrator(gh, repo, cfg, worker);
    for (const v of issues) {
      if (v.labels.includes(FLOW.approved)) { console.error(`\n=== FIX #${v.number}: ${v.title} ===`); await orch.onIssueLabeled(v, FLOW.approved); }
      else if (!v.labels.some((l) => l.startsWith("flow:"))) { console.error(`\n=== TRIAGE #${v.number}: ${v.title} ===`); await orch.onIssueLabeled(v, ENTRY_LABEL); }
      else console.error(`  #${v.number} in ${v.labels.filter((l) => l.startsWith("flow:")).join(",")} — no action`);
    }
  } else if (cmd === "cutpr") {
    const fixed = issues.filter((v) => v.labels.includes(FLOW.fixed)).map((v) => v.number);
    if (!fixed.length) { console.error("[cutpr] no flow:fixed issues to batch"); }
    else {
      const pr = await openBatchPr(gh, repo, fixed);
      for (const n of fixed) await setFlow(gh, repo, n, FLOW.inReview);
      console.error(`[cutpr] PR #${pr.number} — closes ${fixed.map((n) => `#${n}`).join(", ")}`);
    }
  } else if (cmd === "review") {
    const involved = issues.filter((v) =>
      [FLOW.inReview, FLOW.changesRequested, FLOW.fixed].some((f) => v.labels.includes(f))).map((v) => v.number);
    await runReview(gh, repo, cfg, worker, process.env.OPENROUTER_API_KEY!, process.env.REVIEWER_MODEL!, involved);
  } else {
    console.error(`[main] unknown cmd '${cmd}' (poll | cutpr | review)`);
  }
  console.error("\n[main] done.");
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
