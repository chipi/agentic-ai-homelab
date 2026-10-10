# Agent operations handbook — every homelab service, how to read and change it

## How to use this page

Hand this page to any agent that has to look inside or operate the operator's
products and the homelab: Grafana and the Victoria stack, Umami, GlitchTip,
Langfuse, LiteLLM, delivery, Close Listening, Orrery, the DGX. Each section is
**get in → read → change → careful**. Every recipe here was run against the live
systems on 2026-10-10 (writes against throwaway `zz-handbook-test` objects that were
then removed).

**The loop:** when a task isn't covered, do it, then add the working recipe here
(or ask the homelab session to). This page only gets better if it's kept current.

**No new access is needed.** Everything below uses access that already exists:
the operator's SSH keys, and credentials already in the services' own `.env` files.
Do not create logins, publish ports or change groups to "get access".

## 0. Getting onto each host

| Host | What runs there | Command (from the operator's laptop) |
|---|---|---|
| Mac mini (`homelab`) | Grafana, Victoria{Metrics,Logs,Traces}, Umami, GlitchTip, Langfuse, LiteLLM, delivery | `ssh -i ~/.ssh/homelab_mini -o IdentitiesOnly=yes homelab` |
| Mac mini, `claude` account | where agents on the mini run; dev engine only | `ssh homelab-claude` |
| Prod VPS (`prod-podcast`) | Close Listening (player, operator, viewer, MCP, obs), Orrery, LiteLLM (prod) | `ssh deploy@prod-podcast` |
| DGX (`dgx-llm-1`) | vLLM (prod + translate), faster-whisper, pyannote, moss | `ssh dgx-llm-1` |

- Plain `ssh homelab` is refused: no `Host homelab` alias exists; the key flags are required.
- On the mini, non-interactive shells lack `/usr/local/bin` on `PATH`: call
  `/usr/local/bin/docker`.
- **Run multi-line recipes as a script file on the host** (`scp` it, `bash file.sh`),
  not as an inline heredoc piped through `ssh`. Nested quoting through `ssh` silently
  corrupts JSON bodies; the same commands work from a file.
- Recipes below run **on the mini** unless marked otherwise. From the laptop, every
  web service also has its own tailnet name (`https://<name>.tail6d0ed4.ts.net`:
  `grafana`, `vm`, `vlogs`, `vtraces`, `litellm`, `langfuse`, `umami`, `glitchtip`,
  `hub`, `evals`) — see [observability endpoints](observability-endpoints.md).

**Credentials** — load them from the file, never print them, never copy them anywhere:

| Service | Load on the mini with | Gives you |
|---|---|---|
| Grafana | `set -a; . ~/agentic-ai-homelab/infra/observability/backend/.env; set +a` | `GRAFANA_ADMIN_USER`, `GRAFANA_ADMIN_PASSWORD` |
| Umami | `set -a; . ~/umami/.env; set +a` (note: `~/umami`, not the repo) | `UMAMI_ADMIN_PASSWORD` (user `admin`) |
| GlitchTip (read) | `set -a; . ~/signal-fleet/fleet-gateway.env; set +a` | `GLITCHTIP_TOKEN` (read-only) |
| GlitchTip (write) | `set -a; . ~/agentic-ai-homelab/infra/glitchtip/.env; set +a` | `DJANGO_SUPERUSER_EMAIL`, `DJANGO_SUPERUSER_PASSWORD` |
| Langfuse | `set -a; . ~/signal-fleet/fleet-gateway.env; set +a` | `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY` (project `agents`) |
| LiteLLM (mini) | `set -a; . ~/agentic-ai-homelab/infra/litellm/.env; set +a` | `LITELLM_MASTER_KEY` |
| LiteLLM (VPS) | inside the `litellm` container's env | `LITELLM_MASTER_KEY` |
| DGX vLLM | `docker exec vllm-prod-vllm printenv VLLM_API_KEY` (or `vllm-translate`) | the server's API key |
| Databases | none — `docker exec … psql` trusts local connections | — |

## 1. Grafana (`:3000` on the mini · `https://grafana.tail6d0ed4.ts.net`)

```sh
set -a; . ~/agentic-ai-homelab/infra/observability/backend/.env; set +a
G=http://127.0.0.1:3000; A="$GRAFANA_ADMIN_USER:$GRAFANA_ADMIN_PASSWORD"

curl -s $G/api/health                                            # health + version
# Firing / pending / broken alert rules:
curl -s -u "$A" $G/api/prometheus/grafana/api/v1/rules | python3 -c '
import sys,json
for g in json.load(sys.stdin)["data"]["groups"]:
  for r in g["rules"]:
    if r["state"]!="inactive" or r["health"]!="ok": print(r["state"], r["health"], r["name"])'
# State history of one rule (from/to in SECONDS; time column is MICROseconds):
curl -s -u "$A" "$G/api/v1/rules/history?ruleUID=<uid>&from=$(( $(date +%s)-3*86400 ))&to=$(date +%s)" | python3 -c '
import sys,json,datetime as dt
t,_,prev,nxt,_=json.load(sys.stdin)["data"]["values"]
for i in range(len(t)): print(dt.datetime.utcfromtimestamp(t[i]/1e6).isoformat(timespec="seconds")+"Z", prev[i], "->", nxt[i])'
curl -s -u "$A" "$G/api/search?type=dash-db"                   # dashboards
curl -s -u "$A" $G/api/datasources                             # victoriametrics, victorialogs, victoriatraces-*, litellm-pg
curl -s -u "$A" $G/api/v1/provisioning/contact-points          # where alerts go
```

**Silence an alert** (e.g. during planned work) and remove the silence:

```sh
SID=$(curl -s -u "$A" -H 'Content-Type: application/json' -X POST $G/api/alertmanager/grafana/api/v2/silences \
  -d '{"matchers":[{"name":"alertname","value":"<exact alert title>","isRegex":false,"isEqual":true}],
       "startsAt":"'"$(date -u +%Y-%m-%dT%H:%M:%SZ)"'","endsAt":"'"$(date -u -v+1H +%Y-%m-%dT%H:%M:%SZ)"'",
       "createdBy":"<agent>","comment":"<why>"}' | python3 -c 'import sys,json;print(json.load(sys.stdin)["silenceID"])')
curl -s -u "$A" -X DELETE $G/api/alertmanager/grafana/api/v2/silence/$SID
```

**Change alert rules or dashboards — in the repo, not the UI.** Rules live in
`infra/observability/backend/grafana/provisioning/alerting/rules.yaml`, dashboards in
`infra/observability/backend/grafana/dashboards/`. Edit, push, `git pull` on the mini,
then `curl -s -u "$A" -X POST $G/api/admin/provisioning/alerting/reload`. Check drift
with the `obs-boot` skill (`drift: 0`). UI edits to provisioned dashboards are
allowed but are overwritten the next time the file changes.

**Careful:** a rule change can mute a real outage. Prove a rule change on history
first (`infra/observability/rules-drift/rule_history_replay.py`, skill
`replay-proven-fix`).

## 2. VictoriaMetrics (`:8428` · `https://vm.tail6d0ed4.ts.net`)

```sh
VM=http://127.0.0.1:8428
curl -s $VM/api/v1/query --data-urlencode 'query=up{instance="dgx-llm-1"}'
curl -s $VM/api/v1/query_range --data-urlencode 'query=sum(rate(delivery_sent_total[1h]))' \
  --data-urlencode "start=$(( $(date +%s)-3600 ))" --data-urlencode "end=$(date +%s)" --data-urlencode step=15m
curl -s $VM/api/v1/label/__name__/values --data-urlencode 'match[]={__name__=~"delivery_.*"}'   # metric names
curl -s $VM/api/v1/label/instance/values                                                       # hosts
```

Push a metric, and delete a series (destructive — exact matcher, never a broad regex):

```sh
printf 'my_metric{source="x"} 42\n' | curl -s --data-binary @- $VM/api/v1/import/prometheus
curl -s $VM/api/v1/admin/tsdb/delete_series --data-urlencode 'match[]=my_metric{source="x"}'
```

**Careful:** new samples are invisible to queries for ~30 s (`search.latencyOffset`);
wait before reading back. Instances: `homelab`, `prod-podcast`, `dgx-llm-1`.

## 3. VictoriaLogs (`:9428` · `https://vlogs.tail6d0ed4.ts.net`)

Every container on the mini, the VPS and the DGX ships here (fields: `instance`,
`container`, `cluster`, `env`).

```sh
VL=http://127.0.0.1:9428
curl -s --get $VL/select/logsql/query --data-urlencode 'query=_time:1h container:delivery-email' --data-urlencode limit=20
curl -s --get $VL/select/logsql/query --data-urlencode 'query=_time:24h instance:prod-podcast ERROR | stats by (container) count() n'
curl -s --get $VL/select/logsql/field_names --data-urlencode 'query=_time:15m container:umami'
```

Write a log line:

```sh
curl -s -H 'Content-Type: application/stream+json' \
  --data-binary '{"_msg":"my message","source":"x"}' "$VL/insert/jsonline?_stream_fields=source"
```

**Careful:** without that `Content-Type` header VictoriaLogs answers **200 and drops the
line silently**. Deleting logs is **disabled** on this instance (`-delete.enable` is not
set; logs expire after 30 days). Turning deletion on is a config change for the operator.

## 4. VictoriaTraces (`:10428` · `https://vtraces.tail6d0ed4.ts.net`)

```sh
VT=http://127.0.0.1:10428
curl -s $VT/select/jaeger/api/services
curl -s $VT/select/jaeger/api/services/delivery-worker/operations
curl -s --get $VT/select/jaeger/api/traces --data-urlencode service=delivery-worker \
  --data-urlencode operation=delivery.send --data-urlencode lookback=24h --data-urlencode limit=5
curl -s $VT/select/jaeger/api/traces/<traceID>
```

Traces cannot be deleted; they expire with retention. New traces are queryable after ~30 s.

## 5. Sending telemetry in (OTLP, remote-write, Loki push)

| Signal | Endpoint (on the mini; tailnet names work too) | Format |
|---|---|---|
| Traces | `http://homelab:10428/insert/opentelemetry/v1/traces` | OTLP/HTTP, protobuf or JSON |
| Metrics | `http://homelab:8428/api/v1/write` | Prometheus remote-write (Alloy) |
| Logs | `http://homelab:9428/insert/loki/api/v1/push` | Loki push (Alloy) |

Apps set `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT` to the traces URL and a `service.name`;
host logs and metrics go through the Alloy collector on each host (configs under
`infra/observability/`). A minimal OTLP/JSON trace (fields: `resourceSpans` →
`resource.attributes[service.name]` → `scopeSpans[].spans[]` with hex `traceId` /
`spanId` and nanosecond start/end) posted with `Content-Type: application/json`
returns 200 and appears in VictoriaTraces.

## 6. Umami (`:3001` · `https://umami.tail6d0ed4.ts.net` · tracker `https://analytics.closelistening.app/script.js`)

**API** (run from a script file on the mini):

```sh
set -a; . ~/umami/.env; set +a
U=http://127.0.0.1:3001
TOK=$(curl -s -H 'Content-Type: application/json' -d "{\"username\":\"admin\",\"password\":\"$UMAMI_ADMIN_PASSWORD\"}" \
  $U/api/auth/login | python3 -c 'import sys,json;print(json.load(sys.stdin)["token"])')
H="Authorization: Bearer $TOK"
curl -s -H "$H" "$U/api/websites?pageSize=50"                              # id, name, domain of every site
END=$(( $(date +%s)*1000 )); START=$(( END - 7*86400*1000 ))           # ms timestamps
curl -s -H "$H" "$U/api/websites/<id>/stats?startAt=$START&endAt=$END"    # pageviews, visitors, visits, bounces, totaltime (+ comparison)
curl -s -H "$H" "$U/api/websites/<id>/metrics?startAt=$START&endAt=$END&type=path&limit=20"  # also: referrer, browser, country, event
curl -s -H "$H" "$U/api/websites/<id>/pageviews?startAt=$START&endAt=$END&unit=day&timezone=UTC"
# New website → put its id in the app's VITE_UMAMI_WEBSITE_ID
# (with VITE_UMAMI_SRC=https://analytics.closelistening.app/script.js):
curl -s -H "$H" -H 'Content-Type: application/json' -d '{"name":"<name>","domain":"<domain>"}' $U/api/websites
curl -s -H "$H" -X DELETE $U/api/websites/<id>                          # removes the site and its data
```

`metrics` takes `type=path` (older docs say `url`, which now returns 400).

**SQL** for anything the API doesn't cover (event-level queries, bulk deletes):

```sh
q(){ /usr/local/bin/docker exec -i umami-db psql -U umami -d umami -P pager=off; }
# Page views per site per day (event_type 1 = page view, 2 = custom event):
echo "select w.name, date_trunc('day', e.created_at)::date day, count(*) from website_event e join website w using (website_id)
      where e.event_type=1 and e.created_at > now()-interval '7 days' group by 1,2 order by 2 desc,1;" | q
echo "select event_name, count(*) from website_event e join website w using (website_id)
      where w.name='Player' and event_type=2 group by 1 order by 2 desc;" | q
```

**Delete data (e.g. test traffic) — preview, delete in a transaction, check, then commit:**

```sh
q <<'SQL'
begin;
select count(*) from website_event where hostname in ('127.0.0.1','localhost')
  and website_id = (select website_id from website where name='Player');
delete from website_event where hostname in ('127.0.0.1','localhost')
  and website_id = (select website_id from website where name='Player');
-- read the DELETE count; type commit only if it matches the preview, else rollback
rollback;
SQL
```

**Careful:** deleting analytics data is irreversible and needs the operator's go for
that specific scope. `hostname` is the page's host; dev traffic mostly lands on the
"Player (dev)" website, not "Player".

## 7. GlitchTip (`:8090` · `https://glitchtip.tail6d0ed4.ts.net` · org `homelab`)

**Read** with the fleet's read-only token:

```sh
set -a; . ~/signal-fleet/fleet-gateway.env; set +a
GT=http://127.0.0.1:8090; H="Authorization: Bearer $GLITCHTIP_TOKEN"
curl -s -H "$H" $GT/api/0/organizations/homelab/projects/
curl -s -H "$H" "$GT/api/0/organizations/homelab/issues/?query=is:unresolved&limit=25"
curl -s -H "$H" "$GT/api/0/issues/<id>/"                 # one issue; events under /events/
```

**Write** (resolve, ignore, delete issues; create projects) with the superuser session
— the token above is read-only (writes return 403). Save as a script and run it:

```sh
set -a; . ~/agentic-ai-homelab/infra/glitchtip/.env; set +a
GT=http://127.0.0.1:8090; CJ=$(mktemp)
curl -s -c $CJ -b $CJ -o /dev/null $GT/_allauth/browser/v1/config; CSRF=$(awk '$6=="csrftoken"{print $7}' $CJ)
curl -s -c $CJ -b $CJ -o /dev/null -H 'Content-Type: application/json' -H "X-CSRFToken: $CSRF" -H "Referer: $GT/" \
  -d "{\"email\":\"$DJANGO_SUPERUSER_EMAIL\",\"password\":\"$DJANGO_SUPERUSER_PASSWORD\"}" $GT/_allauth/browser/v1/auth/login
CSRF=$(awk '$6=="csrftoken"{print $7}' $CJ)
S(){ curl -s -c $CJ -b $CJ -H "X-CSRFToken: $CSRF" -H "Referer: $GT/" -H 'Content-Type: application/json' "$@"; }

S -X PUT -d '{"status":"resolved"}' "$GT/api/0/organizations/homelab/issues/?id=<id>"   # or "ignored" / "unresolved"
S -X DELETE "$GT/api/0/organizations/homelab/issues/?id=<id>"
# New project (projects live under a team; the org had none on 2026-10-10 — create one once):
S -d '{"slug":"<team>"}' $GT/api/0/organizations/homelab/teams/
S -d '{"name":"<project>","platform":"python"}' $GT/api/0/teams/homelab/<team>/projects/
S $GT/api/0/projects/homelab/<project>/keys/            # → dsn.public for the app's SENTRY_DSN
rm -f $CJ
```

Send a test error the way apps do (Sentry SDK, from inside the GlitchTip container):

```sh
/usr/local/bin/docker exec -e DSN="http://<public key>@127.0.0.1:8080/<project id>" glitchtip-web-1 \
  python -c "import os,sentry_sdk;sentry_sdk.init(dsn=os.environ['DSN']);sentry_sdk.capture_message('test',level='error');sentry_sdk.flush(10)"
```

**Careful:** issue delete returns 200 but the issue stays readable for a while
(deletion is deferred). Ids are numeric; short ids (`PLAYER-1D`) are for humans.

## 8. Langfuse (`:4000` · `https://langfuse.tail6d0ed4.ts.net`)

```sh
set -a; . ~/signal-fleet/fleet-gateway.env; set +a
LF=http://127.0.0.1:4000; A="$LANGFUSE_PUBLIC_KEY:$LANGFUSE_SECRET_KEY"
curl -s -u "$A" $LF/api/public/projects                        # → project "agents"
curl -s -u "$A" "$LF/api/public/traces?limit=20"               # newest traces
curl -s -u "$A" "$LF/api/public/traces/<traceId>"
curl -s -u "$A" -X DELETE "$LF/api/public/traces/<traceId>"    # deletion is asynchronous
```

Write a trace (run from a script file):
`POST $LF/api/public/ingestion` with `{"batch":[{"id":"<event id>","type":"trace-create","timestamp":"<ISO>","body":{"id":"<trace id>","name":"<name>"}}]}` → `207` with per-event `201`; readable after ~15 s.

Direct database access: `langfuse-postgres-1` (`psql -U postgres -d postgres`) and
`langfuse-clickhouse-1`:

```sh
echo "select count() from system.tables where database='default'" | /usr/local/bin/docker exec -i langfuse-clickhouse-1 \
  sh -c 'clickhouse-client --user "$CLICKHOUSE_USER" --password "$CLICKHOUSE_PASSWORD"'
```

**Careful:** these keys only see project `agents`. Other projects need their own keys
(Langfuse UI → project settings).

## 9. LiteLLM (mini `:4001` · `https://litellm.tail6d0ed4.ts.net` · VPS `:4001`)

```sh
set -a; . ~/agentic-ai-homelab/infra/litellm/.env; set +a
LL=http://127.0.0.1:4001; M="Authorization: Bearer $LITELLM_MASTER_KEY"
curl -s $LL/health/liveliness
curl -s -H "$M" $LL/v1/models                                  # model aliases
# A scoped virtual key (expires, budget-capped), its info, and deletion:
curl -s -H "$M" -H 'Content-Type: application/json' -d '{"key_alias":"<name>","duration":"7d","max_budget":5}' $LL/key/generate
curl -s -H "$M" "$LL/key/info?key=<sk-…>"
curl -s -H "$M" -H 'Content-Type: application/json' -d '{"keys":["<sk-…>"]}' $LL/key/delete
```

Spend lives in `litellm-postgres` (`psql -U litellm -d litellm`). On the VPS, the same
API runs in container `litellm` (master key in its env); run the calls from the VPS.

**Careful:** never hand out the master key; give agents and apps a virtual key with
`duration` and `max_budget`.

## 10. Delivery (email + push workers on the mini)

- Health: `/usr/local/bin/docker ps | grep delivery` (`delivery-email`, `-push`, `-events`, all `healthy`).
- Queue and sends (VictoriaMetrics): `delivery_batch_pending`, `delivery_sent_total`,
  `delivery_attempts_total`, `delivery_send_seconds_*`, `delivery_events_cursor_age_seconds`.
- Logs: `container:delivery-email` (or `-push`, `-events`) in VictoriaLogs.
- Real test send (sends a REAL email): `infra/delivery/README.md` → "Deployed-service e2e".
- Pause all sends: `cd ~/agentic-ai-homelab/infra/delivery && /usr/local/bin/docker compose stop` (outbox keeps the backlog).

## 11. Close Listening (prod VPS)

| Service | Where it answers |
|---|---|
| player API | the VPS tailnet address `:8099` only (not `127.0.0.1`) |
| operator API | not published — `docker exec operator-api-1 curl -s http://127.0.0.1:8000/api/health` |
| player MCP `:8009`, obs `:8848` | `127.0.0.1`; `401` without a token |
| operator viewer `:8093`, compose viewer `:8080` | `127.0.0.1` |

App data are files inside the API containers: `APP_DATA_DIR=/app/appdata` and the
corpus at `PODCAST_STACK_OUTPUT_DIR=/app/output`. Under `/app/appdata`: `users/<id>/`
(per-user JSON/JSONL: `library.json`, `playback.json`, `listening_daily.json`,
`comms.json`, `push_subscriptions.json`, `*_events.jsonl` …), `outbox/`, `oauth_*.json`
(each with a `.lock`), `magic_link_*`, `audit.jsonl`, `digest_health.json`.

```sh
ssh deploy@prod-podcast 'docker exec player-api-1 ls /app/appdata/users'
ssh deploy@prod-podcast 'docker exec player-api-1 cat /app/appdata/users/<id>/library.json'
```

**Careful — writes:** prefer the app's API. If a file must be edited by hand, copy it
first (`cp f f.bak-<date>`), keep it valid JSON, and respect the `.lock` files: the app
holds those locks while writing (a stuck lock already showed up as `PLAYER-1D`).

## 12. Orrery (prod VPS)

`orrery-web` `:8090` (public), `orrery-lab-api` `:8094`, `orrery-mcp` `:8091`, all on the
VPS (`127.0.0.1`; `/` returns 404 on the APIs — use their paths). Analytics: Umami
websites "Orrery" and "Orrery Staging"; errors: GlitchTip projects `orrery`, `orrery-prod`.

## 13. DGX services

```sh
ssh dgx-llm-1 '~/bin/gpu-mode-swap.sh status 2>&1'     # which vLLMs own the GPU
```

| Port | Service | Notes |
|---|---|---|
| `:8000` | faster-whisper (speaches) | `/health`; transcription at `/v1/audio/transcriptions` |
| `:8001` | pyannote | `/health` |
| `:8003` | vLLM (prod serving) | models `NVFP4/Qwen3-30B-A3B-Instruct-2507-FP4`, alias `autoresearch` |
| `:8004` | moss | `/v1/models` |
| `:8005` | vLLM (translate) | models `google/translategemma-12b-it`, alias `translate` |

Both vLLMs need their API key (compose: `infra/vllm/{prod-vllm,translate}/` in the DGX's checkout):

```sh
ssh dgx-llm-1 'K=$(docker exec vllm-prod-vllm printenv VLLM_API_KEY); curl -s -H "Authorization: Bearer $K" http://127.0.0.1:8003/v1/models'
```

**Careful:** switching GPU modes or restarting a model server interrupts the pipeline —
use the `gpu-mode` skill and ask first. Never unload or kill a whisper request mid-flight:
on 2026-10-09 an interrupted request plus an unload hung the server until a restart.

## 14. Docker engines and databases

- **Production engines** (mini, VPS, DGX) are for operating: logs, `ps`, `exec`,
  queries, deploys when asked. **Never** development workloads there (image builds,
  e2e stacks, test containers) — those go to the mini's dev engine:
  `devengine start`, `docker --context dev …`, `devengine stop`
  ([dev Docker engine](dev-docker-engine.md)). A dev container in the production VM
  preceded two outages.
- Databases, all via `docker exec` on their host, SQL on stdin:

| Host | Container | Engine | User / database |
|---|---|---|---|
| mini | `umami-db` | Postgres | `umami` / `umami` |
| mini | `glitchtip-postgres-1` | Postgres | `glitchtip` / `glitchtip` |
| mini | `langfuse-postgres-1` | Postgres | `postgres` / `postgres` |
| mini | `langfuse-clickhouse-1` | ClickHouse | env `CLICKHOUSE_USER` / `default` |
| mini | `litellm-postgres` | Postgres | `litellm` / `litellm` |
| VPS | `litellm-postgres` | Postgres | `litellm` / `litellm` |

## Rules

1. Reads are always fine; write when the task needs it. For one-off SQL,
   `BEGIN READ ONLY; … ROLLBACK;` is the safe default.
2. Never print secrets (`docker exec <c> env` shows passwords — filter it).
3. Destructive actions (deleting rows, issues, websites, series, files; restarting or
   recreating production containers) need the operator's go for that specific scope.
4. Test writes on a throwaway object first (name it `zz-…`), and remove it after.
5. Changes to `agentic-ai-homelab` or the mini's infrastructure are the homelab
   session's job; ask it rather than editing that repo from another project.

## Known gaps (2026-10-10)

- **GlitchTip's fleet token is read-only**; writes use the superuser session (section 7).
- **VictoriaLogs deletion is disabled** (section 3).

## Troubleshooting

- `Permission denied (publickey)` on `ssh homelab` → add `-i ~/.ssh/homelab_mini -o IdentitiesOnly=yes`.
- `context "colima": context not found` as `claude` → `docker context use dev`.
- `permission denied … /var/run/docker.sock` as `claude` → by design; production goes
  through the operator account (section 0).
- `docker: command not found` over ssh on the mini → `/usr/local/bin/docker`.
- A JSON write returns `Invalid JSON` / `Cannot parse request body` when sent through an
  `ssh` heredoc → run it from a script file on the host.
