# homelab-serve — tailnet HTTPS entry points for the mini's services

The self-hosted services on the mini bind plain HTTP on the tailnet. Browsers /
mobile apps refuse cleartext (iOS ATS, Android cleartext default, Capacitor
mixed-content), so each service is fronted by **`tailscale serve`** — a
Tailscale-issued cert for the node's `*.ts.net` FQDN, **tailnet-only, no public
exposure** (serve, not funnel). This dir captures that map as code so it can be
rebuilt on demand.

Base FQDN: `https://homelab.tail6d0ed4.ts.net` (the mini, tag `homelab-host`).

## The map

| URL | Backend | Kind |
|---|---|---|
| `…/grafana` | `:3000` Grafana | web UI (needs `GRAFANA_ROOT_URL`) |
| `…/glitchtip` | `:8090` GlitchTip | ingest + API |
| `…/umami` | `:3001` Umami | web UI |
| `…/litellm` | `:4001` LiteLLM | gateway API + `/ui` |
| `…/vm` | `:8428` VictoriaMetrics | API + `/vmui` |
| `…/vlogs` | `:9428` VictoriaLogs | API + UI |
| `…/vtraces` | `:10428` VictoriaTraces | API |
| `…/home` | `:8888` homelab-home | landing page (basic-auth) |
| `…:8443/` | `:4000` Langfuse | web UI + API (dedicated TLS port) |

## Re-apply (the point of this dir)

Run **on the mini** (needs the App-Store Tailscale app context; the
`/usr/local/bin/tailscale` wrapper no-ops over SSH — the script uses the real
binary in `/Applications/Tailscale.app`). No sudo needed.

```sh
cd ~/agentic-ai-homelab/infra/homelab-serve
./serve-map.sh            # apply / reconcile (idempotent)
./serve-map.sh --status   # print current serve status
./serve-map.sh --reset    # clean slate first, then apply (brief blip)
```

The serve config persists in tailscaled state across reboots, so you usually
don't need this — reach for it on a **fresh mini**, after a `serve reset`, or to
**reconcile drift**.

## Two patterns (when adding a service)

- **API / path-tolerant app → `:443` path mount** (`--set-path=/name`). Tailscale
  **strips** the `/name` prefix before proxying, so the backend sees requests at
  root. Works for APIs and GlitchTip ingest.
- **Web UI with root-absolute assets → dedicated TLS port** (`:8443`, `:10000`)
  *or* tell the app its external base URL:
  - **Grafana:** `GF_SERVER_ROOT_URL=…/grafana` + `serve_from_sub_path=false`
    (set via `GRAFANA_ROOT_URL` in `infra/observability/backend/.env`). Then
    `/grafana` works with a stripping proxy.
  - **Langfuse (Next.js):** no clean subpath support → dedicated port `:8443`,
    plus `AUTH_TRUST_HOST=true` on langfuse-web (in `infra/langfuse/`) so NextAuth
    login works over the `:8443` origin.

## ACL — required for reach

A mount is reachable from **other** tailnet devices only after its port is
granted to `tag:homelab-host` in
[`podcast_scraper-infra` `tailscale/policy.hujson`](https://github.com/chipi/podcast_scraper/blob/main/tailscale/policy.hujson)
and applied (`tofu apply`, via the `Infra apply (manual)` workflow). Currently
granted: `443` and `8443` (plus the direct service ports). Adding a new TLS port
(e.g. `:10000`) needs a new ACL line + apply. From the mini itself, mounts work
without the ACL (loopback).

## Related

- Systems index: [`infra/README.md`](../README.md)
- App-side config: [`infra/observability/backend/`](../observability/backend/) (Grafana),
  [`infra/langfuse/`](../langfuse/README.md) (Langfuse).
