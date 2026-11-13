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
up -d` (recreates litellm only). A change to `config.yaml` ALONE is not a compose
change, so `up -d` leaves the running container on the old config: use
`docker compose restart litellm`, then confirm with `GET /model/info`
(2026-10-13: `up -d` reported nothing to do and the new alias was absent until the restart).
A restart is a cold start of about 2 minutes (2026-11-03: 17:31:15 → 17:33:12Z before `/health/liveliness` answered), and calls in that window fail: restart at a quiet moment.

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

Minted with the master key; consumers NEVER get the master key. The keys live in
LiteLLM's **postgres** (`LiteLLM_VerificationToken` table), so a DB reset /
stack-recreate **wipes them** — after which the fleet 401-floods (see recreate
note). Current consumers:

| key_alias | models | max_budget (lifetime) | consumer |
|---|---|---|---|
| `fleet-triage` | `fleet-triage-flash`, `fleet-triage-pro` | $50 | signal-fleet triager (`OPENROUTER_API_KEY` in `~/signal-fleet/fleet-gateway.env`) |
| `fleet-bugfix` | `fleet-bugfix-flash`, `fleet-bugfix-pro`, `fleet-bugfix-reviewer` | $100 | bugfix-fleet — routes via the gateway (`LLM_BASE_URL=http://localhost:4001/v1` + `LLM_API_KEY=LITELLM_FLEET_BUGFIX_KEY`), was OpenRouter-direct |
| `hub-briefing` | `assistant`, `assistant-cloud` | $2 | the hub's morning briefing (`infra/homelab-home/briefing-job.js`), key in `~/hub-briefing-litellm.env` (mode 600); minted 2026-11-03. `assistant-cloud` bills its own OpenRouter key, `assistant-cloud` in the misc-experiments workspace ($10 a month, `OPENROUTER_API_KEY_ASSISTANT` in `.env`), because the bugfix-fleet workspace's guardrail behind `OPENROUTER_API_KEY` excludes every provider of `qwen/qwen3-30b-a3b-instruct-2507` (404 "provider not allowed by guardrail") |
| `grafana-llm` | `assistant` | $2 | Grafana's LLM app (titles, descriptions, change summaries on 11.6), key in `~/grafana-llm-litellm.env` and Grafana's `.env` as `GRAFANA_LLM_LITELLM_KEY`; Grafana calls `litellm:4000` on `litellm_default`; minted 2026-11-04 |
| `eval-fleet-triage` | `eval-fleet-triage-pro` | $5 | the fleet session's eval-harness triage arms (signal-fleet changes replayed over `orrery_triage_v1_labelled`), key in `~/eval-fleet-triage-litellm.env` on the mini and on the X3 (mode 600); minted 2026-11-04 |
| `assistant-ui-eval` | `assistant` | $3 | the two chat UIs under evaluation on the X3 (`infra/x3/assistant-ui-eval/`), key in `~/assistant-ui-eval-litellm.env` on the mini and the stack's `.env` on the X3 (mode 600); minted 2026-11-03, `assistant` only since 2026-11-03 (the failover still works: a fallback model need not be on the key), expires 2027-11-03; revoke when the UI decision is made |
| `proj-podcast-dev` | `NVFP4/Qwen3-30B-A3B-Instruct-2507-FP4` (the DGX alias, named as the real model id) | $1 (the alias is $0; the cap only stops a mispriced alias) | podcast_scraper dev on the DGX profiles (`dev_dgx_full`): laptop → this gateway → the DGX vLLM, so dev calls reach Langfuse like prod's (podcast_scraper#2342). Restricted to the DGX alias, so a dev run can never reach a paid model. Minted 2026-10-13, but its value was never stored, so it was deleted unused (spend 0) and re-minted 2026-10-17 with the same settings and logging. **The value lives in `~/podcast-litellm-dev.env` on the mini** (`LITELLM_API_KEY`, `LITELLM_API_BASE`, mode 600); copy it into a checkout's gitignored `.env`. Store a key's value the moment you mint it: LiteLLM shows it only once |
| `proj-podcast-dev` logging | — | — | The key carries `metadata.logging` (Langfuse `callback_vars`) so its calls are traced in the **`podcast-dev`** project, not `agents` (per-key logging is not Enterprise-gated in LiteLLM 1.96; verified 2026-10-13). Keyless pass-throughs (`/tokenize`, `/v1/translate/...`) go to this gateway's default project, `agents`. |
| `eval-harness` | the `eval-*` aliases (40 models on the key on 2026-10-30; `/key/info` lists them) | $100 / 30d | [chipi/eval-harness](https://github.com/chipi/eval-harness) — golden references + model sweeps (`LITELLM_BASE_URL` + `LITELLM_API_KEY` in its `.env`). The key name stays `eval-harness`; only the consumer moved. |
| `robotics-brain` | `robot-vlm`, `robot-planner` (both `openrouter/qwen/qwen3-vl-30b-a3b-instruct`) and `robot-vlm-gemma` (`openrouter/google/gemma-4-26b-a4b-it`, the second model to compare; "A red square." in 0.93 s), all on the eval OpenRouter key: open weights, so phase 2 can serve them from the DGX | $10 / 30d | chipi/robotics-lab's robot brain (phase 1, operator's go 2026-11-13). Key in `~/robotics-brain-litellm.env` on the mini and on the X3 (mode 600). Proven: 200 on `robot-vlm`, 403 on `fleet-triage-flash`, and an image answered ("Red square.") through both aliases in 0.72 s and 2.08 s (one call each) |

