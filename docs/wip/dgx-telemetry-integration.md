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

## NOT done / pending (equal weight)
- **Durable vLLM port fix** (task #7): idling fixed it *now*, but `gpu-mode-swap.sh
  research` will re-collide. Fix = pin vLLM engine port off 8004 (`VLLM_PORT` in
  `infra/vllm/autoresearch/docker-compose.yml`, keep `--port=8003`). **Staged, not
  shipped** — needs a live vLLM start to validate it doesn't break startup; box is
  idled, so deferred to next research swap.
- **env label `production`** (task, batch): today moss=`prod`, pyannote=`dgx-prod`,
  log label `env=prod`. Standardize both (alloy `HOMELAB_ENV` + converge
  `SENTRY_ENVIRONMENT`) — cross-repo (podcast_scraper converge). Not yet done.
- **Backup guardrail** (task #6): nightly `pg_dump` of GlitchTip/Umami/Langfuse so a
  future volume reprovision is a restore, not permanent loss (the failure that
  started this whole thread). Not yet built.
- **vllm logs** not live-validated (idled).
- **Repo divergence:** the DGX `/home/ops/agentic-ai-homelab` checkout has
  `infra/librechat` + `infra/vllm/autoresearch` that differ from origin — reconcile
  before relying on in-repo copies for those two.

## Rollback
- Per-service DSN: `/home/markodragoljevic/.env.bak-*` on the DGX (backed up before
  each edit) → restore + `docker compose up -d --force-recreate <svc>`.
- vLLM: `gpu-mode-swap.sh research` brings it back (will re-collide with moss until
  the durable fix lands — see task #7).
