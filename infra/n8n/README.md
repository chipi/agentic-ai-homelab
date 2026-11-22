# n8n: the installation's plumbing tool

The layer between the company's tools and flotilla (flotilla
[RFC-0014](https://github.com/chipi/flotilla/blob/main/docs/rfc/RFC-0014-visual-plane-and-mashups.md) §4.0, §4.7):
it calls flotilla through flotilla's signed webhook, and flotilla calls it back through signed HTTP. Set up on
2026-11-22 at the operator's go. **No workflows and no connectors**: the operator adds those case by case.

**Licence.** n8n is under the Sustainable Use License: the installation's own internal use is fine; it is never
offered to others as a service.

## Stack

- `n8n` (`docker.n8n.io/n8nio/n8n:2.48.7`, pinned) and `n8n-db` (`postgres:17-alpine`, its own).
- Networks, all internal, nothing published on the host:
  - `plumbing`: n8n, flotillad (flotilla's compose joins it as an external network) and alloy-homelab
    (scrapes `/metrics`).
  - `n8n_db`: n8n and its Postgres only.
  - `n8n_ui`: n8n and caddy only: the editor at **https://n8n.tail6d0ed4.ts.net** (tailnet only; caddy answers 404 for webhook paths there). Deploy n8n before `infra/reverse-proxy`.
- **Base URL for webhooks, as flotillad's container sees it:** `http://n8n:5678/` (webhooks under
  `/webhook/<path>`, test webhooks under `/webhook-test/<path>`).
- No route out: a connector that needs the internet needs a network decision first.

## Run (on the mini, in this checkout)

```sh
cp .env.example .env && chmod 600 .env    # then replace each <generate: ...> with its output
docker compose up -d
docker inspect -f '{{.State.Health.Status}}' n8n   # healthy
bash owner-setup.sh                          # once: the owner login, into ~/n8n/owner.env
```

## Credentials (values never printed)

| What | Where (mini, mode 600) | Variables |
|---|---|---|
| Database password, encryption key | `~/agentic-ai-homelab/infra/n8n/.env` | `N8N_DB_PASSWORD`, `N8N_ENCRYPTION_KEY` |
| Owner login | `~/n8n/owner.env` | `N8N_OWNER_EMAIL`, `N8N_OWNER_PASSWORD` |

`N8N_ENCRYPTION_KEY` encrypts every credential n8n stores; without it a restored database's credentials are
unreadable. The stacks' `.env` files are not in the backups: keep a copy in the password manager.

## Observability and backup

- **Logs:** alloy-homelab ships the containers' stdout like every other container (`service="n8n"`).
- **Health:** the container healthcheck (`/healthz`), and alloy scrapes `n8n:5678/metrics` (job `n8n`).
  The generic alert `infra-target-down` (warning) fires when `up{job="n8n"}` is 0 for 5 minutes; a
  missing container scrapes as 0 too.
- **Backup:** `n8n-db` is in the nightly `pg_dump` of `infra/backup/dump-observability-dbs.sh`, and so in the
  encrypted off-mini copy.

## Upgrade

n8n migrates its database on start. Bump the tag here, take a dump first
(`docker exec n8n-db pg_dump -U n8n n8n | gzip > ~/db-backups/n8n-db-pre-upgrade.sql.gz`), then
`docker compose up -d` and check health. Undo: the old tag plus that dump restored into `n8n-db`.

## Not covered

- The editor is reachable by every tailnet device; n8n's own login (the owner) is what protects it.
- The hook and `plumbing.call` (flotilla's side) are not built; nothing calls n8n yet.
