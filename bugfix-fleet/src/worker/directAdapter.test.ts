import { describe, it, expect } from "vitest";
import { parseVerdict } from "./directAdapter.js";

describe("parseVerdict", () => {
  it("happy path — clean JSON object", () => {
    const raw = JSON.stringify({
      area: "backend",
      severity: "high",
      actionable: true,
      needsInfo: "",
      hypothesis: "null deref on empty response",
      recommend: true,
    });
    const v = parseVerdict(raw);
    expect(v.area).toBe("backend");
    expect(v.severity).toBe("high");
    expect(v.actionable).toBe(true);
    expect(v.hypothesis).toBe("null deref on empty response");
    expect(v.recommend).toBe(true);
    // empty needsInfo string → coerced to undefined
    expect(v.needsInfo).toBeUndefined();
  });

  it("extracts JSON embedded in prose (the regex path)", () => {
    const raw = `Here is my verdict: {"area":"infra","severity":"low","actionable":false,"needsInfo":"which env?","hypothesis":"misconfigured env var","recommend":false} done.`;
    const v = parseVerdict(raw);
    expect(v.area).toBe("infra");
    expect(v.severity).toBe("low");
    expect(v.actionable).toBe(false);
    expect(v.needsInfo).toBe("which env?");
    expect(v.recommend).toBe(false);
  });

  it("needsInfo present and non-empty → preserved as string", () => {
    const raw = JSON.stringify({
      area: "ui",
      severity: "med",
      actionable: false,
      needsInfo: "What browser version?",
      hypothesis: "CSS regression",
      recommend: false,
    });
    const v = parseVerdict(raw);
    expect(v.needsInfo).toBe("What browser version?");
  });

  it("throws on unknown area", () => {
    const raw = JSON.stringify({
      area: "network", // not in enum
      severity: "high",
      actionable: true,
      hypothesis: "x",
      recommend: true,
    });
    expect(() => parseVerdict(raw)).toThrow(/bad area/);
  });

  it("throws on unknown severity", () => {
    const raw = JSON.stringify({
      area: "backend",
      severity: "critical", // not in enum
      actionable: true,
      hypothesis: "x",
      recommend: true,
    });
    expect(() => parseVerdict(raw)).toThrow(/bad severity/);
  });

  it("throws when actionable is not boolean", () => {
    const raw = JSON.stringify({
      area: "docs",
      severity: "low",
      actionable: "yes", // wrong type
      hypothesis: "x",
      recommend: true,
    });
    expect(() => parseVerdict(raw)).toThrow(/actionable not boolean/);
  });

  it("throws on unparseable JSON", () => {
    expect(() => parseVerdict("not json at all")).toThrow();
  });

  it("all four valid areas are accepted", () => {
    for (const area of ["backend", "ui", "infra", "docs"] as const) {
      const raw = JSON.stringify({ area, severity: "low", actionable: true, hypothesis: "h", recommend: false });
      expect(() => parseVerdict(raw)).not.toThrow();
    }
  });

  it("all three valid severities are accepted", () => {
    for (const severity of ["high", "med", "low"] as const) {
      const raw = JSON.stringify({ area: "backend", severity, actionable: true, hypothesis: "h", recommend: false });
      expect(() => parseVerdict(raw)).not.toThrow();
    }
  });

  it("recommend coerced from truthy (1) to boolean true", () => {
    // Boolean(1) = true — matches the `Boolean(o.recommend)` coercion in source
    const raw = JSON.stringify({
      area: "backend",
      severity: "med",
      actionable: true,
      hypothesis: "x",
      recommend: 1, // number, truthy
    });
    const v = parseVerdict(raw);
    expect(v.recommend).toBe(true);
  });
});
