# `infra/delivery/` — outbound communications platform

Standalone, **multi-tenant** service that delivers digest emails + push nudges for any
product on the homelab. **Homelab, tailnet-only, egress-only.** Email via the **Resend HTTP
API**; **Web Push** is fully self-hosted (VAPID + RFC 8291, no third party). It is a **pure
consumer** of the app↔infra delivery seam (podcast_scraper #1412 / ADR-145) — it shares no
code with any app, only the vendored contract under `schema/<tenant>/` (see `schema/SYNC.md`).

## Multi-tenant — one engine, many products

Podcast (player + operator, closelistening) is tenant #1; orrery / future surfaces plug in
with **no code change**. The engine is shared; everything product-specific lives in one
`tenants.yaml` entry + its `delivery/templates/<tenant>/` + `schema/<tenant>/` + its secrets:

```yaml
tenants:
  podcast:
    outbox_base_url: http://127.0.0.1:8092
    internal_token_env: PODCAST_INTERNAL_OUTBOX_TOKEN
    vapid_private_key_env: PODCAST_VAPID_PRIVATE_KEY
    mail_from: "Close Listening <digest@mail.closelistening.app>"
    app_origin: https://closelistening.app
    unsubscribe_path: /api/app/comms/unsubscribe
```

One Resend account verifies every tenant's sending domain (shared `RESEND_API_KEY`), so
email needs only a per-tenant `mail_from`. Push needs a per-tenant VAPID key. **Onboard a
tenant:** add an entry + its templates/schema + its two secrets. That's it.

Each channel service runs **one worker per tenant** (registry-driven); the events poller is
a **single cross-tenant** loop (one Resend account) that routes each bounce back to the
right tenant's outbox via the tenant-tagged sent-index. Every metric, log, error, and trace
carries **`tenant`** + a **`correlation_id`** (= the envelope id, which also rides to Resend
as an `X-Correlation-Id` header) for end-to-end tracing.

## Topology

```
app outbox (tailnet) ──poll──▶ delivery-email ──HTTPS──▶ Resend ──▶ inbox
                     ◀─status──
                                delivery-events ◀─poll─ Resend events (bounce/complaint → suppress)
app outbox (tailnet) ──poll──▶ delivery-push  ──HTTPS──▶ browser push endpoint
```

Rendering (payload → HTML / push) is done here, extractive Jinja, **no LLM** (D6). The app
never emits HTML. Digest items carry the graph (`graph_refs`) — never a flat clip.

## Run (docker compose, like the other homelab services)

```bash
cp .env.example .env         # then fill in the secrets (plain gitignored .env — see below)
docker compose build
docker compose up -d
docker compose logs -f       # JSONL events; watch the first drains
```

Three services: `delivery-email`, `delivery-push`, `delivery-events`. No published ports
except loopback `/metrics` (9110/9111/9112) for the Alloy scrape.

**Container hardening** (each of the three services):
- **HEALTHCHECK** — `email`/`push` probe the worker's per-cycle liveness file
  (`/var/lib/delivery/live-<tenant>-<channel>`, mtime <120s = 4 poll cycles): this catches a
  **hung loop** that still serves `/metrics`, which `up{job="delivery"}` cannot see. `events`
  (a single cross-tenant poller that writes no liveness file) probes `/metrics`; a stalled
  cursor there is caught by the `delivery-events-stalled` alert on cursor age.
- **Resource limits** — `mem_limit: 256m`, `cpus: 0.5` per service (lightweight pollers).
- **Log rotation** — json-file, `max-size: 10m` × `max-file: 3`.

## Observability (fully wired)

- **Metrics:** each loop exposes Prometheus `/metrics`; the homelab Alloy scrapes them
  (`prometheus.scrape "delivery"` in `../observability/hosts/homelab/config.alloy`, job=delivery).
- **Logs:** canonical JSONL events to stdout → Alloy → VictoriaLogs (`event_type=delivery`
  / `delivery_suppression` / `delivery_deadletter`).
- **Dashboard:** `../observability/backend/grafana/dashboards/Delivery/delivery.json`
  (worker-up, sent-by-status, **bounce+complaint canary**, pending depth, dead-letters,
  cursor lag, latency).
- **Alerts:** `delivery` group in `../observability/.../alerting/rules.yaml` — worker-down
  (critical → GlitchTip), high-bounce, dead-letter, events-stalled.
- **Errors:** dead-letters → GlitchTip via `DELIVERY_SENTRY_DSN`.
- **Traces:** optional OTEL spans per drain cycle if `OTEL_EXPORTER_OTLP_ENDPOINT` is set.

## Secrets

A **plain gitignored `.env`** — the live homelab convention (observability, glitchtip and
langfuse all run the same way; repo sops is an unwired placeholder, so there is no
`secrets.sops.env`/bootstrap step here). Keys: `PODCAST_INTERNAL_OUTBOX_TOKEN` (must match
the app), `RESEND_API_KEY`, `PODCAST_VAPID_PRIVATE_KEY`, `DELIVERY_SENTRY_DSN`. Never
committed; `.env` is gitignored (verified never in history). Generate VAPID once with
`delivery-gen-vapid` and **back up the private key outside the host** (losing it invalidates
every push subscription).

## DNS preflight (email deliverability)

```bash
bash verify-dns.sh mail.closelistening.app
```
Checks the Resend return-path SPF + MX on `send.mail.…`, DKIM, DMARC. (Verified 4/4 green +
a real inbox delivery on 2026-08-05.)

## Pause all sends (<5 min)

```bash
docker compose stop    # SIGTERM → each loop finishes its batch and exits; outbox keeps the backlog
```

## Tests

```bash
python -m pip install -e ".[dev,obs]"
python -m pytest tests/     # contract (vs vendored golden fixtures) + webpush RFC vector + worker branches
```

**Deployed-service e2e** (`e2e/`, run against the live workers, not pytest): `e2e_send.py`
(real send through the multi-tenant code), `e2e_failure.py` (forces a dead-letter and
confirms the o11y chain), `stub_outbox_host.py` (a tiny host-side stub outbox for the
deployed worker to drain). These verify the running stack end-to-end after a change.

## Contract sync

The seam schema + fixtures under `schema/` are vendored from the app repo. When the app
re-PRs the delivery seam, re-sync per `schema/SYNC.md` and re-run the contract test.
