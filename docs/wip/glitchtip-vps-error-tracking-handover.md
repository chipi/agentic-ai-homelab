# Handover — integrate the podcast app with GlitchTip (error tracking, from code)

**For:** the VPS/podcast agent. **Goal:** the podcast app reports exceptions to
the self-hosted GlitchTip, split **dev** (Mac) vs **prod** (VPS). GlitchTip is
Sentry-SDK/DSN compatible — you use the normal `sentry-sdk`, just point it here.

> **`obs`** is the Tailscale name of the observability host (custom DNS record →
> the DGX now, the Mac mini later). See [`../recipes/observability-endpoints.md`](../recipes/observability-endpoints.md).
> Until the `obs` record exists, substitute the host IP `100.69.49.126`.

## Status (2026-07-20) — everything is ready

- **GlitchTip live:** `http://obs:8090` (tailnet-only).
- **Org/team/project created:** org `homelab` → team `podcast` → project
  `podcast` (id 1). Admin (`admin@homelab.local`) is Owner.
- **DSN (verified — a test event ingested 200):**
  ```
  http://4c40d7bc-0987-427e-84dc-b4b3fcad9a62@obs:8090/1
  ```
  This is an **ingest (send-only) key**, and the endpoint is **tailnet-only**, so
  it's not exploitable off the tailnet — safe to keep in repo config. Still,
  read it from an env var (`GLITCHTIP_DSN`) rather than hardcoding.
- **ACL:** port `8090` is granted. Preflight from the app host:
  `curl -m5 -o /dev/null -w "%{http_code}\n" http://obs:8090/_health/` → `200`.

## Install

```sh
pip install "sentry-sdk"        # GlitchTip speaks the Sentry protocol
```

## Minimal init (do this once, at process startup, before app code runs)

```python
import os, sentry_sdk

sentry_sdk.init(
    dsn=os.environ["GLITCHTIP_DSN"],
    environment=os.environ.get("APP_ENV", "dev"),   # VPS sets APP_ENV=prod
    release=os.environ.get("APP_RELEASE"),           # optional: git sha / version
    traces_sample_rate=0.0,        # errors only (perf tracing → VictoriaTraces, not here)
    send_default_pii=False,        # don't auto-attach request bodies / user IPs
    max_breadcrumbs=50,
)
```

Env per host:
- **VPS (prod):** `APP_ENV=prod`, `GLITCHTIP_DSN=…` in the app's env/secrets.
- **Mac (dev):** `APP_ENV=dev`, same DSN.

Once `init()` runs, **unhandled exceptions are captured automatically** — you
don't need try/except everywhere.

## Framework wiring (auto-integrations)

`sentry-sdk` auto-detects common libs; be explicit for the app's stack:

```python
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.starlette import StarletteIntegration
from sentry_sdk.integrations.celery import CeleryIntegration      # if pipeline uses Celery
from sentry_sdk.integrations.logging import LoggingIntegration
import logging

sentry_sdk.init(
    dsn=os.environ["GLITCHTIP_DSN"],
    environment=os.environ.get("APP_ENV", "dev"),
    integrations=[
        FastApiIntegration(), StarletteIntegration(),
        CeleryIntegration(),
        LoggingIntegration(level=logging.INFO, event_level=logging.ERROR),  # logging.error() → GlitchTip
    ],
)
```

- **FastAPI/Starlette (api, viewer):** unhandled 500s become issues with the
  request context.
- **Celery / pipeline workers:** task failures become issues. For the ephemeral
  `pipeline`/`pipeline-llm` `docker compose run` containers, just call `init()`
  at the top of the entrypoint — crashes are captured before the container exits
  (add `sentry_sdk.flush()` before a hard exit to be safe).
- **CLI / plain scripts:** `init()` at top; wrap the main in
  `try/except: sentry_sdk.capture_exception(); raise`.

## Manual capture + context

```python
# explicit capture
try:
    risky()
except Exception:
    sentry_sdk.capture_exception()      # or capture_message("...", level="error")

# enrich (shows as filters/facets in GlitchTip)
sentry_sdk.set_tag("pipeline_stage", "transcribe")
sentry_sdk.set_context("episode", {"id": ep_id, "feed": feed})
with sentry_sdk.new_scope() as scope:   # scoped, doesn't leak to other events
    scope.set_tag("job_id", job_id)
    do_work()
```

## Redaction — important (GlitchTip stores what you send)

Errors can carry secrets/PII in locals, args, or messages. Scrub before send:

```python
def before_send(event, hint):
    # drop obviously sensitive keys from extra/contexts if present
    for section in ("extra", "contexts"):
        data = event.get(section) or {}
        for k in list(data):
            if any(s in k.lower() for s in ("token", "secret", "password", "api_key", "authorization")):
                data[k] = "[redacted]"
    return event

sentry_sdk.init(..., before_send=before_send)
```

(`send_default_pii=False` already keeps request bodies / IPs out.)

## Verify

```python
sentry_sdk.capture_message("glitchtip wiring test from VPS", level="error")
# or force one:  1 / 0
```
Then GlitchTip → `http://obs:8090` → project `podcast` → filter
`environment:prod` (or `:dev`) → the event appears within seconds. (There's
already one test `dev` event from setup.)

## Where GlitchTip fits (don't cross the streams)

| Signal | Goes to | How |
|---|---|---|
| **errors/exceptions** | **GlitchTip** | **this doc — `sentry-sdk`** |
| request/distributed traces | VictoriaTraces | OTEL SDK (`podcast-otel-traces-handover.md`) |
| LLM prompt/cost | Langfuse | capture layer (RFC-0001, later) |
| host/container metrics + logs | VictoriaMetrics/Logs | Alloy collector (`hosts/prod-podcast/`) |

## Gotchas

- Endpoint is `http://` (not https) and **tailnet-only** — reach `obs`,
  never a public URL. Don't expose `8090` publicly.
- Give a distinct `environment` per host (`dev`/`prod`) — it's the main filter.
- `traces_sample_rate=0.0` here on purpose: perf tracing lives in VictoriaTraces,
  not GlitchTip. Set it >0 only if you want GlitchTip's own transaction view too.
- Background/ops: `infra/glitchtip/README.md`; decision: `docs/adr/ADR-0005`.
