# GlitchTip — self-hosted error tracking

Sentry-SDK/DSN-compatible error tracking, self-hosted (ADR-0005). Apps send
exceptions via a normal Sentry SDK pointed at a **project DSN**; you filter
**dev vs prod** with the SDK `environment` tag:

- **dev** — Mac (coding agents + podcast app running locally)
- **prod** — VPS (`prod-podcast`)

One GlitchTip project receives both; filter by environment in the UI.

Stack: `web` + `worker` (celery+beat) + `postgres` + `redis`. Web UI/ingest bind
to the tailnet IP only; datastores stay on the internal bridge.

## Prerequisites

- Docker + compose, on the tailnet.
- **Tailnet ACL:** grant port `8090` to this host's tag (loopback-only for ingest; the web UI uses the `glitchtip` node, not this port). Also grant the `glitchtip` node cert for HTTPS access.

## Bring-up

```sh
cd infra/glitchtip
cp .env.example .env
# edit .env:
#   GLITCHTIP_LISTEN=127.0.0.1              # loopback only; HTTPS via caddy-tailscale node
#   GLITCHTIP_DOMAIN=https://glitchtip.tail6d0ed4.ts.net   # canonical admin-UI URL (tailscale node)
#   POSTGRES_PASSWORD=...  SECRET_KEY=...  DJANGO_SUPERUSER_PASSWORD=...
docker compose up -d            # runs migrate → web + worker
docker compose ps

# bootstrap the admin user (idempotent; ignores "already exists"):
docker compose run --rm web ./manage.py createsuperuser --noinput \
  --email "$(grep DJANGO_SUPERUSER_EMAIL .env | cut -d= -f2)" || true
```

Open the admin UI at **`https://glitchtip.tail6d0ed4.ts.net`** — HTTPS via a
dedicated Tailscale certificate node (Caddy reverse-proxy), because GlitchTip's 
Angular frontend emits `<base href="/">` and can't run under a stripped `/glitchtip` 
subpath. `GLITCHTIP_DOMAIN` must match this origin or Django rejects login on CSRF. 
Log in with the superuser. Create an **Organization** → **Project** (platform = python 
or whatever the app is) → copy its **DSN**.

## Point an app at it (Sentry SDK)

Any Sentry SDK works — just set the DSN + environment. Python example:

```python
import sentry_sdk
sentry_sdk.init(
    dsn="http://<public_key>@homelab:8090/<project_id>",
    environment="prod",        # "dev" on the Mac, "prod" on the VPS
    traces_sample_rate=0.0,    # errors only; raise for perf tracing
)
```

The DSN host must be the tailnet IP:port the app can reach.

## Where it runs

On the always-on **Mac mini** (`homelab`) — verified live 2026-07-25; reach the
admin UI at `https://glitchtip.tail6d0ed4.ts.net` (via Tailscale certificate node/Caddy).
The `:8090` port binds loopback only (not exposed to the tailnet); ingest uses that port
internally, but the web UI is served via the dedicated `glitchtip` node. The
brief DGX-hosted stopgap has been retired. To **re-home** in future: `docker compose down`, 
migrate the `pg-data` volume (or `pg_dump`/restore) or start fresh (errors are append-only — 
fresh-start loses history), `docker compose up -d` on the new host, give it the `homelab` 
tailnet name apps expect (or update each app's DSN host).

## Backup / rollback

- Config in git; data in the `pg-data` volume.
- Backup: `docker compose exec postgres pg_dump -U glitchtip glitchtip > backup.sql`.
- Rollback a bad bring-up: `docker compose down` (add `-v` to also wipe data —
  destructive).

## Notes

- Registration is closed (`ENABLE_OPEN_USER_REGISTRATION=false`) — tailnet-private,
  first user is the superuser.
- Ports bind to the tailnet IP → reach at `100.x.y.z`, not `127.0.0.1`.
- Don't expose `8090` publicly — tailnet only.

## Related

- Systems index: [`infra/README.md`](../README.md)
- Global docs: [Pillar 2 — Local AI infra](https://github.com/chipi/agentic-ai-homelab/blob/main/docs/local-ai-infra.md)
