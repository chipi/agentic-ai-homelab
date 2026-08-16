# Level 3 — orrery + moss telemetry flip to the TLS nodes

**From:** homelab agent (owns the mini + the caddy-tailscale TLS nodes).
**Context:** homelab is retiring the raw plaintext ingest ports `homelab:8090` (GlitchTip)
and `homelab:3001` (Umami). Every app that still ingests via those raw ports must flip to
the per-service caddy-tailscale TLS nodes (`glitchtip.<TAILNET>.ts.net` /
`umami.<TAILNET>.ts.net`, real certs) **before** the homelab closes them. Podcast player +
operator-viewer already migrated + proven with real events. Remaining: **orrery** and **moss**.

## What the reprovision wiped (and what's already restored)
The OrbStack→colima cutover started GlitchTip + Umami on **fresh empty volumes** — all
user-created projects/DSN-keys/websites were lost (unrecoverable; no backup existed). The
homelab agent has recreated, **match-ID** (same project id + key, same website UUID → zero
app-side change), everything it had values for:

| Surface | GlitchTip project · key | Umami UUID | Status |
|---|---|---|---|
| Player (web+MCP) | 5 · `5edf9f1c…` | `cd384a3e…` | restored + real-event proven |
| Operator viewer (gi-kg-viewer) | 1 · `d8aa7c66…` | `a5a60c25…` | restored + real-event proven |
| **Orrery** | **1 · `d8aa7c66…`** (shares gi-kg-viewer's project) | **`fb07dfd6…`** | **restored (this doc)** |
| Delivery (mini-local) | 13 · `503ef68e…` | — | restored |
| **Moss** | unknown — not on any box the homelab reaches | unknown | **NOT restored — needs moss's values** |

## Cleanup is HELD
The homelab will **not** close `homelab:8090` / `:3001` until **both** orrery and moss
confirm they're off the raw ports. Raw ports stay open the whole time → every flip is
instantly reversible (revert the vhost + restart caddy, no telemetry lost).

## header_up Host is mandatory (verified)
The caddy-tailscale nodes match **strictly on Host** and **silently drop a foreign Host** —
they return an empty `200` and the request never reaches the backend (looks like success,
telemetry lost). `reverse_proxy` forwards the incoming public Host by default, so it MUST be
overridden to the node name. Evidence: `Host=node → 403` (GlitchTip) / `400` (Umami) =
reached; `Host=foreign → 200` empty = dropped.

**Deny-list:** do NOT hardcode the tailnet FQDN in the repo (the operator-identifier gate
fails the PR). Inject `<TAILNET>` at deploy time (like the existing domain rewrite), derived
from `vars.PROD_TAILNET_FQDN` (everything after the first label).

---

## Handover — orrery agent (ready now)
See the paste block relayed to the operator. Summary: GlitchTip project 1 + Umami
`fb07dfd6…` already restored → orrery agent flips `orrery-telemetry.caddy` +
`orrery-analytics.caddy` to the nodes (with `header_up Host`), deploys, verifies a real
event lands, then reports "orrery off the raw ports". **First action: confirm the live
`PUBLIC_SENTRY_DSN` key is really `d8aa7c66…`/project 1** — if it differs, send the homelab
agent the real DSN and it fixes project 1's key before cutover. Orrery metrics/logs go to
Grafana Cloud (grafana-agent), unaffected.

## Handover — moss agent (two-step)
Moss's telemetry values are **not** on any box the homelab reaches, so its old project/site
are gone and can't be matched blind. Step 1: moss agent sends the homelab agent moss's live
GlitchTip DSN (`https://<key>@<host>/<project_id>`) + Umami website UUID (if used) from
moss's own config; homelab match-ID restores them and confirms. Step 2: moss agent flips its
caddy vhost(s) to the nodes (with `header_up Host`), deploys, verifies a real event lands,
reports "moss off the raw ports". Also confirm where moss's metrics/logs go — if moss pushes
to `homelab:8428/:9428`, that path needs checking too before the raw ports close.
