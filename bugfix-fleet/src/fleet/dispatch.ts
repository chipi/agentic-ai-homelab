// Description-based dispatch — the thing to see work. Given an issue and the
// fleet's agent DESCRIPTIONS, an LLM picks the best-fit agent (semantic match on
// the descriptions), exactly how opencode/Claude select subagents. This replaces
// a hardcoded area→agent map with description-driven routing.

import { Agent } from "./registry.js";
import { trace } from "../observability/langfuse.js";
import { orChat } from "../llm.js";

const DISPATCH_SYS =
  'You are a dispatcher routing a bug to the best-fit specialist agent. You are given the ' +
  'issue and a list of agents with their descriptions. Pick the ONE agent whose description ' +
  'best matches the bug. Reply with ONLY a JSON object (no prose, no fences): ' +
  '{"agent":"<agent name>","reason":"one line why"}. The agent name must be exactly one from the list.';

export interface Dispatch {
  agent: Agent;
  reason: string;
}

export async function dispatchAgent(
  apiKey: string, model: string, agents: Agent[],
  issue: { number: number; title: string; body: string },
): Promise<Dispatch> {
  return trace("dispatch", model, issue.number, async () => {
    const roster = agents.map((a) => `- ${a.name}: ${a.description}`).join("\n");
    const user = `Bug #${issue.number}: ${issue.title}\n${issue.body}\n\n=== agents ===\n${roster}`;
    const raw = await orChat(apiKey, model, DISPATCH_SYS, user, { phase: "dispatch", issue: issue.number });
    const o = JSON.parse((raw.match(/\{[\s\S]*\}/) || [raw])[0]);
    const agent = agents.find((a) => a.name === o.agent)
      ?? agents.find((a) => a.name.toLowerCase() === String(o.agent).toLowerCase());
    if (!agent) throw new Error(`dispatcher picked unknown agent '${o.agent}'`);
    return { agent, reason: String(o.reason ?? "") };
  });
}
