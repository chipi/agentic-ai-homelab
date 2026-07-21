// Shared OpenRouter client — the single place every LLM call goes through, so it
// logs a Langfuse generation (model, tokens, cost, latency) for EVERY leaf
// (triage/dispatch/fix/review). This is the fleet's token-spend + performance
// instrument, and the bake-off measurement rig.

import { Langfuse } from "langfuse";

let lf: Langfuse | null | undefined;
function langfuse(): Langfuse | null {
  if (lf !== undefined) return lf;
  const pk = process.env.LANGFUSE_PUBLIC_KEY, sk = process.env.LANGFUSE_SECRET_KEY;
  lf = pk && sk ? new Langfuse({ publicKey: pk, secretKey: sk, baseUrl: process.env.LANGFUSE_HOST }) : null;
  return lf;
}

export interface LlmMeta {
  phase: "triage" | "dispatch" | "fix" | "review";
  issue: number;
  area?: string;
  harness?: string;
}

export async function orChat(
  apiKey: string, model: string, system: string, user: string, meta: LlmMeta,
): Promise<string> {
  const start = new Date();
  const res = await fetch("https://openrouter.ai/api/v1/chat/completions", {
    method: "POST",
    headers: { Authorization: `Bearer ${apiKey}`, "Content-Type": "application/json" },
    body: JSON.stringify({
      model, messages: [{ role: "system", content: system }, { role: "user", content: user }],
      response_format: { type: "json_object" }, temperature: meta.phase === "dispatch" ? 0 : 0.1,
    }),
  });
  if (!res.ok) throw new Error(`OpenRouter ${res.status}: ${(await res.text()).slice(0, 300)}`);
  const j: any = await res.json();
  const content: string = j.choices?.[0]?.message?.content ?? "";
  const u = j.usage;

  const client = langfuse();
  if (client) {
    const t = client.trace({
      name: `${meta.phase}-#${meta.issue}`,
      tags: ["bugfix-fleet", meta.phase, ...(meta.area ? [`area:${meta.area}`] : [])],
      metadata: { issue: meta.issue, area: meta.area, harness: meta.harness ?? "direct" },
    });
    t.generation({
      name: meta.phase, model, startTime: start, endTime: new Date(),
      input: [{ role: "system", content: system }, { role: "user", content: user }],
      output: content,
      usage: u ? { input: u.prompt_tokens, output: u.completion_tokens, total: u.total_tokens, unit: "TOKENS" } : undefined,
      metadata: { area: meta.area },
    });
  }
  return content;
}

export async function flushLangfuse(): Promise<void> {
  const c = langfuse();
  if (c) await c.flushAsync();
}
