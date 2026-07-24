# Phase 0 — signal-fleet infra consumption readiness

**Status:** ✅ **PASS** — every signal/correlation surface is consumable by an
agent via the platform's own prescribed integration, verified with live data.
**Date:** 2026-07-24
**Host:** everything runs on **`homelab`** (the Mac mini) — the DGX→mini migration
is effectively done; `dgx-llm-1:*` times out, `homelab:*` answers. Endpoints below
are `homelab:<port>` on the tailnet.

> Success bar (operator): *"you can get the data from all the surfaces and do all
> the things you want with agents later."* This doc is the proof + the exact
> consume recipe per surface. No DB reads, no hacks — each surface is consumed the
> way its platform prescribes.

## Result — per surface

| Surface | Prescribed consumer method | Endpoint | Auth | Verified (live) |
|---|---|---|---|---|
| **VictoriaMetrics** | PromQL HTTP API | `homelab:8428/api/v1/query` | none (tailnet) | `up` → 3 targets (`homelab/node`, `prod-podcast/api`, `prod-podcast/integrations/unix`) |
| **VictoriaLogs** | LogsQL HTTP API | `homelab:9428/select/logsql/query` | none | 7607 log lines / 15m |
| **VictoriaTraces** | Jaeger/Tempo HTTP API | `homelab:10428/select/jaeger/...` | none | services `player-api`, `podcast-api` |
| **GlitchTip** (errors) | **Sentry-compatible REST API** (poll issues) | `homelab:8090/api/0/...` | **API token** (label `signal-fleet`) | listed 8 projects; issues `PLAYER-4` (SyntaxError ×4), `ORRERY-B/C`, `PLAYER-3` |
| **Grafana** (alerts) | **read:** Alertmanager API · **push:** webhook contact point | `homelab:3000/api/alertmanager/grafana/api/v2/alerts` · webhook → fleet | admin basic-auth ⚠ *(a service-account token is Grafana's cleaner prescribed path — R3-6 follow-up)* | 7 rules incl. *"Orrery launch data stale"*; **push test delivered end-to-end** to the receiver (`status:firing` payload captured) |
| **Umami** (UX) | **REST API** after `POST /api/auth/login` | `homelab:3001/api/...` | login → bearer token | logged in; 7 sites (`orrery`, `player`=closelistening.app, `operator`…); stats endpoint returns pageviews/visitors |

## Consumption pattern (decided from what actually works)

- **Correlation reads** = the three Victoria\* query APIs — **no auth on the
  tailnet**, ready as-is. This is the join surface (job/instance/window/trace_id).
- **Error signals (GlitchTip)** = **poll the Sentry-compat REST API** with the
  token. Chosen over the webhook because GlitchTip's generic webhook is
  *Slack-shaped* (thin: title + link), so the API read is needed for real issue
  data regardless. (A project webhook alert can be added later as a
  latency optimization; not required for Phase 0.)
- **Alert triggers (Grafana)** = **both work**: poll the Alertmanager API, *or*
  receive a **webhook contact point** push (proven end-to-end here). The webhook
  is the low-latency path; the API poll is the reliable fallback.
- **UX (Umami)** = login → bearer token → stats/events API.

## What was created / deployed (this phase)

1. **GlitchTip API token** — label `signal-fleet`, full scopes, owned by
   `admin@homelab.local`. Minted via GlitchTip's own management shell
   (`api_tokens.APIToken`). Used for the read API.
2. **Test webhook receiver** — `signal-fleet/test-receiver/receiver.py` (stdlib,
   no deps), deployed to the mini at `~/signal-fleet-receiver/`, running on
   **`:8099`**. Reachable from the host and from containers via
   `host.docker.internal:8099`. Captures inbound webhooks to `captures.log`. This
   is the homelab **test entry point** — a stand-in for the real fleet ingress; it
   already captured Grafana's push. *It is a harness, not production.*

## Secrets — where they live (values intentionally NOT in this doc)

The fleet must load these from env/sops at runtime; **never commit values.**
- GlitchTip token — label `signal-fleet` (in GlitchTip's DB). Move into the
  fleet's secrets store for reuse.
- Grafana admin — `infra/observability/backend/.env` (`GRAFANA_ADMIN_*`).
- Umami admin — `~/umami/.env` (`UMAMI_ADMIN_PASSWORD`); login user is `admin`.

## NOT done / follow-ups (honest gaps)

- **GlitchTip project webhook alert recipient** — not created (poll chosen as the
  data path). Add later if push latency matters.
- **The receiver is a test stub**, not the fleet's real ingress, and it's running
  under `nohup` on the mini — stop it (`pkill -f 'receiver.py 8099'`) or leave it
  for further trigger tests.
- **Tailscale ACLs / persistence** — consumption worked from this Mac and on-box;
  the real fleet (on the mini) reads localhost, so no new ACL is needed for reads.
  A production webhook ingress + its ACL is Phase-1.
- **Token/cred storage for the fleet** — currently the token exists in GlitchTip
  but isn't yet wired into a fleet secrets file (sops). Do that when the fleet
  ingress is built.
- **Least-privilege debt (R3-6)** — Phase-0 consumed each source with the broadest
  handy credential: GlitchTip token minted **full-scope** (needs issue-read + later
  resolve), Grafana via the **admin** password, Umami via the **admin** login, and
  `mvp/run.sh` sources whole stack `.env`s into the fleet process. None blocks the
  MVP; before the daemon/ingress phase, do one scope-down pass: a read/resolve-only
  GlitchTip token, a Grafana service account, a Umami view-only user, and a
  fleet-owned sops file.

See [`SIGNALS.md`](SIGNALS.md) §6/§8 for how these surfaces feed the triager.
