# Handover — wire the podcast app to GlitchTip (error tracking)

**For:** the VPS/podcast agent. **Goal:** the podcast app reports exceptions to
the self-hosted GlitchTip, tagged **prod** on the VPS and **dev** on the Mac.

GlitchTip is Sentry-SDK/DSN compatible — you use a normal Sentry SDK, just point
its DSN at our instance and set `environment`.

## Status (2026-07-20)

- **GlitchTip is LIVE** on the DGX: `http://100.69.49.126:8090`
  (`infra/glitchtip/`, tailnet-only). Admin user exists (operator has creds).
- **ACL:** port **`8090`** must be granted to `tag:dgx-llm-host` in the Tailscale
  admin console (per-port allowlist, like `3000`/`8428`/`9428`). Verify first:
  `curl -m5 -o /dev/null -w "%{http_code}\n" http://100.69.49.126:8090/_health/`
  (expect `200`; a timeout = grant missing → tell the operator).

## Get the DSN (operator / one-time)

The DSN comes from a GlitchTip **project**. Operator (or you, if you have login):
1. Open `http://100.69.49.126:8090`, log in.
2. Create an **Organization** (e.g. `homelab`) → **Project** (e.g. `podcast`,
   platform = Python).
3. Copy the project **DSN** — looks like
   `http://<public_key>@100.69.49.126:8090/<project_id>`.

The DSN host MUST be the tailnet IP:port the app can reach. The DSN is an ingest
key (semi-public) — store it in the podcast app's config/secrets, not hardcoded
in a public place.

## Integrate (Sentry SDK)

Same DSN in both places; the **`environment`** tag is what separates them.
Derive it from an env var so the same code does the right thing per host:

```python
import os, sentry_sdk

sentry_sdk.init(
    dsn=os.environ["GLITCHTIP_DSN"],
    environment=os.environ.get("APP_ENV", "dev"),   # VPS sets APP_ENV=prod
    traces_sample_rate=0.0,     # errors only; raise later for perf tracing
    release=os.environ.get("APP_RELEASE"),          # optional: git sha
)
```

Per host:
- **VPS (prod):** `APP_ENV=prod`, `GLITCHTIP_DSN=…` in the app's env/secrets.
- **Mac (dev):** `APP_ENV=dev`, same DSN.

One project receives both; filter by `environment` in the GlitchTip UI.

## Verify

Trigger a test error and confirm it lands under the right environment:

```python
sentry_sdk.capture_message("glitchtip wiring test from VPS", level="error")
# or:  1 / 0
```

Then in GlitchTip → the `podcast` project → filter `environment:prod` → the
event should appear within seconds.

## Notes / gotchas

- Reach GlitchTip at the **tailnet IP** `100.69.49.126:8090`, never loopback,
  never a public URL. Don't expose `8090` publicly.
- If ingest 400s on host validation, the GlitchTip `ALLOWED_HOSTS` is wildcard
  by default (accepts the tailnet IP) — should be fine; tell the operator if not.
- This is separate from metrics/logs (that's the Alloy collector →
  VictoriaMetrics/VictoriaLogs, see `observability-vps-collector-handover.md`).
- Background + ops: `infra/glitchtip/README.md`; decision: `docs/adr/ADR-0005…`.
