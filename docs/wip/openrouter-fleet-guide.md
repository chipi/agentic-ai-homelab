# OpenRouter for the Fleet — Reference Guide

A standalone reference for running OpenRouter as the single cloud gateway for a multi-agent
fleet (Pi / OpenCode / Claude Code), with per-role open models. The per-role *model map* lives
in the fleet guide (§2.4); this doc is the OpenRouter platform mechanics — keys, attribution,
privacy, routing, cost.

---

## 1. Why OpenRouter here

Your design is **per-role model selection**, so the operation that must stay cheap is
*swapping a role's model*. OpenRouter gives every model — DeepSeek, Qwen, GLM, Kimi, MiniMax,
plus US models — **one key, one OpenAI-compatible endpoint, one ID format**. Assigning a model
to a role becomes a one-line string edit.

- **One bill, unified attribution** across every model (feeds telemetry, §8).
- **Automatic failover** — if a provider errors or rate-limits, OpenRouter transparently
  falls back to the next provider; direct keys just die mid-run. Real resilience for unattended
  parallel fleets.
- **Zero-onboarding experimentation** — try a different model on a role with no new signup.

### The cost reality (corrected)
OpenRouter **does not mark up per-token inference** — you pay the provider's listed price. The
fee is a **5.5% platform fee on credit purchases** (pay-as-you-go). So it's a top-up surcharge,
not a per-call tax — cheaper than the "small markup" framing suggests. (BYOK — §9 — is a
separate 5% routing fee.)

### Trade-offs to keep honest
- Prompts **transit OpenRouter** — a privacy hop (mitigated, see §4, and it's why local/
  FastContext never routes through it, §7).
- Slightly less control over per-provider params than a direct connection (recoverable via
  provider routing, §5).

---

## 2. Setup

```bash
# OpenAI-compatible: just change the base URL
BASE_URL = https://openrouter.ai/api/v1
# header: Authorization: Bearer sk-or-...
```
Create an account, buy credits (USD base; set **auto top-up** so a parallel fleet doesn't
stall mid-run when the balance dips). Free-tier caps (50 req/day, 20 RPM) don't apply once
you're on paid credits — but upstream provider rate limits still can.

---

## 3. Per-agent attribution — the fleet feature

The single most useful OpenRouter capability for a fleet: **multiple API keys, one per agent
role**, each with its own spend limit. The dashboard then breaks down tokens/cost **by key =
by agent** with zero code — this is the cheapest path to per-agent telemetry (no proxy, no
metadata passthrough needed).

- **Per-key credit limit** — cap each agent key so a runaway role can't drain the balance.
- **Provisioning API** — create/read/update/delete keys *programmatically*. Use it to mint a
  key per agent (or per agent×project) automatically rather than clicking through the UI —
  the right move when the fleet has many roles or you spin up per-project keys.
- **Guardrails** (org controls) — set spending limits, restrict which models a key may use,
  and enforce data policies per key/member. E.g. lock the cheap-tier keys to only the cheap
  models so a misconfig can't accidentally run GLM on the docs agent.

Pattern: one named key per role (`orchestrator`, `reviewer`, `backend`, …), each limited and
(optionally) model-restricted via Guardrails. Attribution falls out of the dashboard for free.

---

## 4. Privacy & data policy (the proprietary-code angle)

OpenRouter's default is **privacy-protective**, which matters for your proprietary repos:

