# LiteLLM gateway — handover (for any agent working on it)

**Status 2026-07-25:** first-class homelab service, stood up as the
production LLM router. Stack: `infra/litellm/` (compose: litellm-database +
postgres + postgres-exporter, port **4001**). Operator intent on record:
**this serves more than the agent fleets** — treat it as shared homelab
infrastructure, not fleet plumbing.

## The mental model

- **Aliases are the contract** (`fleet-triage-flash`, `homelab-pro`…);
  provider routes behind them are swappable config. Consumers, eval stamps,
  and rate tables never reference provider model names directly.
- **OpenRouter = the lab** (model variety, bake-offs, direct); **the
  gateway = production** (budgets, observability, provider flexibility).
- **Virtual keys are the money backstop**: per-consumer, hard `max_budget`,
  minted with the master key (mini-side `.env`, never in the repo). Raising
  a budget is a deliberate operator act.

## Operate

- Bring-up / keys / alias swaps: `infra/litellm/README.md` (all one-liners).
- Secrets: `infra/litellm/.env` on the mini only, chmod 600. Master key =
  admin; never hand it to a consumer.
- Adding a **direct provider** (the operator's stated direction — DeepSeek,
  Moonshot/Kimi, Z.ai/GLM, cheap US): add `<PROVIDER>_API_KEY` to `.env`,
  point the alias's `litellm_params.model` at `deepseek/...` (native
  provider prefix) instead of `openrouter/...`, `docker compose up -d`.
  Verify with one completion against the alias + check the Langfuse trace
  shows the new underlying model. Swap back = revert the alias.

## Observability wiring (as built)

- **Langfuse** project `litellm-gateway` (producer-separated). Keys in
  `.env` (`LANGFUSE_PUBLIC_KEY/SECRET_KEY`, host `homelab:4000`).
- **GlitchTip** project `litellm` — DSN minted with the django-shell
  pattern (see `~/gt_create.py` on the mini for the canonical example;
  adapt org/project names). `SENTRY_DSN` in `.env`.
- **Alert**: `litellm-gateway-down` in
  `infra/observability/backend/grafana/provisioning/alerting/rules.yaml`
  (probes the stack's postgres-exporter `up`).
- LiteLLM's own Prometheus metrics endpoint is enterprise-gated upstream;
  spend truth = `/key/info` + the postgres DB + Langfuse. Do not burn time
  enabling it on OSS.

## Known limits / next steps

- [ ] First direct-provider route (DeepSeek) — config-only, do it when the
      operator wants the flip; A/B via the alias.
- [ ] Consumer migration status: signal-fleet triage → gateway (done at
      stand-up, virtual key `fleet-triage`); bugfix fleet → pending Track B
      wiring (`fleet-bugfix` key pre-minted).
- [ ] Image tags are `main-stable` — PIN after the first week of stable
      operation (repo convention).
- [ ] If gateway request volume ever makes per-request Langfuse tracing
      noisy/costly, sample — decision belongs to the operator.

## Rules that bind here

Secrets never in the repo · compose runs in place from the mini's repo
clone (`~/agentic-ai-homelab`) · shared-state changes (compose down/up,
budget raises) are per-instance operator approvals · producer separation:
the gateway's own telemetry stays in its own Langfuse/GlitchTip projects.
