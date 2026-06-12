# 0002 — Decision Log

Append-only log of decisions made in this repo. Each entry: what was
decided, what alternatives were considered, why this won.

Newer entries at the top. Decisions that turn out to be wrong get a follow-up
entry (don't edit the original — the trail of reasoning is the value).

---

## D-0007 — LibreChat removed from scope; Chatbox for mobile if wanted

**Date:** 2026-06-12
**Supersedes:** D-0005 (LibreChat over Open WebUI for mobile).
**Context:** Genesis-session decision D-0005 picked LibreChat as the
mobile / multi-model chat UI. Stack was deployed and templated. After
the v0.2 work landed (docs site, recipes, project-setup templates), the
operator wanted hands-on time with LibreChat before committing to
maintain the compose + docs + ACL hole long-term. That evaluation
concluded LibreChat doesn't earn its keep relative to the simpler
Chatbox path (OpenAI-compatible client, no deploy, no maintenance).
**Decision:** Remove LibreChat entirely from Pillar 2 scope. Mobile /
phone access to the local vLLM, if wanted, is via **Chatbox** pointed at
`http://<dgx-host>.<your-tailnet>.ts.net:9000`. No self-hosted chat UI
is maintained in this repo.
**Alternatives:**
- Keep LibreChat templated but mark "experimental" — rejected; either
  the maintenance cost is justified or it's not, and "experimental"
  durably rots.
- Switch to Open WebUI as the mobile path — rejected; same trade-off,
  same conclusion.
- Keep no mobile story at all — rejected; Chatbox is zero-cost to mention
  and genuinely useful for the cases that come up.
**Consequence:**
- `infra/librechat/` directory removed.
- `docs/local-ai-infra.md` no longer documents LibreChat (stack diagram,
  port list, subsection, ACL note all stripped).
- `docs/cloud-ai-workflow.md`, `docs/agent-harnesses.md`, `README.md`,
  `docs/index.md` no longer mention LibreChat in forward-looking sections.
- `docs/wip/NEXT_STEPS.md` adds "self-hosted multi-model chat UIs" to
  the deliberately-not-in-scope list.
- Tailscale ACL :3080 entry can be removed from the operator's tailnet
  ACL when they next touch it.
- `docs/history/0001-genesis.md` Phase 5 description preserved unchanged
  per append-only history convention — that's the record of what was
  tried.
- `docs/adr/ADR-0001-repo-scope.md` Pillar 2 description still mentions
  "mobile access (LibreChat)" — preserved per ADR convention
  ("supersede with a new ADR" if the high-level repo scope itself needs
  re-stating). Not warranted for this narrow component drop; the
  four-pillar structure is unchanged.

## D-0006 — Single global AGENTS.md, projects layer on top

**Date:** 2026-06-11
**Context:** Four existing project AGENTS.md files (505/631/405/281 lines)
have substantial overlap. Project rules repeat universal rules ("never push
without approval", "rebase before push", "show diff first") in slightly
different words.
**Decision:** Maintain a single source of truth at `~/.config/opencode/AGENTS.md`
+ this repo's `AGENTS.md`. Per-project files keep ONLY project-specific
content (stack tables, named ADR/RFC anchors, project-domain rules).
**Alternatives:**
- Keep current per-project copies; accept drift. Rejected — drift is the
  problem.
- Single project-level AGENTS.md that references global. Considered; will
  do this in the projects' next pass.
**Consequence:** Existing project AGENTS.md files will be deduplicated in a
later session (open thread #5 in genesis).

## D-0005 — LibreChat over Open WebUI for mobile

**Date:** 2026-06-11
**Context:** Operator wanted to chat with vLLM from phone. Options were
Chatbox (chat-only), Open WebUI (already deployed, chat + RAG, basic tools),
LibreChat (chat + RAG + MCP + agents + multi-provider).
**Decision:** Deploy LibreChat. Slim 3-container variant: api + mongodb +
meilisearch. Skip nginx (tailnet handles transport encryption); skip
vectordb + rag_api (RAG can be added later if wanted).
**Alternatives:**
- Chatbox-only — rejected as too limited; no agent/tool story.
- Repoint existing Open WebUI at coder-next — rejected as a middle option
  that doesn't justify the work.
**Consequence:** New container stack on DGX (3 services). 3080 needs to be
opened in Tailscale ACL.

## D-0004 — Passive Ollama observability (Level 1)

**Date:** 2026-06-11
**Context:** Both viable Ollama exporters
(`ghcr.io/norskhelsenett/ollama-metrics` and `frcooper/ollama-exporter`)
are **transparent proxies** — to get per-request metrics, clients must
route through the exporter instead of hitting `:11434` directly. Operator's
autoresearch pipeline currently hits `:11434` directly.
**Decision:** Run the exporter (it also polls `/api/ps` passively for model
inventory) but do not retarget any clients. Get model-inventory + RAM
gauges; live without per-request token/duration metrics for now.
**Alternatives:**
- Level 2 (selective proxy) — retarget autoresearch to `:9778`. Rejected —
  adds a dependency to a pipeline that already works.
- Level 3 (full proxy) — retarget all. Rejected — exporter becomes single
  point of failure.
**Consequence:** Limited Ollama visibility. Promotable later if/when wanted
via a one-line config change in the autoresearch client.

## D-0003 — NorskHelsenett/ollama-metrics chosen over alternatives

**Date:** 2026-06-11
**Context:** Initial guess (`ricardbejarano/ollama_exporter`) was made
without verification. Operator pushed back: "do small research and make
actual solution that works". WebSearch + `gh api` validated against both
top candidates.
**Decision:** Use `ghcr.io/norskhelsenett/ollama-metrics:latest`. Real org
behind it (Norwegian Health Network), published image (no build step), Go
single-binary (lower footprint), configurable port via env var.
**Alternatives:**
- `frcooper/ollama-exporter` — more stars (44 vs 26), Python/FastAPI, but
  no published image (must build from source). Rejected on deployment
  friction.
**Consequence:** Published image, no build step in the operator's compose.

## D-0002 — Unified port 9000 for both vLLM composes

**Date:** 2026-06-11
**Context:** `vllm-Qwen3-Coder-Next` on port 8000 collides with the DGX
`speaches` service. Operator opened tailnet ACL on 9000 to fix it. Then
asked to also move `vllm-openwebui` to 9000.
**Decision:** Both vLLM composes bind to port 9000. They're mutually
exclusive at runtime anyway (GPU contention forces it). Single port =
single tailnet ACL entry, single URL to remember.
**Alternatives:**
- Different ports (e.g., 9000 + 9001) — rejected as unnecessary FW surface
  area for two services that can't run simultaneously.
**Consequence:** `container_name` distinction handles the docker-level
collision (`vllm-coder-next` vs `vllm-openwebui`).

## D-0001 — Repo name `agentic-ai-homelab`, framed as personal not authoritative

**Date:** 2026-06-11
**Context:** Operator wanted a public repo to extract patterns from his
projects + the session's work. Wanted "agentic ai" in the name for
search relevance.
**Decision:** `agentic-ai-homelab`. "homelab" frames it as a personal
self-hosted setup (modest, recognized GH genre, sets honest expectations).
"agentic ai" stays in the name for searchability.
**Alternatives:**
- `agentic-ai-stack` — more accurate to deliverable, less personal flavor.
- `agentic-ai-best-practices` / `agentic-ai-cookbook` — rejected as
  overpromising; invites issues + PRs the operator doesn't want for a
  config repo.
- `local-agentic-ai` — too narrow (excludes cloud workflow).
**Consequence:** Repo positioning is "what I run", not "what you should run".
Reflected in README's "What this is not" section.