- By default OpenRouter **will not route to providers that log or train on inputs** (or whose
  policy it can't confirm) — those are only used if you explicitly switch on the **model-
  training toggle** in privacy settings. Leave it **off**.
- You can set **`data_collection: "deny"`** in the request's provider preferences to force
  only non-logging providers.
- Guard behavior: if your request's provider routing finds **no provider matching your privacy
  level**, the request **errors out** rather than silently leaking — fail-closed, which is what
  you want for proprietary code.

This makes the "prompts transit OpenRouter" hop acceptable for most work — but it's still a
hop, so anything that must stay fully air-gapped (and FastContext recon over the whole repo)
stays on the **local** provider, never OpenRouter (§7).

---

## 5. Provider routing — controls worth knowing

A given model is often served by several upstream providers at different price/speed/quality.
OpenRouter lets you steer that per request (`provider` preferences, or model-ID variants):

- **`:nitro`** — sort providers by **throughput** (fastest). Good for latency-sensitive
  interactive roles (the orchestrator you're waiting on).
- **`:floor`** — sort by **price** (cheapest). Good for the high-volume cheap tier
  (tester/docs) where latency doesn't matter.
- **`:exacto`** — quality-first signals tuned for **tool-calling reliability**. Worth trying
  on agents that fire many tool calls (builders, recon) where a flaky provider breaks the loop.
- **`order` / `ignore` / `allow_fallbacks`** — pin a preferred provider, exclude a bad one,
  or require fallbacks on/off.
- **`require_parameters`** — only route to providers that support the params you sent (e.g.
  tool calling, structured output) — avoids silent capability mismatches.

Per-role suggestion: orchestrator `:nitro`, cheap tier `:floor`, tool-heavy builders/recon
`:exacto`. These are tunable later, not day-one essential.

---

## 6. Model slugs

Slugs are `vendor/model`, and when nested through Pi/OpenCode's own `provider/model` scheme
they become three segments: `openrouter/deepseek/deepseek-v4-pro`.

Current Chinese roster (mid-2026 — **verify every slug at `openrouter.ai/models`; they drift**):
- DeepSeek → `deepseek/deepseek-v4-pro`, `deepseek/deepseek-v4-flash`
- Qwen → `qwen/qwen3.6-plus`, `qwen/qwen3-coder`
- GLM (Z.ai) → `z-ai/glm-5.2`
- Kimi (Moonshot) → `moonshotai/kimi-k2.7-code`
- MiniMax → `minimax/minimax-m3`
- MiMo (Xiaomi) → `xiaomi/mimo-v2.5-pro`

The model→role assignments are in the fleet guide §2.4. Confirm each resolves with
`opencode models` / Pi's model list before trusting it.

---

## 7. Wiring (brief — full config in fleet guide §2)

- **Pi:** key in `~/.pi/agent/auth.json` (`openrouter`), provider block in `models.json`
  (`baseUrl: https://openrouter.ai/api/v1`, `api: openai-completions`), assign per role in
  `settings.json` `subagents.agentOverrides`.
- **OpenCode:** `opencode auth login` → OpenRouter; reference `openrouter/<vendor>/<model>` per
  agent in `opencode.json`.
- **Local never routes through OpenRouter** — Ollama/llama.cpp/FastContext are a *separate*
  local provider pointing at `localhost`. Register both; assign per role.

---

## 8. Telemetry

Two paths, depending on how much you need:

- **Light (dashboard only):** per-agent **virtual keys** (§3) → OpenRouter's own usage
  dashboard breaks down tokens/cost by key/agent. No infra. Limitation: no per-*task* grouping.
- **Full (proxy → Langfuse):** put a **LiteLLM proxy** in front of OpenRouter as the capture
  seam (one base-URL swap, harness-agnostic), carrying an **`agent`** tag and a propagated
  **`task_id`**. LiteLLM ships to your existing **Langfuse**, which groups by `task_id` (join
  key to `scores.json` → *tokens per passing task*) and rolls cost by agent. This is what
  unlocks net-total-per-task measurement for recon/compression work.

Virtual keys give attribution by *agent*; the proxy + `task_id` adds attribution by *task*.

---

## 9. BYOK (optional)

If one model's volume makes even the (zero) markup irrelevant and you want your *own* provider
key used: OpenRouter **BYOK** lets you register a direct provider key, used first with
OpenRouter endpoints as fallback. Cost: **5% of normal** (waived first 1M BYOK requests/month).
Keys can be **Prioritized** or **Fallback**, with per-model filters. Niche — only worth it if
a single role becomes a heavy hitter and you want direct-provider rates/control.

---

## 10. Day-one checklist
- [ ] Buy credits + enable **auto top-up** (parallel fleets stall on empty balance).
- [ ] **Model-training toggle OFF**; set `data_collection: "deny"` for proprietary work (§4).
- [ ] One **named key per role**, each with a spend limit (§3); consider Guardrails model-locks.
- [ ] If scaling roles/projects: script keys via the **Provisioning API**.
- [ ] **Verify slugs** at `openrouter.ai/models` (they drift) — §6.
- [ ] Decide routing variants per tier (`:nitro` / `:floor` / `:exacto`) — §5, tune later.
- [ ] Keep **local/FastContext off OpenRouter** entirely (§7).

---

## Sources
- OpenRouter FAQ (no per-token markup; 5.5% top-up fee; privacy default; routing variants): https://openrouter.ai/docs/faq
- Provider routing & dynamic variants (`:nitro`/`:floor`/`:exacto`): https://openrouter.ai/docs/faq
- Provisioning API (programmatic keys): https://openrouter.ai/docs/features/provisioning-api-keys
- Guardrails (spend limits, model restriction, data policy): https://openrouter.ai/docs/guides/features/guardrails
- BYOK (own provider keys, 5%): https://openrouter.ai/docs/guides/overview/auth/byok
- Rate limits: https://openrouter.ai/docs/api/reference/limits
