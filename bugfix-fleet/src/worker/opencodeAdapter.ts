// opencode worker adapter — drives an `opencode serve` HTTP server via
// @opencode-ai/sdk (RFC-0002). opencode gives subagents + NATIVE structured
// output (JSON schema + StructuredOutput tool + retry) — so the triager's
// schema-adherence on cheap models is handled for us. This is the "configure a
// fleet" side of the bake-off.
//
// STATUS: skeleton. TODOs are the real opencode integration.

import { Worker, TriageTask, TriageVerdict, FixTask, FixResult } from "./types.js";
import { TRIAGE_SCHEMA } from "./schemas.js";
import { trace } from "../observability/langfuse.js";

export interface OpencodeOptions {
  serverUrl: string; // an `opencode serve` instance
  triageAgent: string; // configured agent (cheap model) in opencode.json
  fixAgentByArea: Record<string, string>; // area -> configured specialist agent
}

export function makeOpencodeWorker(opts: OpencodeOptions): Worker {
  return {
    harness: "opencode",

    async triage(task: TriageTask): Promise<TriageVerdict> {
      return trace("opencode.triage", opts.triageAgent, task.issueNumber, async () => {
        // TODO(opencode): createOpencodeClient(serverUrl); session.create();
        // prompt the triageAgent over the issue text; request structured output
        // with TRIAGE_SCHEMA (native — retry handled). Return parsed verdict.
        throw new Error("opencode triage not implemented — Phase 0 spike");
      });
    },

    async fix(task: FixTask): Promise<FixResult> {
      return trace("opencode.fix", opts.fixAgentByArea[task.area] ?? "build", task.issueNumber, async () => {
        // TODO(opencode): run the area specialist agent with cwd=worktreeDir;
        // goal = fix issue #N (or address task.reviewItem). Return FixResult.
        throw new Error("opencode fix not implemented — Phase 0 spike");
      });
    },
  };
}

void TRIAGE_SCHEMA;
