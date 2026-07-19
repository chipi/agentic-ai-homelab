# Langfuse — self-hosted LLM/agent tracing

Langfuse v3, self-hosted (ADR-0005). Captures how the harnesses (Claude Code,
opencode, Pi) and apps talk to models: prompts, completions, token/cost,
latency, session/trace trees. Tailnet-only, one host (DGX now, Mac mini later).

Stack (adapted from upstream): `langfuse-web` + `langfuse-worker` + `postgres` +
`clickhouse` + `redis` + `minio`. Only **langfuse-web** publishes a host port
(tailnet IP : `LANGFUSE_PORT`, default `4000` — `3000` is Grafana's). All
datastores are internal-bridge only.

## Prerequisites

- Docker + compose, on the tailnet.
- **Tailnet ACL:** grant `LANGFUSE_PORT` (default **`4000`**) to
  `tag:dgx-llm-host` — same per-port allowlist as the observability stack.

## Bring-up

```sh
cd infra/langfuse
cp .env.example .env
# generate + fill secrets (see comments in .env); the important consistency rules:
#   DATABASE_URL password  == POSTGRES_PASSWORD
#   *_S3_*_SECRET_ACCESS_KEY == MINIO_ROOT_PASSWORD
#   ENCRYPTION_KEY = openssl rand -hex 32 (exactly 64 hex chars)
# set LANGFUSE_LISTEN=100.x.y.z and NEXTAUTH_URL=http://100.x.y.z:4000
docker compose up -d          # postgres/clickhouse/minio/redis come healthy, then web+worker
docker compose ps
```

First boot runs DB + ClickHouse migrations (can take a minute). The
`LANGFUSE_INIT_*` vars bootstrap an **org + project + API keys + admin user**, so
Langfuse comes up ready — no UI setup needed for the keys.

Open `http://100.x.y.z:4000`, log in with `LANGFUSE_INIT_USER_EMAIL` /
`_PASSWORD`. The project's **public/secret keys** are what apps/proxies use to
send traces (`LANGFUSE_INIT_PROJECT_PUBLIC_KEY` / `_SECRET_KEY`).

## Sending traces (capture path — decided separately)

Ingest host for any SDK/proxy: `http://100.x.y.z:4000` with the project keys.
Two paths (per ADR-0005 §4, chosen at wiring time):

- **LiteLLM proxy choke point** — all harnesses → LiteLLM → providers; LiteLLM
  logs to Langfuse. Uniform, provider-agnostic. (Recommended.)
- **OTEL / native per-harness** — point each harness's OTLP/SDK at Langfuse.

**dev vs prod:** tag traces with an environment (Langfuse supports trace
`environment`) — Mac coding agents + podcast app = `dev`, VPS = `prod` — or use
separate projects. Decide when wiring.

## Move to the Mac mini later

`docker compose down` here → migrate the five named volumes (postgres,
clickhouse data+logs, minio, redis) or start fresh (traces are append-only;
fresh-start loses history) → `up -d` on the mini → update `NEXTAUTH_URL` +
`LANGFUSE_LISTEN` to the mini's tailnet IP + any senders' host.

## Backup / rollback

- Config in git; state in the five named volumes. Real backup = `pg_dump` +
  ClickHouse backup + MinIO data copy.
- Rollback a bad boot: `docker compose down` (add `-v` to wipe volumes — destructive).

## Notes

- `langfuse` images pinned; datastores at upstream tags — **pin after first good boot**.
- No media/browser MinIO endpoint exposed → media previews in traces won't load
  (text LLM traces are unaffected). Publish MinIO on the tailnet if you need media.
- Reach at the tailnet IP `:4000`, never loopback/public. Don't expose publicly.
