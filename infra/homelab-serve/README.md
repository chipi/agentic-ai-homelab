# homelab-serve — tailnet HTTPS entry points for the mini's services

> ⚠️ **DEPRECATED (2026-08-15) — RETIRED, do not use.** Exposure moved to
> **per-service caddy-tailscale nodes** (`grafana./glitchtip./umami./langfuse./
> litellm./vm./vlogs./vtraces./hub.tail6d0ed4.ts.net`, each with a real Tailscale
> cert). See [`infra/reverse-proxy/`](../reverse-proxy/) for the current
> architecture and [`docs/observability-dependency-map.md`](../../docs/observability-dependency-map.md)
> for who consumes what. `tailscale serve` is empty on the mini; the old
> `:8443/:8444/:8445/:10000/:9443` ports and `:443` paths below are historical.

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
| `…/glitchtip` | `:8090` GlitchTip | ingest + API (admin UI is on `:8445`) |
| `…/litellm` | `:4001` LiteLLM | gateway **API** (path-tolerant; UI is on `:10000`) |
| `…/vm` | `:8428` VictoriaMetrics | API + `/vmui` |
| `…/vlogs` | `:9428` VictoriaLogs | API + UI |
| `…/vtraces` | `:10428` VictoriaTraces | API |
| `…/home` | `:8888` homelab-home | landing page (basic-auth) |
| `…:8443/` | `:4000` Langfuse | web UI (dedicated TLS port — Next.js) |
| `…:8444/` | `:3001` Umami | web UI (dedicated TLS port — Next.js) |
| `…:8445/` | `:8090` GlitchTip | admin UI (dedicated TLS port — Angular `base href=/`) |
| `…:10000/ui/` | `:4001` LiteLLM | admin UI (dedicated TLS port — Next.js) |

> The `/umami` `:443` path mount was **removed** — it only served Umami's broken
> shell. The `/litellm` and `/glitchtip` `:443` mounts stay as path-tolerant
> **APIs** (LLM gateway / error ingest); their web UIs are on the dedicated ports
> above.

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
- **Web UI with root-absolute assets → dedicated TLS port** (`:8443`, `:8444`,
  `:8445`, `:10000`) *or* tell the app its external base URL:
  - **Grafana:** `GF_SERVER_ROOT_URL=…/grafana` + `serve_from_sub_path=false`
    (set via `GRAFANA_ROOT_URL` in `infra/observability/backend/.env`). Then
    `/grafana` works with a stripping proxy.
  - **Langfuse / Umami / LiteLLM (Next.js):** no clean subpath support (they emit
    root-absolute `/_next` or `/…-asset-prefix/_next` assets that 404 under a
    stripped mount) → dedicated ports `:8443` / `:8444` / `:10000`. Langfuse also
    needs `AUTH_TRUST_HOST=true` on langfuse-web (in `infra/langfuse/`) so NextAuth
    login works over the `:8443` origin.
  - **GlitchTip (Angular):** emits `<base href="/">` so `/static` assets resolve
    to root and 404 under `/glitchtip` → dedicated port `:8445`, plus
    `GLITCHTIP_DOMAIN=https://homelab.<tailnet>:8445` (in `infra/glitchtip/.env`)
    so Django `ALLOWED_HOSTS`/`CSRF_TRUSTED_ORIGINS` accept the `:8445` origin.

## ACL — required for reach

A mount is reachable from **other** tailnet devices only after its port is
granted to `tag:homelab-host` in
[`podcast_scraper` `tailscale/policy.hujson`](https://github.com/chipi/podcast_scraper/blob/main/tailscale/policy.hujson)
and applied. **GitOps per ADR-128** (NOT tofu): a **PR** touching `policy.hujson`
runs the `test` dry-run; **merge to `main`** runs the live `apply` (the Tailscale
GitOps action, `.github/workflows/tailscale-acl.yml`). Currently granted TLS
ports: `443`, `8443`, `8444`, `10000` (plus the direct service ports). Adding a
new port needs a new ACL line + merge. From the mini itself, mounts work without
the ACL (loopback).

## Related

- Systems index: [`infra/README.md`](../README.md)
- App-side config: [`infra/observability/backend/`](../observability/backend/) (Grafana),
  [`infra/langfuse/`](../langfuse/README.md) (Langfuse).
