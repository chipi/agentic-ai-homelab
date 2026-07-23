# Umami — self-hosted web analytics

Single, self-hosted analytics tool for orrery (and later podcast), running on the
`homelab` Mac mini beside the observability stack. Decision + rationale:
[ADR-0007](../../docs/adr/ADR-0007-umami-self-host-analytics.md). Tracking issue: #8.

## Stack

- `umami` — the Node app (`ghcr.io/umami-software/umami:postgresql-latest`).
- `umami-db` — a dedicated `postgres:16-alpine` (not shared with GlitchTip/Langfuse).
- Published on **`:3001`** (Grafana holds `:3000`).

## Run

```sh
cp .env.example .env      # fill secrets (see below)
docker compose up -d
curl -fsS http://localhost:3001/api/heartbeat   # 200 = up
```

Secrets:
```sh
UMAMI_DB_PASSWORD=$(openssl rand -hex 24)
UMAMI_APP_SECRET=$(openssl rand -hex 32)
```

First run creates a default admin **`umami` / `umami`** — **rotate immediately**
(Settings → Profile → Password).

## The public-ingress split (important)

Unlike the rest of the mini (tailnet-only), Umami's **tracking beacon must be
public** — visitor browsers load `script.js` and POST events from the open
internet. So:

- **Admin UI (`:3001`)** — keep **tailnet-only** (`UMAMI_LISTEN` = tailnet IP);
  needs an ACL grant to `tag:homelab-host:3001` for the operator.
- **Beacon path** — exposed publicly via **Tailscale Funnel** or **Cloudflare
  Tunnel** (operator decision, #8). Only the collection endpoint is public.

## Wire up a site (e.g. orrery)

1. Log into the admin UI → **Settings → Websites → Add** → name + domain.
2. Copy the tracking snippet; the `data-website-id` is the site's UUID.
3. Point `src` at the **public** beacon host (the tunnel/Funnel URL), not the
   tailnet address:
   ```html
   <script defer src="https://<public-umami-host>/script.js"
           data-website-id="<uuid>"></script>
   ```
4. For orrery: replace the current (hosted-Umami) snippet with this one.

## Ops

- Data lives in the `umami-db-data` volume (Postgres). Back it up with the mini's
  usual volume backup.
- Upgrades: bump the image tag, `docker compose pull && up -d` (Umami self-migrates).
