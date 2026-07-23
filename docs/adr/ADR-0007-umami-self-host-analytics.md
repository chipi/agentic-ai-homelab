# ADR-0007 — Consolidate analytics on self-hosted Umami (over PostHog)

**Status:** Accepted. Umami stack **stood up** on the mini 2026-07-22; public
ingress + orrery cutover pending (issue #8).
**Date:** 2026-07-22
**ctx src:** this session. Operator drivers: one tool not two, own-the-stack,
low maintenance, fits the mini. Relates to [ADR-0005](ADR-0005-langfuse-glitchtip-self-host.md)
(the observability platform this sits beside) and issue #8.

## ctx

Analytics were split across two products and two tools: **orrery → Umami**
(hosted), **podcast → PostHog**. The operator wants **one** analytics tool,
**self-hosted on the `homelab` Mac mini**, next to the existing observability
stack (VictoriaMetrics/Logs/Traces + Grafana + GlitchTip + Langfuse).

## Decision

**Umami, self-hosted on the mini.** A single Node app + one dedicated Postgres.

Rationale:
- **Resource fit.** Umami is featherweight (~300–500 MB). Self-hosted **PostHog**
  is a beast — ClickHouse + Kafka + Redis + Postgres + Zookeeper + workers — and
  the mini is already carrying VictoriaMetrics/Logs/Traces, GlitchTip, and
  Langfuse (which itself drags in ClickHouse + Postgres + Redis + MinIO). Adding
  PostHog's ClickHouse+Kafka invites contention/OOM.
- **PostHog discourages self-hosting.** Its OSS "hobby" deploy is community-
  maintained and steered toward Cloud. Self-hosting the thing its vendor tells
  you not to self-host is the wrong bet.
- **Fit to need.** Both products are sites/viewers; their core needs (pageviews,
  sources, UTM, events, basic funnels/retention/goals) are covered by Umami v2.
  Cookieless + privacy-friendly is a bonus.

## The one architectural wrinkle — Umami must be PUBLIC

Unlike every other service on the mini (tailnet-only by design, ADR-0005), Umami's
**tracking beacon (`script.js` + the event endpoint) is loaded by end-users'
browsers on the public internet** — so the collection endpoint **must be publicly
reachable over HTTPS**. This is the one service that needs public ingress. Options
(operator decision, issue #8):
- **Tailscale Funnel** — zero extra deps; serves on the `*.ts.net` domain; needs
  a `funnel` node-attr in the tailnet policy.
- **Cloudflare Tunnel** — clean custom domain (orrery already fronts on
  Cloudflare); needs `cloudflared` + a CF-managed hostname.

The Umami **admin UI** stays tailnet-only (`:3001`); only the beacon path is
exposed.

## Alternatives considered

- **Self-host PostHog** — rejected: heavy stack, vendor-discouraged, poor mini fit.
- **PostHog Cloud** — kept as the **fallback** *if* the podcast viewer later needs
  product-analytics depth (session replay, feature flags, deep funnels). Use Cloud
  for that, not self-host. Not needed for the current pageview/event scope.
- **Umami Cloud** — rejected: the point is to own the stack (same driver as ADR-0005).
- **Keep both tools** — rejected: the operator wants one.

## Consequences

- **Positive:** one privacy-friendly, low-maintenance analytics tool the mini
  handles trivially; sits beside the observability stack; own the data.
- **Negative:** loses PostHog's product-analytics depth (session replay, flags) —
  acceptable for site/viewer scope; PostHog Cloud remains the escape hatch.
- **Migration:** orrery cuts over ASAP (primary ask); podcast follows — export any
  PostHog history worth keeping *before* cutover (it's abandoned otherwise).
- **New public surface:** the beacon endpoint is the mini's first public ingress —
  keep the admin UI tailnet-only; expose only the collection path.
