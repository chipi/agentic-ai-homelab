// GitHub labels ARE the state machine (RFC-0002). No separate DB — the pipeline
// state is visible in the issue list. The orchestrator only ever advances an
// issue by swapping these labels.

export const ENTRY_LABEL = "bug"; // operator-applied trigger; nothing else moves

export const FLOW = {
  triaging: "flow:triaging",
  needsInfo: "flow:needs-info", // triager wants clarification from operator
  approved: "flow:approved", // operator greenlit (the go gate)
  fixing: "flow:fixing",
  fixed: "flow:fixed", // landed on the `fixes` branch, awaiting batch PR
  inReview: "flow:in-review", // batch PR open, Claude reviewing
  changesRequested: "flow:changes-requested",
  stuck: "flow:stuck", // loop exhausted / tests red / conflict → operator
  shipped: "flow:shipped", // batch PR merged to main + deployed
} as const;

export const AREA = {
  backend: "area:backend",
  ui: "area:ui",
  infra: "area:infra",
  docs: "area:docs",
} as const;

export const SEV = { high: "sev:high", med: "sev:med", low: "sev:low" } as const;

// Definitions the orchestrator ensures exist on the target repo at startup.
export const ALL_MANAGED_LABELS: { name: string; color: string; description: string }[] = [
  { name: FLOW.triaging, color: "fbca04", description: "bug-fix fleet: triage running" },
  { name: FLOW.needsInfo, color: "d4c5f9", description: "bug-fix fleet: needs operator info" },
  { name: FLOW.approved, color: "0e8a16", description: "bug-fix fleet: operator approved" },
  { name: FLOW.fixing, color: "1d76db", description: "bug-fix fleet: worker fixing" },
  { name: FLOW.fixed, color: "0e8a16", description: "bug-fix fleet: on fixes branch" },
  { name: FLOW.inReview, color: "5319e7", description: "bug-fix fleet: Claude reviewing PR" },
  { name: FLOW.changesRequested, color: "e99695", description: "bug-fix fleet: revise loop" },
  { name: FLOW.stuck, color: "b60205", description: "bug-fix fleet: needs operator" },
  { name: FLOW.shipped, color: "c2e0c6", description: "bug-fix fleet: shipped" },
  ...Object.values(AREA).map((n) => ({ name: n, color: "bfd4f2", description: "bug-fix fleet: area" })),
  ...Object.values(SEV).map((n) => ({ name: n, color: "fef2c0", description: "bug-fix fleet: severity" })),
];
