// The worker abstraction — the seam that makes the Pi-vs-opencode bake-off a
// config flip (RFC-0002 Phase 0). The orchestrator only ever talks to this
// interface; adapters (piAdapter, opencodeAdapter) implement it.

export type Area = "backend" | "ui" | "infra" | "docs";
export type Severity = "high" | "med" | "low";

/** Structured verdict the TRIAGER must return (JSON — the orchestrator parses,
 *  never scrapes prose). Cheap models are weak at schema adherence, so the
 *  adapter is responsible for validate-and-retry until this shape is met. */
export interface TriageVerdict {
  area: Area;
  severity: Severity;
  /** well-specified enough to attempt now? */
  actionable: boolean;
  /** if not actionable, the question to ask the operator */
  needsInfo?: string;
  /** one-line root-cause hypothesis */
  hypothesis: string;
  /** recommend the fleet attempt it? (operator still gates) */
  recommend: boolean;
}

/** Result a SPECIALIST returns after attempting a fix in its worktree. */
export interface FixResult {
  /** did local tests/lint pass? (the pre-land gate) */
  testsGreen: boolean;
  /** short human summary of the change (goes in the commit + PR) */
  summary: string;
  /** files touched (for audit + routing back on review) */
  filesChanged: string[];
  /** the worker's own confidence note / caveats */
  notes?: string;
}

/** A single actionable item parsed from Claude's PR review (Phase 1). */
export interface ReviewWorkItem {
  file: string;
  line: number;
  severity: "blocking" | "nit";
  instruction: string;
  threadId: string;
}

export interface TriageTask {
  kind: "triage";
  issueNumber: number;
  title: string;
  body: string;
}

export interface FixTask {
  kind: "fix";
  issueNumber: number;
  title: string;
  body: string;
  area: Area;
  worktreeDir: string; // isolated checkout on the `fixes` branch
  /** the dispatched specialist's knowledge/prompt + model (description-based dispatch) */
  agentPrompt?: string;
  agentModel?: string;
  /** present when this is a revise-from-review pass (Phase 1) */
  reviewItem?: ReviewWorkItem;
}

export type WorkerTask = TriageTask | FixTask;

/** Every LLM leaf goes through here. label = which model/harness ran, for
 *  Langfuse attribution + the bake-off comparison. */
export interface Worker {
  readonly harness: "pi" | "opencode" | "direct";
  triage(task: TriageTask): Promise<TriageVerdict>;
  fix(task: FixTask): Promise<FixResult>;
}
