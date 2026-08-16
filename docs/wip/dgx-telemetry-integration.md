# DGX service telemetry → homelab stack (integration state)

**Goal (operator, 2026-08-16):** every DGX app service sends **logs → Grafana**
(VictoriaLogs) and **errors → homelab GlitchTip** (one project per service),
labelled `production`; **hosted sentry.io removed**. For third-party apps with no
native Sentry, **option B**: logs→VictoriaLogs is the error path (do NOT SDK-patch
someone else's server).

Most of this work is **remote-host state** (DGX `/home/markodragoljevic/.env` +
mini GlitchTip DB rows), not in-repo — so this doc is the reproducible record.

## Per-service state (validated end-to-end)

| Service | Type | Errors | Logs→VLogs | Validation |
|---|---|---|---|---|
| **moss** (:8004, transcribe) | our app (sentry_sdk) | GlitchTip **proj 14** | ✅ | `POST /v1/transcribe` garbage → 500 → real `RuntimeError` landed in proj 14 |
| **pyannote** (:8001, diarize) | our app (sentry_sdk) | GlitchTip **proj 15** | ✅ | `POST /v1/diarize` garbage → 500 → real `RuntimeError` landed in proj 15 |
| **faster-whisper** (:8000, speaches) | third-party FastAPI | logs-only (B) | ✅ | poked → access logs landed in VLogs |
| **librechat-api** (:3080) | third-party Node | logs-only (B) | ✅ | restart → 20 startup lines landed in VLogs |
| **vllm-autoresearch** (:8003) | third-party FastAPI | logs-only (B) | idled | validate logs when `gpu-mode-swap.sh research` runs |

## GlitchTip project registry (homelab, org `homelab`)
Created on the mini GlitchTip (glitchtip.tail6d0ed4.ts.net):
- **14** `moss` — key `a57b1085…` — DGX moss
- **15** `pyannote` — key `ef1fe398…` — DGX pyannote
- (restored earlier, same session) **1** gi-kg-viewer/orrery `d8aa7c66…`, **5** player `5edf9f1c…`, **13** delivery `503ef68e…`
- Umami sites: player `cd384a3e…`, operator-viewer `a5a60c25…`, orrery `fb07dfd6…`

## How the DSNs are wired (DGX)
The DGX podcast services (moss/pyannote/faster-whisper) share
`/home/markodragoljevic/.env` (hand-maintained central config, NOT converge-
generated → edits persist). Each service's code reads a **different** var, so the
shared file holds per-service DSNs without collision:
- `GLITCHTIP_DSN=…/14`  ← **moss** reads this (`GLITCHTIP_DSN or SENTRY_DSN`)
- `SENTRY_DSN=…/15`     ← **pyannote** reads this (SENTRY_DSN only)

⚠ **Gotcha:** because the `.env` is shared, do NOT blank a var for one service —
it affects the others on their next restart. (I did this once: blanked
`SENTRY_DSN` for moss, which would have killed pyannote's reporting — fixed by
pointing `SENTRY_DSN` at pyannote's own project 15.) A **3rd** service reading
`GLITCHTIP_DSN` or `SENTRY_DSN` would collide — it needs its own var, or move to
per-service `environment:` blocks in converge `deploy.py`.

## Port collision fixed (root cause of a ~3-day silent outage)
moss (:8004) had been crash-looping for ~3 days: the autoresearch **vLLM engine
grabbed 8004** (its API is 8003, ACL-required; engine takes 8003+1=8004 = moss).
Pre-existing (vLLM up 2d20h), surfaced by a moss recreate. **Resolved** by
`gpu-mode-swap.sh free` (idles vLLM, frees 8004) per operator — moss now healthy,
`RestartCount=0`.

## Done in the 2026-08-16 fix pass (all validated)
- **Durable vLLM port fix (task #7): SHIPPED + validated.** API hardcoded to 8003,
  `VLLM_PORT=8090` → engine binds **8091** (not 8004). Started research live:
  `:8003/health → 200`, EngineCore on `:8090`, **moss kept :8004, RestartCount=0** —
  they coexist. Then re-idled (`free`). Fix in `infra/vllm/autoresearch/`
  docker-compose.yml + .env.example, and on the DGX `.env` (`VLLM_PORT=8090`).
- **vllm logs: validated** — 20 `vllm-autoresearch` lines in VictoriaLogs while up.
- **env label `production`: done + validated.** Set in all 4 sources (shared `.env`
  `SENTRY_ENVIRONMENT`, moss compose override, DGX alloy `HOMELAB_ENV`, converge
  `deploy.py`). GlitchTip events for proj 14+15 now tagged `production`; VLogs DGX
  logs carry `env=production, cluster=dgx`.
- **Backup guardrail (task #6): done + tested.** `infra/backup/dump-observability-dbs.sh`
  + `com.homelab.db-backup.plist` (nightly 04:30) installed on the mini; test dump of
  all 4 config DBs succeeded (glitchtip/umami/langfuse/litellm).

## Still open
- **converge durability caveat:** the `SENTRY_ENVIRONMENT=production` edit to
  `deploy.py` was made in the DGX runner checkout — the **podcast_scraper GitHub repo**
  needs the same commit or a CI re-checkout reverts it (moss's compose is
  converge-generated). Coordinate with the podcast/orrery agent.
- **Repo divergence:** the DGX `/home/ops/agentic-ai-homelab` checkout has
  `infra/librechat` + `infra/vllm/autoresearch` that differ from origin — reconcile
  before relying on in-repo copies for those two. (The vLLM compose fix here was made
  to BOTH the DGX copy and this repo; librechat still needs reconciling.)
- **GlitchTip cosmetic:** stale `prod`/`dgx-prod` environment rows remain (FK-guarded
  delete didn't take) — harmless, no new events use them.

## Rollback
- Per-service DSN: `/home/markodragoljevic/.env.bak-*` on the DGX (backed up before
  each edit) → restore + `docker compose up -d --force-recreate <svc>`.
- vLLM: `gpu-mode-swap.sh research` brings it back (will re-collide with moss until
  the durable fix lands — see task #7).
