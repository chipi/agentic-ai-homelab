# AGENTS.md — bugfix-fleet (scoped)

MVP prototype for RFC-0002. Rules for agents working in this subproject.

- **This is a Phase-0 bake-off, not production.** Optimize for connecting
  everything end-to-end and measuring Pi vs opencode — not polish.
- **The orchestrator stays deterministic.** No LLM decides pipeline control flow;
  LLMs live only behind the `Worker` interface (triage/fix). Don't leak model
  calls into the orchestrator/flows.
- **The worker seam is sacred.** Pi and opencode are swappable adapters behind
  `src/worker/types.ts`. Keep flows harness-agnostic so the bake-off is a config flip.
- **Structured output is the point.** The triager must return valid `TRIAGE_SCHEMA`
  JSON; the orchestrator parses, never scrapes prose. Measuring how hard this is on
  cheap models (esp. on Pi, which has no native structured output) is the spike.
- **Secrets via sops on the mini** — never commit `.env`, the App `.pem`, or keys.
- **Target = the sandbox repo only** until the loop is trusted. Never point the
  MVP at a real repo without operator approval.
- **Operator gates go/no-go, merge, deploy.** The fleet proposes; it never merges
  to main or deploys.
