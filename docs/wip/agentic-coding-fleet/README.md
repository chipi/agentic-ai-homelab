# Agentic Coding Fleet — WIP subproject tracker

Standing up a multi-agent fleet across **opencode** and **Pi**, fronted by
**OpenRouter** for cloud models (Chinese coding-model roster) and a local
**Ollama** provider for FastContext-4B recon. Two harnesses, same role design,
per-agent model assignment with hard model-locks at the gateway. Goal: take
the fleet for a test ride on one greenfield project, then graduate this work
into a published guide under a new **Agentic coding** docs section
(co-located eventually with FastContext + telemetry write-ups).

## Source guides we're implementing

- [`../fastcontext-recon-guide.md`](../fastcontext-recon-guide.md) — recon
  subagent (FastContext-4B). **Already implemented**: see
  [`infra/fastcontext/`](../../../infra/fastcontext/) for the working
  Modelfile + bug context, plus `~/.config/opencode/opencode.json`
  (`agent.explore`) and `~/.pi/rules/fastcontext.md` for the harness wiring.
- [`../multi-agent-fleet-pi-and-opencode.md`](../multi-agent-fleet-pi-and-opencode.md)
  — fleet architecture (8 roles, two review gates, 5-phase rollout).
- [`../openrouter-fleet-guide.md`](../openrouter-fleet-guide.md) — gateway
  mechanics (per-role virtual keys, Guardrails model-locks, provider
  routing).

This tracker captures what we **actually do** as we build it, the
**decisions** we make along the way, and the **test rides** we run — so when
this graduates to published docs the operator's own playbook (not a
restated guide) is what ships.

---

## Eventual publish destination

A new **`docs/agentic-coding/`** section, navigable from `mkdocs.yml`, with
roughly:

- `index.md` — overview, when to use which harness, cost reality
- `fastcontext.md` — recon engine setup (refined from
  `infra/fastcontext/README.md` + wip recon guide + lessons)
- `multi-agent-fleet.md` — the per-role topology in both harnesses, with
  the operator's actual configs
- `openrouter-setup.md` — keys, Guardrails, routing variants
- `telemetry.md` — LiteLLM + Langfuse (only after Phase 4 lands)

While we're in WIP, **everything new lives in this folder.** Promotion to
`docs/agentic-coding/` happens when the test ride is green and we have one
real-task example to anchor each page.

---

## Decisions locked

