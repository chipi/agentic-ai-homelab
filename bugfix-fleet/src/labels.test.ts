import { describe, it, expect } from "vitest";
import { ENTRY_LABEL, FLOW, AREA, SEV, ALL_MANAGED_LABELS } from "./labels.js";

describe("labels", () => {
  it("ENTRY_LABEL is 'bug'", () => {
    expect(ENTRY_LABEL).toBe("bug");
  });

  it("FLOW values all have 'flow:' prefix", () => {
    for (const v of Object.values(FLOW)) {
      expect(v).toMatch(/^flow:/);
    }
  });

  it("FLOW values are unique", () => {
    const vals = Object.values(FLOW);
    expect(new Set(vals).size).toBe(vals.length);
  });

  it("AREA values all have 'area:' prefix", () => {
    for (const v of Object.values(AREA)) {
      expect(v).toMatch(/^area:/);
    }
  });

  it("SEV values all have 'sev:' prefix", () => {
    for (const v of Object.values(SEV)) {
      expect(v).toMatch(/^sev:/);
    }
  });

  it("ALL_MANAGED_LABELS contains all FLOW, AREA, SEV labels", () => {
    const names = new Set(ALL_MANAGED_LABELS.map((l) => l.name));
    for (const v of [...Object.values(FLOW), ...Object.values(AREA), ...Object.values(SEV)]) {
      expect(names.has(v), `missing label: ${v}`).toBe(true);
    }
  });

  it("ALL_MANAGED_LABELS has no duplicate names", () => {
    const names = ALL_MANAGED_LABELS.map((l) => l.name);
    expect(new Set(names).size).toBe(names.length);
  });

  it("ALL_MANAGED_LABELS every entry has name, color, description", () => {
    for (const l of ALL_MANAGED_LABELS) {
      expect(typeof l.name).toBe("string");
      expect(l.name.length).toBeGreaterThan(0);
      expect(typeof l.color).toBe("string");
      expect(l.color).toMatch(/^[0-9a-f]{6}$/);
      expect(typeof l.description).toBe("string");
    }
  });
});
