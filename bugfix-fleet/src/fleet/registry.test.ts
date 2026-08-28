import { describe, it, expect } from "vitest";
import { loadAgents } from "./registry.js";

describe("loadAgents", () => {
  it("returns at least one agent", () => {
    const agents = loadAgents();
    expect(agents.length).toBeGreaterThan(0);
  });

  it("every agent has required fields (name, description, model, area, systemPrompt)", () => {
    const agents = loadAgents();
    for (const a of agents) {
      expect(typeof a.name, `agent.name should be string`).toBe("string");
      expect(a.name.length, `agent.name should not be empty`).toBeGreaterThan(0);
      expect(typeof a.description).toBe("string");
      expect(a.description.length).toBeGreaterThan(0);
      expect(typeof a.model).toBe("string");
      expect(a.model.length).toBeGreaterThan(0);
      expect(typeof a.area).toBe("string");
      expect(typeof a.systemPrompt).toBe("string");
      expect(a.systemPrompt.length).toBeGreaterThan(0);
    }
  });

  it("agent names are unique", () => {
    const agents = loadAgents();
    const names = agents.map((a) => a.name);
    expect(new Set(names).size).toBe(names.length);
  });

  it("includes a 'triage' agent", () => {
    const agents = loadAgents();
    expect(agents.some((a) => a.name === "triage")).toBe(true);
  });
});
