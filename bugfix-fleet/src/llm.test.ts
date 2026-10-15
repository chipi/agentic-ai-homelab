// One Langfuse trace per LLM leaf, holding the gateway's costed generation (2026-10-15).
//
// The fleet used to write its own trace + generation (tokens, no cost) while the LiteLLM gateway
// logged the same call as a separate trace (model, tokens, cost) — two unrelated records per call.
// Through the gateway the fleet now creates the trace first and hands its id to the gateway as
// `existing_trace_id`, which adds its generation to that trace and leaves the trace to the fleet.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const generations: unknown[] = [];
vi.mock("langfuse", () => ({
  Langfuse: class {
    trace() {
      return { id: "trace-123", generation: (g: unknown) => generations.push(g) };
    }
    async flushAsync() {}
  },
}));

const meta = { phase: "fix" as const, issue: 7, area: "a" };
let bodies: any[] = [];

async function load(baseUrl: string) {
  vi.resetModules();
  process.env.LLM_BASE_URL = baseUrl;
  process.env.LANGFUSE_PUBLIC_KEY = "pk";
  process.env.LANGFUSE_SECRET_KEY = "sk";
  return import("./llm.js");
}

beforeEach(() => {
  bodies = [];
  generations.length = 0;
  vi.stubGlobal("fetch", async (_url: string, init: any) => {
    bodies.push(JSON.parse(init.body));
    return {
      ok: true,
      json: async () => ({
        choices: [{ message: { content: "{}" } }],
        usage: { prompt_tokens: 1, completion_tokens: 1, total_tokens: 2 },
      }),
    };
  });
});

afterEach(() => {
  vi.unstubAllGlobals();
  delete process.env.LLM_BASE_URL;
});

describe("orChat → Langfuse", () => {
  it("through the gateway: the call carries the trace, and the fleet writes no duplicate", async () => {
    const { orChat } = await load("http://homelab:4001/v1");
    await orChat("k", "fleet-bugfix-pro", "s", "u", meta);
    expect(bodies[0].metadata).toEqual({ existing_trace_id: "trace-123", generation_name: "fix" });
    expect(generations).toHaveLength(0);
  });

  it("OpenRouter direct: no metadata, the fleet keeps its own generation", async () => {
    const { orChat } = await load("https://openrouter.ai/api/v1");
    await orChat("k", "deepseek/deepseek-v4-pro", "s", "u", meta);
    expect(bodies[0].metadata).toBeUndefined();
    expect(generations).toHaveLength(1);
  });
});
