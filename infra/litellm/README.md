# LiteLLM — the homelab LLM gateway

One OpenAI-compatible endpoint (`http://homelab:4001/v1`) in front of every
LLM provider; **providers are config, consumers never change**. First-class
homelab service (not fleet-scoped): the agent fleets are the first
consumers, any project can be next. Design lineage: RFC-0001 (the original
LiteLLM↔Langfuse capture proposal) resurrected by ADR-0008's fired trigger
("going beyond OpenRouter"); operator decision 2026-07-25.

## The contract: aliases, not provider names

Consumers call **aliases** (`fleet-triage-flash`, `homelab-pro`, …). The
route behind an alias (OpenRouter today; direct DeepSeek / Moonshot / Z.ai /
US providers tomorrow) is swapped in `config.yaml` without touching any
consumer, eval stamp, or rate table. Adding a provider = add its key to
`.env` + point the alias's `litellm_params.model` at it + `docker compose
up -d` (recreates litellm only).

**Config drift — the file is not the whole truth.** Two ways aliases land: (a)
committed in `config.yaml` (the `homelab-*` / `fleet-*` set, reconciled to the
deployed gateway on 2026-08-05 — `num_retries` is 6), and (b) added at runtime via
the admin API (`/model/new` → stored in Postgres) which does **not** write back to
`config.yaml`. So the live gateway can serve models absent from the file. Source of
truth for what's actually routable = **`GET /model/info`**; treat `config.yaml` as
the versioned baseline, not the complete live list.

## Bring-up (mini, in-place from the repo clone)

```sh
cd ~/agentic-ai-homelab/infra/litellm
cp .env.example .env   # fill per comments; chmod 600 .env
docker compose up -d
curl -s http://localhost:4001/health/liveliness   # -> "I'm alive!"
```

## Virtual keys (per-consumer budgets — the money backstop)

Minted with the master key; consumers NEVER get the master key:

```sh
curl -s http://localhost:4001/key/generate \
  -H "Authorization: Bearer $LITELLM_MASTER_KEY" -H 'Content-Type: application/json' \
  -d '{"key_alias":"fleet-triage","max_budget":10,"models":["fleet-triage-flash","fleet-triage-pro"]}'
```

`max_budget` is a hard lifetime cap (raise deliberately = auditable top-up);
`/key/info` shows spend. One key per consumer: `fleet-triage`,
`fleet-bugfix`, future projects each their own.

## Observability (full package, day one)

- **Langfuse**: every request traced (success+failure callbacks) into the
  dedicated `litellm-gateway` project — producer-separated from the fleets'
  own projects and from the monitored apps.
- **GlitchTip**: gateway errors via `SENTRY_DSN` (failure callback +
  runtime), project `litellm` (created via the django-shell pattern, see
  the handover).
- **Metrics**: `litellm-postgres-exporter` on `127.0.0.1:9189` (scraped by
  the mini's alloy like the other stacks' exporters); LiteLLM's own
  Prometheus endpoint is enterprise-gated upstream — spend/health truth
  lives in the DB + Langfuse, and the `litellm-gateway-down` alert probes
  the DB exporter instead.
- **Logs**: container json logs, collected by the mini's existing
  alloy docker pipeline.

## Consumers today

| Consumer | Key alias | Models |
|---|---|---|
| signal-fleet triage | `fleet-triage` | `fleet-triage-flash`, `fleet-triage-pro` |
| bugfix fleet (Track B, when wired) | `fleet-bugfix` | `fleet-bugfix-pro` |

Division of labor: **OpenRouter direct stays the lab** (bake-off, model
variety); **this gateway is production routing**. Handover / deeper ops:
`docs/wip/litellm-handover.md`.
