# Handover → app-side agent (PR #1441 `feat/delivery-curation-arc`)

The **infra delivery worker** (this dir, deployed on the homelab, epic #1413 slice #1412) is
built, tested against your committed seam contract, and verified end-to-end. Your PR #1441
already implements the seam correctly — endpoints, token gating, `?ref=` unsubscribe, and the
amendments (idempotent status, current-consent filter, expiry, bounce-suppression). **Nothing
in the contract needs to change.** But a few **handshake values + one endpoint** must be right
for it to work the moment #1441 lands. This is everything you need beyond your security fixes.

## 1. VAPID keypair — MUST use the worker's public key (else every push silently fails)

Your `GET /api/app/push/vapid-key` serves `app.state.vapid_public_key`, and the browser binds
its subscription to it. The worker signs with the **matching private key**. They are ONE
keypair — you must serve the public half of the worker's key, not a freshly generated one.

Set the app's `VAPID_PUBLIC_KEY` env (→ `app.state.vapid_public_key`) to exactly:

```
BIvs576yV_5WcqKUr8G8zbt5u11YJ5BCvuBkLZJeveD8cMQDdT6tspp8rbN8Cf5h1SQTdG1H1r5g5oRYgDLcyhU
```

(This is the public key only — safe to commit to config/secrets as a public value. The
private half lives solely in the worker's homelab secret store.)

## 2. `INTERNAL_OUTBOX_TOKEN` — must be byte-identical on both sides

The worker authenticates to `/internal/outbox/*` with a bearer token. The player API's
`INTERNAL_OUTBOX_TOKEN` must equal the worker's `PODCAST_INTERNAL_OUTBOX_TOKEN`. Operator holds
the value (generate one proper token, `openssl rand -hex 32`, set on both). Empty on the app
side → your endpoints 503 and nothing is delivered.

## 3. Add `GET /api/app/comms/unsubscribe?ref=` (the in-body email link is a GET click)

Today `/comms/unsubscribe` is **POST-only**. That's correct for the RFC 8058 one-click header
(the mail-client's native Unsubscribe button — the worker already sends
`List-Unsubscribe` + `List-Unsubscribe-Post`). But the **visible "Unsubscribe" link in the
email body** is an ordinary `<a href>` → a **GET** navigation, which a POST-only route rejects.

Add a `GET` handler on the same path + `ref`: verify the ref, flip the consent bit (reuse the
POST's logic — idempotent), and return a small "You've been unsubscribed" HTML page. Keep the
POST for one-click. Without this, the in-body unsubscribe link 405s.

## 4. Quick confirmations (likely already true in #1441 — please verify)

- **`expires_at`** is set by the digest assembler on each envelope (the worker suppresses
  rather than delivers a digest past it — prevents stale flush after a homelab-down window).
- **`GET /internal/outbox/pending`** filters on **current** consent, not the enqueue snapshot
  (a user who unsubscribes between enqueue and drain must not be returned).
- **`push_subscription`** is stored + emitted as the raw W3C PushSubscription
  (`{endpoint, keys:{p256dh, auth}}`) — the worker consumes it verbatim, no transform.
- **Status write-back is idempotent per `id`**, and a hard status (bounced/complaint) may
  arrive AFTER `delivered` and must supersede it (async bounce; the worker relies on this).

## 5. When the player API deploys with #1441

Give the operator the API's **tailnet address** for `/internal/outbox/*`; the worker's
`tenants.yaml` `podcast.outbox_base_url` gets pointed there (currently a placeholder) and
redeployed — then it drains real envelopes. Nothing else changes.

## What the worker already does (so you can rely on it)

Drains your outbox → renders (Gmail-safe HTML, week-specific title, graph-carrying) → sends via
Resend (email) / self-hosted Web Push (push) → writes terminal status back. Bounces/complaints:
polls `GET /emails/{id}` per sent message (Resend has **no** pollable `/events` list — it's
webhook-only) and reports `bounced`/`complaint` to your outbox. Full o11y (metrics, logs,
GlitchTip) tagged by tenant + `correlation_id` (= your envelope `id`, also sent to Resend as
`X-Correlation-Id`).
