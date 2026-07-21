// The reviewer — reviews the WHOLE PR diff and emits DUAL output (RFC-0002):
//   • human-facing: summary + inline comments (posted via the Review API)
//   • machine-facing: structured JSON the orchestrator dispatches back to workers
// Pluggable model (REVIEWER_MODEL): a stand-in now (e.g. GLM 5.2), Claude later —
// a config change, because the reviewer is a self-hosted job, not a fixed Action.

import { trace } from "../observability/langfuse.js";
import { orChat } from "../llm.js";

export interface ReviewItem {
  path: string;
  line: number;
  severity: "blocking" | "nit";
  instruction: string;
}
export interface Review {
  verdict: "approve" | "request_changes";
  summary: string;
  items: ReviewItem[];
}

const REVIEW_SYS =
  'You are a strict but fair code reviewer for a batch bug-fix PR. You are given the unified diff. ' +
  'Judge correctness (does each change actually fix its bug) AND robustness — explicitly check for ' +
  'unhandled EDGE CASES introduced or left behind: division by zero, empty/None inputs, off-by-one, ' +
  'boundary values. A fix that passes the given tests but still crashes or misbehaves on an obvious ' +
  'untested edge case IS a blocking issue. ' +
  'Reply with ONLY a JSON object (no prose, no fences): ' +
  '{"verdict":"approve|request_changes","summary":"overall assessment", ' +
  '"items":[{"path":"src/x.py","line":12,"severity":"blocking|nit","instruction":"what to change and why"}]}. ' +
  'Use "blocking" only for real correctness/safety problems that must change before merge; "nit" for minor suggestions. ' +
  'verdict=request_changes iff there is at least one blocking item. line = a line number present in the diff.';

export function makeReviewer(apiKey: string, model: string) {
  return {
    model,
    async review(diff: string, pull: number, context?: { path: string; content: string }[]): Promise<Review> {
      return trace("reviewer.review", model, pull, async () => {
        const ctx = context?.length
          ? `=== repository files (for context — judge the diff against the ACTUAL code, e.g. constants/config that define intended behavior) ===\n` +
            context.map((f) => `--- ${f.path} ---\n${f.content}`).join("\n\n") + "\n\n"
          : "";
        const raw = await orChat(apiKey, model, REVIEW_SYS, `${ctx}=== PR #${pull} diff ===\n\n${diff}`, { phase: "review", issue: pull });
        const m = raw.match(/\{[\s\S]*\}/);
        const o = JSON.parse(m ? m[0] : raw);
        const items: ReviewItem[] = Array.isArray(o.items) ? o.items : [];
        const verdict = o.verdict === "request_changes" || items.some((i) => i.severity === "blocking")
          ? "request_changes" : "approve";
        return { verdict, summary: String(o.summary ?? ""), items };
      });
    },
  };
}
