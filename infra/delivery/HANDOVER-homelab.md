# Handover → homelab agent: the new `infra/delivery` service

A new self-contained service landed on `main` (commit `4811e0b` + follow-ups): the
**outbound delivery worker** — a multi-tenant email (Resend) + self-hosted Web Push comms
platform for the closelistening player (epic #1413 / infra slice #1412; app side = app-repo
PR #1441). It is **built, deployed, and verified end-to-end** on the Mac-mini Docker stack.
This note is so you can review + polish; nothing here is urgent-broken.

## What was added (all under `infra/delivery/`)

- **The service** — standalone Python package `delivery/` (no `podcast_scraper` dependency),
  `Dockerfile`, `docker-compose.yml` (3 services: `delivery-email` / `delivery-push` /
  `delivery-events`), `pyproject.toml`, `tenants.yaml` (tenant registry), `verify-dns.sh`,
  `README.md`, and `schema/` (the app↔infra seam contract, vendored from PR #1441 — see
  `schema/SYNC.md`). Tests under `tests/` (25, green).
- **Observability wiring** (in `infra/observability/`):
  - `hosts/homelab/config.alloy` — a `prometheus.scrape "delivery"` block (targets
    `host.docker.internal:9110/9111/9112`).
  - `backend/grafana/dashboards/Delivery/delivery.json` — the "Delivery worker" board
    (tenant filter var).
  - `backend/grafana/dashboards/Podcast Operator/overview.json` — a delivery row scoped to
    `tenant="podcast"`.
  - `backend/grafana/provisioning/alerting/rules.yaml` — a `delivery` alert group (4 rules:
    worker-down/critical, high-bounce, dead-letter, events-stalled).
- **Home page** — `infra/homelab-home/gen.sh` gained a "Delivery" section (workers-up, sent
  24h, bounce/complaint, dead-letters, pending, cursor age).

## Current deployed state (on the mini)

- 3 containers up (`docker compose -f infra/delivery/docker-compose.yml ...`), image
  `closelistening-delivery:local` (built locally on the host).
- `/metrics` on `127.0.0.1:9110-9112`; Alloy scrapes them (job=delivery) → VictoriaMetrics.
  Logs flow via the generic container source → VictoriaLogs. Verified live.
- **GlitchTip**: I created a project **`delivery` (id 13)** via the web container's Django
  shell; its DSN is in the host `.env` (`DELIVERY_SENTRY_DSN`). Container→GlitchTip verified.
- Secrets live in `infra/delivery/.env` on the host (gitignored): `RESEND_API_KEY`,
  `PODCAST_VAPID_PRIVATE_KEY`, `PODCAST_INTERNAL_OUTBOX_TOKEN`, `DELIVERY_SENTRY_DSN`.
- `tenants.yaml` `podcast.outbox_base_url` is a **placeholder** (`127.0.0.1:8092`) — the
  workers idle-poll until the app's player-API (`/internal/outbox/*`, PR #1441) is deployed
  and this is pointed at its tailnet address.

## Review / polish candidates (your call)

1. **Secrets → sops-env.** I used a plain gitignored `.env` for expediency, NOT the homelab
   `secrets.sops.env` + `bootstrap.sh` convention (glitchtip/observability pattern). Worth
   migrating so the delivery secrets are managed like the rest. `secrets.sops.env.example`
   isn't provided yet — add one matching the `.env` keys.
2. **config.alloy is a single-file bind mount** — editing it in place is fine, but replacing
   the file (scp/mv → new inode) **breaks the mount** until the alloy container restarts
   (I hit this; restart re-binds). Consider a directory mount or a documented "edit in
   place + `docker restart alloy-homelab`" note.
3. **Container hardening** — no `HEALTHCHECK`, resource limits, or log rotation yet. The
   worker touches a liveness file (`${DELIVERY_STATE_DIR}/live-<tenant>-<channel>`) each
   cycle — wire a HEALTHCHECK on its mtime; add mem/cpu limits + json-file log caps.
4. **Alert routing** — the `delivery` group uses `severity: critical|warning`. Confirm the
   critical rule (worker-down) routes to a contact point via `provisioning/alerting/
   policies.yaml` (existing policy routes `severity=critical` → GlitchTip; verify it catches
   `kind=delivery`).
5. **Image provenance** — `closelistening-delivery:local` is built on the host from the repo.
   Fine for now; pin/registry-push later if you want reproducible pulls.
6. **VAPID private key backup** — `PODCAST_VAPID_PRIVATE_KEY` is a top-tier secret; losing it
   invalidates every browser push subscription. Ensure it's backed up outside the host.
7. **Metrics publish** — ports are on `127.0.0.1` (Alloy reaches them via
   `host.docker.internal`, verified). If you ever move Alloy off the host network, revisit.

## How to operate

- Pause all sends (<5 min): `docker compose -f infra/delivery/docker-compose.yml stop`.
- Logs: `docker logs delivery-email` (JSONL events, tenant + correlation_id).
- Dashboards: Grafana → "Delivery worker" + the Podcast-Operator delivery row.
- Re-sync the seam contract when app PR #1441 changes: see `schema/SYNC.md`.
- App-side handshake needed for full function: `HANDOVER-app-side.md`.

---

## Homelab agent resolution (2026-08-05)

Worked the 7 candidates. Outcome:

- **#2 config.alloy inode caveat — DONE.** Documented in the `config.alloy` header
  (replacing the single-file bind mount → new inode breaks the mount until
  `docker restart alloy-homelab`; edit in place).
- **#3 container hardening — DONE.** All 3 services now have: a HEALTHCHECK
  (email/push = liveness-file mtime <120s, catching a hung loop that still serves
  `/metrics`; events = `/metrics` responds, since it writes no liveness file and a
  stalled cursor is already caught by `delivery-events-stalled`), `mem_limit: 256m`
  + `cpus: 0.5`, and json-file log rotation (10m×3). Deployed + verified healthy.
- **#1 secrets → sops — NOT A GAP (corrected).** The premise was wrong: NO stack
  in this homelab uses sops. observability/glitchtip/langfuse all run from a plain
  gitignored `.env` on the mini; `.sops.yaml` has a placeholder recipient and no
  `secrets.sops.env` exists anywhere. delivery's plain `.env` already MATCHES the
  live convention — migrating just delivery to sops would make it the sole outlier
  and needs a repo-wide age-key wiring decision. Verified `infra/delivery/.env` is
  gitignored + never committed (no leak). Left as-is by design.
- **#5 image provenance / #7 metrics on 127.0.0.1 — no action** (deferred / not a
  gap, as flagged).
- **#4 alert routing — NEEDS OPERATOR DECISION (not resolved).** `delivery-worker-down`
  (severity=critical) routes via `policies.yaml` to the `glitchtip` contact point,
  which is STILL the placeholder `https://glitchtip.example.com/PLACEHOLDER-SET-IN-ENV`
  (falls through to `default` = `alerts@homelab.local`, also non-deliverable). So a
  real worker outage is currently SILENT. This is the operator's reserved
  routing/fleet-integration design surface — left untouched, flagged for decision.
- **#6 VAPID key backup — NEEDS OPERATOR ACTION.** `PODCAST_VAPID_PRIVATE_KEY` lives
  only in the host `.env`; losing it invalidates every push subscription. Backup
  destination (e.g. the operator's password manager, alongside the age key) is the
  operator's call — flagged, not done.
