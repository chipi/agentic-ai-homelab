import { describe, it, expect } from "vitest";
import { TRIAGE_SCHEMA, FIX_RESULT_SCHEMA } from "./schemas.js";

describe("TRIAGE_SCHEMA", () => {
  it("is an object schema", () => {
    expect(TRIAGE_SCHEMA.type).toBe("object");
  });

  it("has no additionalProperties", () => {
    expect(TRIAGE_SCHEMA.additionalProperties).toBe(false);
  });

  it("required fields are present and correct", () => {
    const req = TRIAGE_SCHEMA.required as readonly string[];
    expect(req).toContain("area");
    expect(req).toContain("severity");
    expect(req).toContain("actionable");
    expect(req).toContain("hypothesis");
    expect(req).toContain("recommend");
  });

  it("area enum covers exactly backend/ui/infra/docs", () => {
    const vals = (TRIAGE_SCHEMA.properties.area as { enum: readonly string[] }).enum;
    expect([...vals].sort()).toEqual(["backend", "docs", "infra", "ui"]);
  });

  it("severity enum covers exactly high/med/low", () => {
    const vals = (TRIAGE_SCHEMA.properties.severity as { enum: readonly string[] }).enum;
    expect([...vals].sort()).toEqual(["high", "low", "med"]);
  });

  it("needsInfo is NOT required (optional clarification field)", () => {
    const req = TRIAGE_SCHEMA.required as readonly string[];
    expect(req).not.toContain("needsInfo");
  });
});

describe("FIX_RESULT_SCHEMA", () => {
  it("is an object schema", () => {
    expect(FIX_RESULT_SCHEMA.type).toBe("object");
  });

  it("has no additionalProperties", () => {
    expect(FIX_RESULT_SCHEMA.additionalProperties).toBe(false);
  });

  it("required fields are summary and filesChanged", () => {
    const req = FIX_RESULT_SCHEMA.required as readonly string[];
    expect(req).toContain("summary");
    expect(req).toContain("filesChanged");
  });

  it("notes is NOT required (optional)", () => {
    const req = FIX_RESULT_SCHEMA.required as readonly string[];
    expect(req).not.toContain("notes");
  });

  it("filesChanged is an array of strings", () => {
    const fc = FIX_RESULT_SCHEMA.properties.filesChanged as { type: string; items: { type: string } };
    expect(fc.type).toBe("array");
    expect(fc.items.type).toBe("string");
  });
});
