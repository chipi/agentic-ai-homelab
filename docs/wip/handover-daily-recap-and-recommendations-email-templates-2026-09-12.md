# Handover — daily-recap + recommendations email templates (2026-09-12)

**Repo:** `infra/delivery` (the Resend last-mile worker, ADR-144). **Commit:** `e1ea3a5` (pushed to
`main`). **Status:** built + tested, **NOT deployed**.

## Why this happened

The app enqueues four email/push templates, but this worker only had templates for
`your-week-digest.v1` and `resurface-nudge.v1`. Two enqueued emails therefore hit `RenderError` and
never sent:

- **`recommendations-digest.v1`** — the wave-H monthly discovery digest. **Silently never sending**
  since it shipped (no template + the vendored schema didn't even list it / `monthly` cadence).
- **`daily-recap.v1`** — the new RFC-122 #2039 end-of-day recap (podcast app repo `feat/player-improvements`).

## What we did (`e1ea3a5`)

- Added `delivery/templates/podcast/email/daily-recap.v1.{subject,html}.j2` — dark Close-Listening
  brand (same shell as your-week), **adaptive**: full recap for one episode, compact stack for many.
- Added `delivery/templates/podcast/email/recommendations-digest.v1.{subject,html}.j2` (reuses the
  `payload.sections` shape).
- `render.py`: **type-aware unsubscribe** — `…/comms/unsubscribe?ref=<ref>&type=<env.type>` so a
  `daily_recap` unsub disables the recap, not the weekly digest; added the `new_in_interests`
  section label + a `monthly` branch to `_period_label`. `envelope.py` now parses `type` (default
  `"digest"`, back-compat).
- Synced the vendored seam schema from the app (`schema/podcast/delivery-envelope.schema.json`:
  adds `daily_recap` type, the two templates, `monthly` cadence) + golden fixtures for both.
- Tests: `pytest` → **36 passed** (both new fixtures schema-validate + render). `mypy` clean.

## What's needed now — DEPLOY

1. **Deploy this worker** to the homelab (tailnet, `tenants.yaml` → `podcast` drains the prod player
   API outbox at `100.124.111.115:8099`). `RESEND_API_KEY` is already set — weekly digests send today,
   so no new secret/DNS work.
2. **Verify after deploy:**
   - A `recommendations-digest.v1` envelope now renders + sends (it never did — worth confirming a
     real send lands, since this was a silent multi-week gap).
   - A `daily-recap.v1` envelope renders; one-click unsubscribe link carries `&type=daily_recap`.
3. **`podcast-dev` tenant** uses box-local symlinks `templates/podcast-dev -> podcast` (per
   `tenants.yaml`); confirm the symlink still resolves so dev drains render too.

## Not in scope here

- The app enqueues at a **fixed UTC hour** (no per-user timezone yet) — tracked in the app repo, not
  a worker concern.
- `daily_recap` is **email-only** (no push template needed; none is enqueued).