Both route to `openrouter/deepseek-v4-pro` via `OPENROUTER_API_KEY` (the shared
key) — so their spend shows on the hub's **"Lab (shared key)"** OpenRouter vertical
(and per-key via `/key/info`). `max_budget` is a hard lifetime cap (raise
deliberately = auditable top-up).

The `eval-harness` cap was raised $20 -> $35 on 2026-09-26, and $60 -> $100 on 2026-10-30 for the
triage-model arms (operator's go): a 24-arm sweep over 200
articles stopped mid-flight at 12 arms on `budget_exceeded`. Two things to know if it
happens again — the harness's own `EVAL_MAX_COST_USD` is a PER-RUN cap and knows
nothing about this one, and the enforced figure came back as exactly 2x what
`/key/info` reported as spend, so raising by the apparent headroom under-shoots.

`eval-harness` routes on its **own** OpenRouter key, `OPENROUTER_API_KEY_EVALS` (the
operator's experiments workspace), since 2026-10-30. Until then it rode the podcast key,
on the grounds that its aliases measured podcast work; the triage-model arms measure the
fleet and outside models, so that no longer held. Every `eval-*` alias uses it: the ones in
`config.yaml` through `os.environ/`, the ones added at runtime with the key stored
(encrypted) in the DB. Keep the virtual-key cap below the OpenRouter key's own limit, so
the proxy refuses first, with an error naming the key, instead of OpenRouter returning a
402 that says nothing about which workload spent it. That workspace enforces zero data
retention: a model with no ZDR endpoint (Fable 5.1 on 2026-10-30) returns 404
"ZDR violation (guardrail)" until its guardrail is changed.

It is also the only key with a rolling `budget_duration` rather than a lifetime
cap. A sweep is repeated work, not a one-off allowance; a lifetime cap on it
just means someone raises the number every few months without reading it.

```sh
curl -s http://localhost:4001/key/generate \
  -H "Authorization: Bearer $LITELLM_MASTER_KEY" -H 'Content-Type: application/json' \
  -d '{"key_alias":"fleet-triage","max_budget":50,"models":["fleet-triage-flash","fleet-triage-pro"]}'
```

**Recreate after a DB wipe (recreation casualty).** Pass the *exact existing key
value* from `fleet-gateway.env` via the `key` field, so no consumer config changes:
```sh
curl -s http://localhost:4001/key/generate -H "Authorization: Bearer $LITELLM_MASTER_KEY" \
  -H 'Content-Type: application/json' \
  -d '{"key":"'"$OPENROUTER_API_KEY"'","key_alias":"fleet-triage","max_budget":50,"models":["fleet-triage-flash","fleet-triage-pro"]}'
```
Incident 2026-08-18: the colima/DB recreate wiped both keys → every triager call
`401`'d → the fleet failed **open** and filed ~90 escalations onto
`chipi/podcast_scraper`. Detect with `/key/info` called with the virtual key as the bearer (`401` = wiped; never
`?key=…`, the access log ships the URL to VictoriaLogs); a triage
call 401s with a body naming `LiteLLM_VerificationTokenTable`.

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
