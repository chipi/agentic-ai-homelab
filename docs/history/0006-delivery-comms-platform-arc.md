# 0006 — delivery comms-platform arc (multi-tenant email + Web Push)

**Date:** 2026-08-05
**Operator:** Marko (chipi)
**Agent:** Claude Opus 4.8, via Claude Code (remote-control)
**Outcome:** A new self-contained homelab service — `infra/delivery/` — shipped
to `main`: a **multi-tenant outbound communications platform** (email via Resend
+ fully self-hosted Web Push) that drains the closelistening player's digest
outbox, renders, delivers, and reports status back. Deployed on the Mac-mini
Docker stack and verified end-to-end: real Gmail inbox delivery, metrics in
VictoriaMetrics, logs in VictoriaLogs, bounce→suppression, dead-letter→GlitchTip.
Full o11y wired (dashboard, 4 alerts, home-page section). Two handovers left in
the repo for the app-side (#1441) and homelab agents.

> Sibling to [`0005-bakeoff-matrix-arc.md`](0005-bakeoff-matrix-arc.md).
> Cold-start reading order: `infra/delivery/README.md` → `HANDOVER-homelab.md`
> (what's deployed + polish list) → `HANDOVER-app-side.md` (the app handshake) →
> this doc's Open threads.

## What the operator pointed at

Delegated infra slice of the app epic #1413 (podcast_scraper): stand up the
outbound delivery infrastructure so the player's personal digest + push nudges
can be *sent*, while the app team builds the payload/consent/outbox half in
parallel (app PR #1441 `feat/delivery-curation-arc`). Mid-arc the operator
widened the goal: **make it a general comms platform** — podcast is tenant #1,
but orrery / an operator surface / future products must plug in with no code
change.

## What landed

- **`infra/delivery/`** — standalone Python service (no `podcast_scraper`
  dependency), `docker-compose.yml` (three loops: `delivery-email` /
  `delivery-push` / `delivery-events`), `tenants.yaml` registry, vendored seam
  contract under `schema/podcast/` (from app PR #1441), 25 tests.
- **Architecture:** the app outbox *is* the queue (Listmonk dropped after an
  advisor review — see D-0013); a thin stateless worker drains it → Jinja render
  (extractive, D6, Gmail-safe HTML, week-specific title) → Resend HTTP API
  (email) + self-hosted Web Push (VAPID + RFC 8291 aes128gcm, no `pywebpush`) →
  status write-back. Idempotent on envelope id; retry/backoff/dead-letter.
- **Multi-tenant:** registry-driven, one worker per (tenant, channel); shared
  Resend account, per-tenant identity/templates/VAPID; a single cross-tenant
  events poller routes each bounce to the right tenant's outbox.
- **Observability:** Alloy scrape (`config.alloy`), JSONL logs → VictoriaLogs,
  GlitchTip project `delivery` (id 13), OTEL-ready; a Grafana "Delivery worker"
  dashboard, a Podcast-Operator delivery row (`tenant="podcast"`), 4 alert rules,
  and a home-page section. Everything tagged `tenant` + `correlation_id`.
- **DNS/deliverability:** `mail.closelistening.app` verified 4/4 (SPF/DKIM/DMARC),
  Resend domain Verified; real inbox delivery confirmed.

## Decisions

- **D-0013** (see `0002-decisions.md`) — delivery worker lives in the homelab
  repo as a pure consumer of the app-owned seam; Listmonk dropped for a thin
  stateless worker → Resend; Resend bounces read per-message via `GET /emails/{id}`
  (no pollable `/events` list).

## Bugs found + fixed by deploying for real (not on the Mac)

1. **Empty email body** — the dark theme was on `<body>`, which Gmail strips →
   light text on white = invisible. Fixed: dark bg on a `bgcolor` wrapper table.
2. **Resend `/events` is always empty** — events are webhook-only; the poller was
   reworked to poll `GET /emails/{id}` per sent message (tailnet-friendly, no
   inbound webhook).
3. **Internal-outbox auth mismatch** — app gates on `X-Internal-Token` (seam v1.1
   amendment 6), not `Authorization: Bearer`; worker aligned.
4. **`tenants.yaml` not found in the image** — needs `DELIVERY_TENANTS_FILE=/app/tenants.yaml`.

## Open threads (resume here)

- **Wire the real outbox** — `tenants.yaml` `podcast.outbox_base_url` is a
  placeholder (`127.0.0.1:8092`); point it at the deployed player-API tailnet
  address (once app PR #1441 deploys) + redeploy → the workers drain real traffic.
- **App handshake** (`HANDOVER-app-side.md`) — the app must serve the worker's
  VAPID **public** key (`BIvs576y…`), share `INTERNAL_OUTBOX_TOKEN`, keep the GET
  `/comms/unsubscribe` route (app agent already added it).
- **Homelab polish** (`HANDOVER-homelab.md`) — GlitchTip finish + a few bits are
  being handled by the homelab agent (container hardening, secrets convention,
  alert routing confirm). README/rules/hardening edits already in progress.
- **Rotate the Resend API key** — it surfaced in-session; roll it + update the
  host `.env`.
- **Contract re-sync** — when app PR #1441 merges, re-sync `schema/podcast/` per
  `schema/SYNC.md` and re-run the contract test.