| # | Decision | Date | Notes |
|---|---|---|---|
| D1 | OpenRouter scheme: **two workspaces, one key per workspace** (opencode workspace + Pi workspace). Model-lock enforced via **workspace allowlist**, not per-key Guardrails. | 2026-06-24 (revised) | Simpler than the original 16-key proposal. Per-harness attribution preserved (workspace = harness). Per-agent attribution **also preserved** — both harnesses already pass agent metadata to OpenRouter, so the workspace dashboard shows the per-agent breakdown natively. (Original D6 claim that this was deferred was wrong — confirmed in OpenRouter dashboard 2026-06-24.) |
| D2 | **Model-locks via workspace allowlist (hard).** Workspace allowlist contains only the 5 slugs we use. Provider-routing pin **deferred** — couldn't find the workspace toggle in OR's current UI; the allowlist alone bounds the cost ceiling. Revisit if/when silent upstream-provider substitution becomes a real problem, then handle via Option #3 (per-request `provider.allow_fallbacks: false` in harness config). | 2026-06-24 (revised) | Trade-off accepted: OR may pick a different upstream provider for an allowed model (e.g. DeepSeek-direct vs Together for `deepseek/deepseek-v4-pro`) — but never a different *model*. Quality/latency might drift slightly across upstreams. Acceptable for supervised test rides. |
| D3 | Role × model map per [fleet guide §2.4](../multi-agent-fleet-pi-and-opencode.md#24-per-role-model-map-openrouter-mid-2026) — **approved as starting baseline; expect to iterate after test ride** | 2026-06-24 | Slugs to verify at `openrouter.ai/models` before paste — they drift. |
| D4 | FastContext stays **local-only**, never routes through OpenRouter | 2026-06-24 | Already wired ([`infra/fastcontext/`](../../../infra/fastcontext/)); reaffirmed for the fleet design. |
| D5 | Claude Code skipped from harness wiring; Claude remains **Gate 2** (out-of-loop diff review) per fleet guide §0 | 2026-06-24 | The fleet's deliverable is a branch/PR you open in Claude Code. |
| ~~D6~~ | ~~Per-agent attribution deferred to Phase 4~~ | 2026-06-24 | **Withdrawn same day** — OpenRouter dashboard shows per-agent breakdown natively inside each workspace; both harnesses already pass agent metadata. |
| D7 | **Local prompt/response logs enabled** at the OpenRouter workspace level (each workspace logs requests/responses to its own local-ish storage in the OR dashboard) | 2026-06-24 | Adds an inspectable trail of what each agent actually sent and got back — useful for debugging mis-routed calls, prompt drift, and Phase 3 orchestrator behavior. Cost: prompts and completions sit in OR's logging, not air-gapped — fine for non-proprietary test rides; reconsider before any work touching sensitive code. |
| D8 | **OpenRouter → Langfuse trace export enabled** (direct, no LiteLLM proxy yet) | 2026-06-24 | Builds the telemetry data pipeline from day 1; gives a real analytics surface (cost trends, per-agent rollups, conversation replay) that OR's dashboard alone doesn't. Note: "tokens per *passing* task" still requires a `task_id` propagated from orchestrator → subagents — that's the LiteLLM proxy job in Phase 4. Until then, Langfuse + OR-direct logs everything *except* the task join key. |
| D9 | **`moonshotai/kimi-k2.6` added to both workspace allowlists + Pi `models.json`** as the long-tool-call-chain builder option and Pi's general default until per-role overrides land | 2026-06-24 | Pi's pre-existing `defaultModel: moonshotai/kimi-k2.6` was outside the original 5-slug allowlist → every default Pi call would have 4xx'd. Two options were on the table: change Pi's default (Option A) or extend the allowlist (Option B). Operator picked B. Distinct-slug count is now 6 (not 5). Kimi is Pi-default-friendly *and* role-map-friendly per fleet guide §2.4. |
| D10 | **RTK skipped in opencode and Pi** — no native variant in either; rules-file workaround judged not worth the complexity | 2026-06-24 | lean-ctx covers most of the token-savings win (opencode via MCP, Pi via embedded bridge). RTK remains active in Claude Code via its native hook. Revisit if/when RTK ships an `opencode` or `pi` hook variant. |
| D11 | **FastContext PARKED for opencode**; remains active for Pi via `~/.pi/rules/fastcontext.md` | 2026-06-24 | Tested 3 subagent models (DeepSeek-V4-Flash, Kimi K2.6, plus initial Qwen 3.6 Plus); all bypass the wrapped fastcontext CLI. Deep-research workflow confirmed ZERO published opencode + FastContext integration exists (searched sst/opencode, microsoft/fastcontext, GitHub issues, blog posts). Architectural blockers: sst/opencode #4096 (subagents get full repo context, no per-subagent scoping), #7296 (task permissions hardcoded disabled). Operator's "off-the-shelf only" constraint (no custom MCP wrappers, no manual CLI) → no remaining viable path. opencode's `agent.explore` set `disable: true`, config preserved for reference. FastContext binary, Ollama model (`fastcontext-clean`), and Pi rule file all intact. |

---

## Role × model map (the baseline)

| Role | Tier | Model | OpenRouter slug (verify) | Notes |
|---|---|---|---|---|
| orchestrator | strong | GLM 5.2 | `z-ai/glm-5.2` | The one you talk to. |
| planner | strong | Qwen 3.6 Plus | `qwen/qwen3.6-plus` | 1M ctx for long plans. |
| backend | mid | DeepSeek V4 Pro | `deepseek/deepseek-v4-pro` | Swap to Kimi K2.7-Code if long tool-call chains hurt. |
| ui | mid | DeepSeek V4 Pro | `deepseek/deepseek-v4-pro` | Same. |
| tester | cheap | DeepSeek V4 Flash | `deepseek/deepseek-v4-flash` | Gate 1 catches under-mocking — see §2.4 caveats. |
| reviewer (Gate 1) | strong | GLM 5.2 | `z-ai/glm-5.2` | **Never downgrade.** Fleet's only automatic gate. |
| docs | cheap | MiMo V2.5 Pro | `xiaomi/mimo-v2.5-pro` | Fewest tokens/task. |
| debugger | strong | GLM 5.2 | `z-ai/glm-5.2` | Ambiguous, high blast radius. |
| oracle | strong | GLM 5.2 | `z-ai/glm-5.2` | Pi-only built-in; opencode equivalent would need to be authored. Skipping for now. |
| scout / explore | local | FastContext-4B | — (local Ollama) | Wired ✓. Never on OpenRouter. |

**Distinct slugs the harnesses actually call** (becomes the workspace
allowlist, per D1+D2):

- `z-ai/glm-5.2` — orchestrator, reviewer, debugger, oracle (Pi only)
- `qwen/qwen3.6-plus` — planner
- `deepseek/deepseek-v4-pro` — backend, ui
- `deepseek/deepseek-v4-flash` — tester
- `xiaomi/mimo-v2.5-pro` — docs
- `moonshotai/kimi-k2.6` — *Kimi addition 2026-06-24 per D9.* Use for
  long-tool-call-chain builder roles (backend/ui swap candidate) and as
  Pi's general default until per-role agent files override it. Fleet
  guide §2.4 flags Kimi as the strongest open-weight family for tool-
  call stability across long sessions.

Both workspaces' allowlists are identical: those 6 slugs, nothing else.

### Workspace policy (the model-lock, per D1+D2)

For **each workspace** (opencode and Pi):

- **Allowlist:** exactly the 5 slugs above. Any call outside the list
  4xx's at OpenRouter — the catastrophic spend failure is blocked.
- **Spend limit:** suggestion **$50–80/mo per workspace** (= ~$100–160/mo
  combined), matching fleet guide §11's $50–75 single-harness baseline.
  Tune after a few weeks of real usage.
- **Data policy:** training-OFF, no-log providers only
  (`data_collection: deny` — should be the account default per OR
  guide §4).
- **Provider routing:** loose default; add `:exacto` only on tool-heavy
  role calls in harness config (we apply this in `opencode.json` /
  Pi agent files, not in the workspace settings).

---

## Slug verification (Phase 0 work, op handles)

Each row needs to be confirmed live at `openrouter.ai/models` before we
key-mint. Strike when verified:

- [ ] `z-ai/glm-5.2`
- [ ] `qwen/qwen3.6-plus`
- [ ] `deepseek/deepseek-v4-pro`
- [ ] `deepseek/deepseek-v4-flash`
- [ ] `xiaomi/mimo-v2.5-pro`
- [ ] (fallback) `moonshotai/kimi-k2.7-code` for builders with long tool chains

If any slug doesn't resolve, pick the nearest current sibling, log it in
the Decisions table as D6+ ("slug X drifted → Y on 2026-06-24"), and
patch the role × model map above.

---

## Phase progress

Following the 5-phase rollout adapted from fleet guide §10.

### Phase 0 — OpenRouter scaffolding   (op handles)
- [x] ~~Credits + auto-top-up enabled~~ — *done 2026-06-24*
- [x] ~~Two workspaces created (opencode + Pi), one key per workspace~~
      — *done 2026-06-24 (per D1)*
- [x] ~~Local prompt/response logs enabled on both workspaces~~
      — *done 2026-06-24 (per D7)*
- [x] ~~Langfuse trace export configured on both workspaces~~
      — *done 2026-06-24 (per D8)*
- [x] ~~Account-default: model-training OFF~~ — *done 2026-06-24*
- [x] ~~Slugs verified~~ — *confirmed via allowlist add 2026-06-24*
- [x] ~~Workspace allowlist applied to each workspace (5 slugs above)~~
      — *done 2026-06-24*
- [x] ~~Workspace spend limit set on each~~ — *done 2026-06-24*
- [x] ~~Keys wired into harness auth files~~ — *done 2026-06-24*:
      `~/.local/share/opencode/auth.json` (opencode workspace key)
      and `~/.pi/agent/auth.json` (Pi workspace key) — both verified.
      Pi also has DGX `vllm` key for the DGX Spark provider; Pi
      `models.json` declares openrouter + vllm + ollama providers
      mirroring opencode.

### Phase 1 — one agent, one model each
**Goal:** prove the plumbing works. Pick `backend` role.
- [ ] opencode: add a single `provider.openrouter` block in
      `opencode.json` with the **opencode workspace key** (one provider,
      reused by every cloud agent)
- [ ] opencode: add `agent.backend` subagent pointing at
      `openrouter/deepseek/deepseek-v4-pro`
- [ ] Pi: add a single `openrouter` provider in `~/.pi/agent/models.json`
      + matching `auth.json` entry with the **Pi workspace key**
- [ ] Pi: author `~/.pi/agent/agents/backend.md` with
      `model: openrouter/deepseek/deepseek-v4-pro`
- [ ] Run a tiny one-shot task in each harness; confirm spend lands in
      the right workspace on OpenRouter dashboard

### Phase 2 — full roster, no orchestration yet
- [ ] opencode: 8 agent blocks in `opencode.json`, all reusing the
      single `openrouter` provider but pointing at different model slugs
- [ ] Pi: 9 agent markdown files in `~/.pi/agent/agents/`, all using the
      single `openrouter` provider with different `model:` slugs
- [ ] Invoke each agent directly (`@backend`, `@reviewer`, …), confirm
      assigned model fires (verify in OpenRouter usage by-model
      breakdown, since per-key breakdown isn't per-agent now)

### Phase 3 — orchestrator + Gate 1 in-loop reviewer
- [ ] Author orchestrator persona (opencode `agent.orchestrator` prompt
      block; Pi `~/.pi/agent/AGENTS.md` routing rules)
- [ ] Wire dispatch rule: "always route finished work through reviewer
      before reporting back"
- [ ] Run small real task end-to-end in each harness
- [ ] **First test ride logged below**

### Phase 4 — parallel + worktrees + telemetry (later)
- [ ] Worktree runner (`git-worktree-runner` or DIY hook)
- [ ] LiteLLM proxy in front of OpenRouter (capture seam for `task_id`)
- [ ] Langfuse hookup (LiteLLM ships there natively)

### Phase 5 — harden + graduate to published docs
- [ ] Test-on-edit hooks
- [ ] CI catches collisions
- [ ] Promote this folder → `docs/agentic-coding/` with at least one
      real-task example per page
- [ ] Strike this subproject from
      [`../NEXT_STEPS.md`](../NEXT_STEPS.md)

---

## Test ride log

The thing this whole subproject exists to produce. Each entry: what we
asked, what the fleet did, what failed, what we learned.

### Test ride 1 — TBD (Phase 3)
- Project: TBD
- Task: TBD
- Outcome: TBD

---

## Open calls (parked, revisit as we go)

- **Oracle role in opencode** — Pi ships one; opencode doesn't. Skip for v1
  or author as `agent.oracle`? Currently skipped (D5 column above).
- **MCP wrapper for FastContext** — service-route via CLI works today (✓).
  Cleaner discoverability via thin MCP wrapper is the upgrade path; not
  prioritized.
- **Telemetry depth** — OpenRouter dashboard gives per-key attribution for
  free (Phase 1+). LiteLLM proxy + Langfuse adds per-task attribution
  (Phase 4). Punted until the simple path proves insufficient.
- **The test-ride project itself** — operator picks; affects how we shape
  the Phase 3 orchestrator persona (TS/Node greenfield per fleet guide §1?
  Something else?).
