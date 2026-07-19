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
- **Tailnet ACL:** grant the web port (default **`8090`**) to this host's tag in
  the Tailscale admin console — same per-port allowlist as the observability
  stack. Needed for both the UI (your Mac) and ingest (Mac dev + VPS prod).

## Bring-up

```sh
cd infra/glitchtip
cp .env.example .env
# edit .env:
#   GLITCHTIP_LISTEN=100.x.y.z            # this host's tailnet IP
#   GLITCHTIP_DOMAIN=http://100.x.y.z:8090
#   POSTGRES_PASSWORD=...  SECRET_KEY=...  DJANGO_SUPERUSER_PASSWORD=...
docker compose up -d            # runs migrate → web + worker
docker compose ps

# bootstrap the admin user (idempotent; ignores "already exists"):
docker compose run --rm web ./manage.py createsuperuser --noinput \
  --email "$(grep DJANGO_SUPERUSER_EMAIL .env | cut -d= -f2)" || true
```

Open `http://100.x.y.z:8090`, log in with the superuser. Create an
**Organization** → **Project** (platform = python or whatever the app is) → copy
its **DSN**.

## Point an app at it (Sentry SDK)

Any Sentry SDK works — just set the DSN + environment. Python example:

```python
import sentry_sdk
sentry_sdk.init(
    dsn="http://<public_key>@100.69.49.126:8090/<project_id>",
    environment="prod",        # "dev" on the Mac, "prod" on the VPS
    traces_sample_rate=0.0,    # errors only; raise for perf tracing
)
```

The DSN host must be the tailnet IP:port the app can reach.

## Move to the Mac mini later

1. `docker compose down` here (DGX).
2. Migrate the `pg-data` volume (or `pg_dump`/restore), or start fresh (errors
   are append-only — fresh-start loses history).
3. `docker compose up -d` on the mini; give it the tailnet name/IP apps expect,
   or update each app's DSN host.

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
