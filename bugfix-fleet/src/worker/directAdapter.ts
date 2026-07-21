// Direct OpenRouter adapter — the simplest possible worker: a raw chat
// completion with JSON forced + validate-and-retry. Serves two purposes:
//   1. gets Flow A running end-to-end NOW (before the harness integrations),
//   2. is the "no harness" CONTROL baseline for the Pi-vs-opencode bake-off —
//      how well does a cheap model do structured output with nothing but a
//      prompt + response_format?

import * as fs from "node:fs";
import * as path from "node:path";
import { Worker, TriageTask, TriageVerdict, FixTask, FixResult } from "./types.js";
import { trace } from "../observability/langfuse.js";

// naive source reader for the MVP: all *.py under src/ in the worktree.
function readSource(dir: string): { path: string; content: string }[] {
  const srcDir = path.join(dir, "src");
  if (!fs.existsSync(srcDir)) return [];
  const out: { path: string; content: string }[] = [];
  for (const f of fs.readdirSync(srcDir)) {
    if (f.endsWith(".py")) out.push({ path: `src/${f}`, content: fs.readFileSync(path.join(srcDir, f), "utf8") });
  }
  return out;
}

const FIX_SYS =
  'You are fixing a bug in a software repository. You are given the issue and the ' +
  'current source files. Reply with ONLY a JSON object (no prose, no fences): ' +
  '{"summary":"one-line description of the change","files":[{"path":"src/x.py","content":"<FULL corrected file contents>"}]}. ' +
  'Include ONLY files you actually changed; return their COMPLETE new contents. Preserve everything unrelated.';

export interface DirectOptions {
  apiKey: string;
  triageModel: string;
  fixModel: string;
}

// NB: comment-free schema — inline // comments in the example JSON make cheap
// models echo malformed/off-schema output. Keep the example valid JSON.
const TRIAGE_SYS =
  'You are a bug triager for a software repository. Classify the bug and reply ' +
  'with ONLY a JSON object (no prose, no markdown fences) of exactly this shape: ' +
  '{"area":"backend|ui|infra|docs","severity":"high|med|low","actionable":true,' +
  '"needsInfo":"","hypothesis":"one-line root-cause hypothesis","recommend":true}. ' +
  'area = which part of the system. actionable = specified enough to fix now. ' +
  'needsInfo = a question for the operator if not actionable, else "". ' +
  'recommend = whether the fleet should attempt a fix.';

async function orChat(apiKey: string, model: string, system: string, user: string): Promise<string> {
  const res = await fetch("https://openrouter.ai/api/v1/chat/completions", {
    method: "POST",
    headers: { Authorization: `Bearer ${apiKey}`, "Content-Type": "application/json" },
    body: JSON.stringify({
      model,
      messages: [{ role: "system", content: system }, { role: "user", content: user }],
      response_format: { type: "json_object" },
      temperature: 0.1,
    }),
  });
  if (!res.ok) throw new Error(`OpenRouter ${res.status}: ${(await res.text()).slice(0, 300)}`);
  const j: any = await res.json();
  return j.choices?.[0]?.message?.content ?? "";
}

function parseVerdict(raw: string): TriageVerdict {
  const m = raw.match(/\{[\s\S]*\}/);
  const o = JSON.parse(m ? m[0] : raw);
  if (!["backend", "ui", "infra", "docs"].includes(o.area)) throw new Error(`bad area: ${o.area}`);
  if (!["high", "med", "low"].includes(o.severity)) throw new Error(`bad severity: ${o.severity}`);
  if (typeof o.actionable !== "boolean") throw new Error("actionable not boolean");
  return {
    area: o.area, severity: o.severity, actionable: o.actionable,
    needsInfo: o.needsInfo || undefined, hypothesis: String(o.hypothesis ?? ""),
    recommend: Boolean(o.recommend),
  };
}

export function makeDirectWorker(opts: DirectOptions): Worker {
  return {
    harness: "direct",
    async triage(task: TriageTask): Promise<TriageVerdict> {
      return trace("direct.triage", opts.triageModel, task.issueNumber, async () => {
        const user = `Issue #${task.issueNumber}: ${task.title}\n\n${task.body}`;
        let lastErr: unknown;
        for (let i = 0; i < 3; i++) {
          const raw = await orChat(opts.apiKey, opts.triageModel, TRIAGE_SYS, user);
          try {
            return parseVerdict(raw);
          } catch (e) {
            lastErr = e;
            console.error(`  [direct] triage retry ${i + 1}/3: ${(e as Error).message} | raw: ${raw.slice(0, 160)}`);
          }
        }
        throw lastErr;
      });
    },
    async fix(task: FixTask): Promise<FixResult> {
      return trace("direct.fix", opts.fixModel, task.issueNumber, async () => {
        const src = readSource(task.worktreeDir);
        const filesBlock = src.map((f) => `--- ${f.path} ---\n${f.content}`).join("\n\n");
        const user =
          `Issue #${task.issueNumber}: ${task.title}\n\n${task.body}\n\n` +
          `=== current source ===\n${filesBlock}`;
        const raw = await orChat(opts.apiKey, opts.fixModel, FIX_SYS, user);
        const m = raw.match(/\{[\s\S]*\}/);
        const obj = JSON.parse(m ? m[0] : raw);
        const files: { path: string; content: string }[] = obj.files ?? [];
        if (!files.length) throw new Error("fix returned no files");
        for (const f of files) {
          const abs = path.join(task.worktreeDir, f.path);
          await fs.promises.mkdir(path.dirname(abs), { recursive: true });
          await fs.promises.writeFile(abs, f.content, "utf8");
        }
        return {
          testsGreen: false, // orchestrator runs the tests
          summary: String(obj.summary ?? `fix for #${task.issueNumber}`),
          filesChanged: files.map((f) => f.path),
        };
      });
    },
  };
}
