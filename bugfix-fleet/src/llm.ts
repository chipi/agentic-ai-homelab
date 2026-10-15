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

// Chat endpoint: OpenRouter direct by default, but override to the homelab LiteLLM
// gateway (LLM_BASE_URL=http://homelab:4001/v1) to route every call through the
// gateway — per-consumer virtual-key budget, spend metering, and gateway-side
// Langfuse. When LLM_API_KEY is set (the litellm virtual key) it overrides the
// per-call apiKey; the model names then become litellm aliases (fleet-bugfix-*).
const LLM_BASE_URL = (process.env.LLM_BASE_URL ?? "https://openrouter.ai/api/v1").replace(/\/+$/, "");
const LLM_API_KEY = process.env.LLM_API_KEY;

// Through the gateway, the gateway logs each call to Langfuse itself (model, tokens, cost).
const VIA_GATEWAY = !LLM_BASE_URL.includes("openrouter.ai");

export async function orChat(
  apiKey: string, model: string, system: string, user: string, meta: LlmMeta,
): Promise<string> {
  const start = new Date();
  // The trace exists before the call so the gateway can add its generation to it:
  // `existing_trace_id` joins it without overwriting the trace's name/input/output.
  const client = langfuse();
  const t = client?.trace({
    name: `${meta.phase}-#${meta.issue}`,
    tags: ["bugfix-fleet", meta.phase, ...(meta.area ? [`area:${meta.area}`] : [])],
    metadata: { issue: meta.issue, area: meta.area, harness: meta.harness ?? "direct" },
  });
  const res = await fetch(`${LLM_BASE_URL}/chat/completions`, {
    method: "POST",
    headers: { Authorization: `Bearer ${LLM_API_KEY ?? apiKey}`, "Content-Type": "application/json" },
    body: JSON.stringify({
      model, messages: [{ role: "system", content: system }, { role: "user", content: user }],
      response_format: { type: "json_object" }, temperature: meta.phase === "dispatch" ? 0 : 0.1,
      ...(t && VIA_GATEWAY ? { metadata: { existing_trace_id: t.id, generation_name: meta.phase } } : {}),
    }),
  });
  if (!res.ok) throw new Error(`LLM gateway ${res.status}: ${(await res.text()).slice(0, 300)}`);
  const j: any = await res.json();
  const content: string = j.choices?.[0]?.message?.content ?? "";
  const u = j.usage;

  // OpenRouter direct logs nothing, so the fleet records the generation; through the gateway
  // that would be a cost-less duplicate of the gateway's own.
  if (t && !VIA_GATEWAY) {
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
