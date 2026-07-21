// JSON Schemas the workers must satisfy. Both adapters force output to these;
// opencode does it natively (StructuredOutput+retry), Pi we implement retry.

export const TRIAGE_SCHEMA = {
  type: "object",
  additionalProperties: false,
  required: ["area", "severity", "actionable", "hypothesis", "recommend"],
  properties: {
    area: { type: "string", enum: ["backend", "ui", "infra", "docs"] },
    severity: { type: "string", enum: ["high", "med", "low"] },
    actionable: { type: "boolean", description: "specified enough to attempt now" },
    needsInfo: { type: "string", description: "question for the operator if not actionable" },
    hypothesis: { type: "string", description: "one-line root-cause hypothesis" },
    recommend: { type: "boolean", description: "recommend the fleet attempt it" },
  },
} as const;

export const FIX_RESULT_SCHEMA = {
  type: "object",
  additionalProperties: false,
  required: ["summary", "filesChanged"],
  properties: {
    summary: { type: "string" },
    filesChanged: { type: "array", items: { type: "string" } },
    notes: { type: "string" },
  },
} as const;
