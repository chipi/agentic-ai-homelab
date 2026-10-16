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

## Source maps (readable JS stack traces)

CI builds source maps, and the mini uploads them. CI runners can't reach GlitchTip: the
tailnet ACL gives `tag:gha-deployer` no path to the glitchtip node, and the public
`telemetry.*` edges serve error ingest only.

1. **App CI** (each deploy job):
   - runs `npx @sentry/cli@2.58.6 sourcemaps inject <dist>`;
   - deploys that same build;
   - uploads the injected `.js` + `.js.map` files as a run artifact named
     `sourcemaps-<release>`. `<release>` must be the release string the app's SDK sends.
2. **The mini:** `upload-sourcemaps.py --apply`, run every 15 min by
   `com.homelab.glitchtip-sourcemaps.plist`.
   - It finds successful runs of the app's deploy workflow (the `APPS` list in the script).
   - It downloads each artifact with `gh`, uploads it with sentry-cli to
     `http://127.0.0.1:8090`, and records the run in `~/glitchtip/sourcemaps-state.json`.
   - A run is recorded only once GlitchTip has stored a bundle for every debug id, so a
     failure is retried on the next tick. The log is
     `/tmp/com.homelab.glitchtip-sourcemaps.log`.
   - Token: `~/glitchtip/orrery-sourcemaps.env` (`project:releases`, org-wide).

Two settings make the upload work at all. Both are in `docker-compose.yml` (2026-10-16):

- `GLITCHTIP_CHUNK_UPLOAD_USE_RELATIVE_URL=true`. Without it, GlitchTip tells clients to
  upload chunks to the tailnet name, which the mini can neither resolve nor reach.
- A shared `uploads` volume for web and worker. Without it, the worker never sees the chunks
  web received, and every assemble fails with `FileNotFoundError`. sentry-cli still exits 0
  in that case, so check the stored bundle (as the script does), not the exit code.

To add an app: add a row to `APPS` and add the artifact step to its deploy job.

## Backup / rollback

- Config in git; data in the `pg-data` volume, uploaded source maps in the `uploads` volume.
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
