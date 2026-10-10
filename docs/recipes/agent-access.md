# Agent access to the homelab — hosts, databases, APIs, files

## Why this exists

Agents working on the operator's products (Close Listening, Orrery, the homelab
services) need to look inside them: query a database, call an API, read app data,
check logs, and sometimes write something. **All of that already works with the
access the operator's account has** — no extra logins, ports or groups are needed.
This page is the map. Every command on it was run on 2026-10-10.

## Quick reference — getting onto each host

| Host | What runs there | Command (from the operator's laptop) |
|---|---|---|
| Mac mini (`homelab`) | observability, delivery, Umami, GlitchTip, Langfuse, LiteLLM (homelab) | `ssh -i ~/.ssh/homelab_mini -o IdentitiesOnly=yes homelab` |
| Mac mini, `claude` account | where agents on the mini run; dev engine only | `ssh homelab-claude` |
| Prod VPS (`prod-podcast`) | Close Listening (player, operator, viewer, MCP, obs), Orrery, LiteLLM (prod) | `ssh deploy@prod-podcast` |
| DGX (`dgx-llm-1`) | vLLM, faster-whisper, pyannote, moss | `ssh dgx-llm-1` |

Plain `ssh homelab` is refused: there is no `Host homelab` alias, so the key flags
are required. On the mini, non-interactive shells lack `/usr/local/bin` on `PATH` —
call `/usr/local/bin/docker`.

## Databases

Run SQL through `docker exec` on the host, feeding the query on stdin (no quoting
trouble, no password needed — the containers trust local connections):

```sh
echo "select count(*) from website;" | ssh -i ~/.ssh/homelab_mini -o IdentitiesOnly=yes homelab \
  '/usr/local/bin/docker exec -i umami-db psql -U umami -d umami -tA'
```

| Host | Container | Engine | User / database |
|---|---|---|---|
| mini | `umami-db` | Postgres | `umami` / `umami` |
| mini | `glitchtip-postgres-1` | Postgres | `glitchtip` / `glitchtip` |
| mini | `langfuse-postgres-1` | Postgres | `postgres` / `postgres` |
| mini | `langfuse-clickhouse-1` | ClickHouse | env `CLICKHOUSE_USER` / `default` (see below) |
| mini | `litellm-postgres` | Postgres | `litellm` / `litellm` |
| VPS | `litellm-postgres` | Postgres | `litellm` / `litellm` |

ClickHouse reads its credentials from the container's own environment:

```sh
echo "select count() from system.tables where database='default'" | \
  ssh -i ~/.ssh/homelab_mini -o IdentitiesOnly=yes homelab \
  '/usr/local/bin/docker exec -i langfuse-clickhouse-1 sh -c "clickhouse-client --user \"\$CLICKHOUSE_USER\" --password \"\$CLICKHOUSE_PASSWORD\""'
```

Close Listening and Orrery have no database server: their data is files (next
section) and their APIs.

## Files — Close Listening app data

Inside the VPS app containers: `APP_DATA_DIR=/app/appdata` (users, magic links,
audit log, digest health) and `PODCAST_STACK_OUTPUT_DIR=/app/output` (the corpus).

```sh
ssh deploy@prod-podcast 'docker exec player-api-1 ls /app/appdata'
```

Homelab service data lives in Docker volumes inside the mini's VM; reach it with
`docker exec <container> …` the same way.

## APIs, UIs, logs and metrics

- **Service URLs on the tailnet** (Grafana, VictoriaMetrics/Logs/Traces, GlitchTip,
  Langfuse, LiteLLM, Umami): [observability endpoints](observability-endpoints.md);
  on the mini they are also on `127.0.0.1` (`docker ps` shows the ports).
- **Container logs without a shell:** VictoriaLogs has every container on the mini,
  the VPS and the DGX — query it in Grafana or at `/vlogs`.
- **Config variables for clients** (`${DGX_TAILNET_HOST}`, vLLM slots, …):
  [consuming homelab services](consuming-homelab-services.md).
- **Close Listening / Orrery APIs on the VPS** (checked 2026-10-10):

  | Service | Where it answers |
  |---|---|
  | player API | the VPS tailnet address, `:8099` (not `127.0.0.1`) |
  | operator API | not published — `docker exec operator-api-1 curl -s http://127.0.0.1:8000/api/health` |
  | player MCP `:8009`, Close Listening obs `:8848` | `127.0.0.1`; both answer `401` without a token |
  | operator viewer `:8093`, Orrery web `:8090` | `127.0.0.1` |
  | Orrery lab API `:8094`, Orrery MCP `:8091` | `127.0.0.1` (`/` is `404`; use their API paths) |

  `docker ps` on the VPS is the source of truth for ports.

## Rules

1. **Reads are always fine; write when the task needs it.** For one-off queries,
   `BEGIN READ ONLY; … ROLLBACK;` is the safe habit unless you mean to write.
2. **Never print secrets.** `docker exec <c> env` shows passwords and tokens — filter
   it (`| grep -E '^(POSTGRES_USER|POSTGRES_DB)='`) or don't run it.
3. **No development workloads on production engines.** Image builds, e2e stacks and
   test containers go to the dev engine on the mini (`devengine start`,
   `docker --context dev`) — [dev Docker engine](dev-docker-engine.md). A dev e2e
   container in the production VM preceded two outages.
4. **Destructive actions need the operator's per-item approval:** deleting rows,
   volumes or files, restarting or recreating production containers.
5. **Changes to the homelab repo or the mini's infrastructure** are the homelab
   session's job; ask it rather than editing `agentic-ai-homelab` from another project.

## Troubleshooting

- **`Permission denied (publickey)` on `ssh homelab`:** add `-i ~/.ssh/homelab_mini
  -o IdentitiesOnly=yes` (no alias exists).
- **`context "colima": context not found` as `claude`:** that account's private colima
  is retired — `docker context use dev`.
- **`permission denied … /var/run/docker.sock` as `claude`:** by design; production
  is reached through the operator account (first row of the table).
- **`docker: command not found` over ssh on the mini:** use `/usr/local/bin/docker`.
