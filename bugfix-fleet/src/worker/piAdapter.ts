// Pi worker adapter — embeds pi-agent-core in-process (RFC-0002). Pi ships 4
// tools (read/write/edit/bash) + a runtime; subagents/structured-output are
// composed by US. This adapter is where the "build a fleet from primitives"
// cost/benefit shows up in the bake-off.
//
// STATUS: skeleton. The TODOs are the actual Pi integration — the point of the
// Phase-0 spike is to fill these in and measure the effort/quality vs opencode.

import { Worker, TriageTask, TriageVerdict, FixTask, FixResult } from "./types.js";
import { TRIAGE_SCHEMA } from "./schemas.js";
import { trace } from "../observability/langfuse.js";

export interface PiOptions {
  triageModel: string; // cheap, e.g. openrouter/deepseek-...-flash
  fixModel: string; // stronger, e.g. openrouter/deepseek-...-pro
  openrouterApiKey: string;
}

export function makePiWorker(opts: PiOptions): Worker {
  return {
    harness: "pi",

    async triage(task: TriageTask): Promise<TriageVerdict> {
      return trace("pi.triage", opts.triageModel, task.issueNumber, async () => {
        // TODO(pi): run pi-agent-core with a triager system prompt + read-only
        // tools over the issue text; force TRIAGE_SCHEMA output. Pi has no
        // native structured-output, so implement validate-and-retry here (this
        // is the effort we're measuring). Return the parsed TriageVerdict.
        throw new Error("pi triage not implemented — Phase 0 spike");
      });
    },

    async fix(task: FixTask): Promise<FixResult> {
      return trace("pi.fix", opts.fixModel, task.issueNumber, async () => {
        // TODO(pi): run pi-agent-core in task.worktreeDir with read/write/edit/
        // bash; goal = fix the bug for issue #N (or address task.reviewItem).
        // Return a FixResult summary (orchestrator runs the tests, not Pi).
        throw new Error("pi fix not implemented — Phase 0 spike");
      });
    },
  };
}

void TRIAGE_SCHEMA; // referenced by the real implementation
