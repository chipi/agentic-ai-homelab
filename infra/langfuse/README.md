# Langfuse — self-hosted LLM/agent tracing

Langfuse v3, self-hosted (ADR-0005). Captures how the harnesses (Claude Code,
opencode, Pi) and apps talk to models: prompts, completions, token/cost,
latency, session/trace trees. Tailnet-only, on the always-on **Mac mini**
(`homelab`) — verified live 2026-07-25; reach the web UI at
`https://langfuse.tail6d0ed4.ts.net` (via Tailscale certificate node/Caddy — 
Next.js can't run under a stripped subpath; `:4000` is the internal backend port). 
(The brief DGX-hosted stopgap has been retired.)

Stack (adapted from upstream): `langfuse-web` + `langfuse-worker` + `postgres` +
`clickhouse` + `redis` + `minio`. Only **langfuse-web** publishes a host port
(tailnet IP : `LANGFUSE_PORT`, default `4000` — `3000` is Grafana's). All
datastores are internal-bridge only.

## Prerequisites

- Docker + compose, on the tailnet.
- **Tailnet ACL:** grant `LANGFUSE_PORT` (default **`4000`**) to the mini's
  (`homelab`) host tag — same per-port allowlist as the observability stack.

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

## Re-home to another host

Runs on the mini today. To move: `docker compose down` → migrate the five named
volumes (postgres, clickhouse data+logs, minio, redis) or start fresh (traces
are append-only; fresh-start loses history) → `up -d` on the new host → update
`NEXTAUTH_URL` + `LANGFUSE_LISTEN` to that host's tailnet IP + any senders' host.

## Backup / rollback

- Config in git; state in the five named volumes. Real backup = `pg_dump` +
  ClickHouse backup + MinIO data copy.
- Rollback a bad boot: `docker compose down` (add `-v` to wipe volumes — destructive).

## Retention / storage (audit 2026-08-30)

**Policy: 30 days.** Three independent caps, because Langfuse data lives in three
places. Two are runtime state on the mini (not in git) — re-apply them if the
stack is ever rebuilt from scratch:

| Layer | Cap | How it is set |
|---|---|---|
| ClickHouse traces/observations/scores | 30d | `projects.retention_days = 30` (Langfuse's own Data Retention job — the worker logs `Executing Data Retention Job` daily). Set in the UI (project settings) or: `docker exec langfuse-postgres-1 psql -U postgres -d postgres -c "update projects set retention_days=30"` |
| MinIO event blobs (`events/` prefix) | 30d | bucket lifecycle rule: `mc ilm rule add lf/langfuse --expire-days 30 --prefix "events/"` |
| ClickHouse's own debug logs | disabled | `clickhouse-lowcpu.xml` (in git) |

**What the audit found — the surprise.** The 3.7 GB ClickHouse volume was **91%
ClickHouse's own untTL'd telemetry**, not Langfuse data: `trace_log` 1.10 GiB /
36M rows, `text_log` 955 MiB / 21M rows, `metric_log` 366 MiB, `part_log` 279 MiB
— against **278 MiB of actual traces**. Real Langfuse growth is only ~17 MB/day;
the self-telemetry was ~185 MB/day of writes nobody reads. Disabling those logs
and dropping the old tables took the volume **3.69 GB → 442 MB** and the log-file
volume **632 MB → 30 KB**; a host `fstrim` returned 37.5 GiB.

Steady state at 30 days is roughly **0.5 GB ClickHouse + ~3.6 GB MinIO events**.
MinIO event blobs (~120 MB/day) are now the dominant Langfuse consumer — they are
raw ingestion payloads kept for replay, not needed to render the UI.

## Notes

- `langfuse` images pinned; datastores at upstream tags — **pin after first good boot**.
- No media/browser MinIO endpoint exposed → media previews in traces won't load
  (text LLM traces are unaffected). Publish MinIO on the tailnet if you need media.
- Reach at the tailnet IP `:4000`, never loopback/public. Don't expose publicly.

## Related

- Systems index: [`infra/README.md`](../README.md)
- Global docs: [Pillar 2 — Local AI infra](https://github.com/chipi/agentic-ai-homelab/blob/main/docs/local-ai-infra.md)
