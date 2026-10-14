# Homelab log standard — the Alloy label contract

**One standard for every log source in the homelab.** Wherever Grafana Alloy
ships logs to the mini's VictoriaLogs — the Mac mini, the DGX, the prod VPS, and
any app (orrery, podcast, player) — the logs MUST carry the fields below. This is
what makes "filter by host / app / env, and pivot log ↔ trace" work **identically
regardless of where the log came from**.

This file is the source of truth. Other repos (`podcast_scraper-infra`, app repos)
reference it by URL and apply the same snippet — they do not redefine it.

Canonical URL:
`https://github.com/chipi/agentic-ai-homelab/blob/main/infra/observability/LOG-STANDARD.md`

## The contract — required on every shipped log

| Field | Kind | Cardinality | Meaning | How it's set |
|---|---|---|---|---|
| `service` | stream label | low | **one deployable**, the same value as its OTel `service.name` (`player-api`, `podcast-pipeline`, `delivery-email`, `glitchtip-worker`) | a `loki.relabel` **after** the source: `<app>-<surface>`, else the container name without `-N`, else the file/journal `job` |
| `environment` | stream label | low | `prod`, `dev`, `ci` for the apps; `operations` for the fleets and the stack's self-monitoring | Alloy `external_labels` (env `HOMELAB_ENV`) / the pusher's own field |
| `instance` | stream label | low | the **host/box** (`homelab`, `dgx-llm-1`, `prod-podcast`) | Alloy `external_labels` (env `HOMELAB_INSTANCE`) |
| `cluster` | stream label | low | coarse group (`homelab`, `dgx`, `vps`) | Alloy `external_labels` (env `HOMELAB_CLUSTER`) |
| `env` | stream label | low | **old key**, same values as `environment` (until ADR-0010 phase C) | Alloy `external_labels` (env `HOMELAB_ENV`) |
| `app` | stream label | low | application (`podcast`, `player`, `orrery`, …) | set per drop-in (`loki.source.docker` labels), from the compose stack |
| `surface` | stream label | low | sub-part of an app: `api`, `web`, `app` | relabel from the container name / compose service (see below) |
| `container` | stream label | low-med | container name | `loki.source.docker` sets it |

> **Naming is the EXISTING convention, not invented here.** ADR-121's per-app
> drop-ins already use `app` (`podcast` = the operator stack, `player`, `orrery`)
> and `surface` (`api` / `web` / `app`). The standard adopts those names verbatim —
> do not rename to `operator`/`component`. `app=podcast,surface=api` is the
> operator API; `app=player,surface=api` is the player API — already separable.
>
> **`service` + `environment` are the cross-signal keys** (2026-10-14, ADR-0010 phase A):
> the values traces (`service.name`, `deployment.environment`) and metrics already carry,
> so one filter follows a service through logs, traces and metrics. `app`/`surface`/`env`
> stay until ADR-0010's phase C replaces them with `namespace`/`service`/`environment`
> declared once by each deployable.
| `trace_id` | **structured_metadata** | **high** | 32-hex W3C/Sentry trace id, for correlation | `loki.process` regex stage (below) |

**Why `trace_id` is structured_metadata, not a stream label:** trace ids are unique
per request (very high cardinality). As a *stream label* they would explode
VictoriaLogs' stream count. As *structured_metadata* they are a normal queryable
field (`trace_id:<id>`) with **no** stream-cardinality cost. This distinction is
mandatory — never promote `trace_id` (or any per-request id) to a stream label.

### Deriving `app` + `surface` (the "double API" case)

Both the operator and player stacks run a container named `api` from the same
image — the service name alone can't tell them apart. The **per-app drop-in**
(ADR-121) owns this: each drop-in has a scoped `loki.source.docker` that keeps
ONLY its own containers (a precise keep-filter, not a broad glob — that's what
prevents cross-app mislabel) and stamps `app` + `surface`. Pattern, as already
deployed in `podcast.alloy` / `player.alloy`:

```alloy
discovery.relabel "player" {
  targets = discovery.docker.app.targets
  rule {   // keep ONLY this app's containers
    source_labels = ["__meta_docker_container_name"]
    regex = "/(player-api-.*|player-learning-app-.*)"
    action = "keep"
  }
  rule {   // surface=api  for the API container
    source_labels = ["__meta_docker_container_name"]
    regex = "/player-api-.*"
    target_label = "surface"
    replacement = "api"
  }
  rule {   // surface=app  for the PWA
    source_labels = ["__meta_docker_container_name"]
    regex = "/player-learning-app-.*"
    target_label = "surface"
    replacement = "app"
  }
}
loki.source.docker "player" {
  targets = discovery.relabel.player.output
  forward_to = [loki.process.player_denoise.receiver]  // denoise -> homelab_std -> sink
  labels = { app = "player" }
}
```

Result: `app=podcast,surface=api` (operator API) vs `app=player,surface=api`
(player API) never merge. To carry `trace_id`, the drop-in's `loki.process`
(the denoise stage) runs the standard regex stage before forwarding to the sink.

### Severity

Log formats are heterogeneous (redis `*`, Caddy HTTP-status, Go `level=`, JSON),
so there is **no** single reliable `level` field. Severity is derived at query
time by **message pattern-match**, not a field:

- warnings+errors: `_msg:~"(?i)(error|err|warn|fatal|panic|exception|traceback|fail|critical)"`
- errors only: `_msg:~"(?i)(error|fatal|panic|exception|traceback|critical)"`

The `Logs — Overview` dashboard's **Severity** variable encodes exactly these.
If an app emits a clean structured `level`, great — keep it; but the portable
severity signal is the message pattern above.

## The reusable Alloy snippet (copy into every Alloy config)

Between your `loki.source.*` and `loki.write`, insert this processing stage and
point the source's `forward_to` at it (and it forwards to `loki.write`):

```alloy
// --- homelab log standard: service label (after the source, never on its targets) ---
// loki.source.docker / loki.source.file key their read positions by TARGET labels: a new
// target label makes every container a new target and re-reads its whole log as duplicates
// (the mini, 2026-10-14: 97,450 lines). So labels are added here, downstream of the source.
loki.relabel "naming" {
  rule {   // <app>-<surface> where a drop-in set both (= the OTel service.name)
    source_labels = ["app", "surface"]
    separator     = "-"
    regex         = "(.+-.+)"
    target_label  = "service"
  }
  rule {   // else the file/journal source's job (caddy, fail2ban, kernel)
    source_labels = ["service", "job"]
    separator     = ";"
    regex         = ";(.+)"
    target_label  = "service"
  }
  forward_to = [loki.process.homelab_std.receiver]
}
// (hosts without app/surface use the container name minus the replica suffix:
//  source_labels = ["container"], regex = "(.+?)(-[0-9]+)?")

// --- homelab log standard: extract trace_id -> structured_metadata ---
// Every shape the apps write: `trace_id=<id>` (OTel log correlation), `"trace_id":"<id>"`
// (JSON events), `trace=<id>` (access log, pipeline), W3C `00-<id>-…` traceparent and
// `sentry-trace`. A labelled prefix is required, so bare hashes and git shas never match.
// Identical to the Grafana VictoriaLogs derived field (which also skips Alloy's own
// `controller_id="" trace_id=` lines). RE2 syntax.
loki.process "homelab_std" {
  stage.match {
    selector = "{container!~\"alloy.*\"}"   // Alloy's own logs carry trace ids it never exports
    stage.regex {
      expression = "(?:trace_id[=\":\\s]+|trace=|00-|sentry-trace[=\":\\s]+)(?P<trace_id>[a-f0-9]{32})"
    }
    stage.structured_metadata {
      values = { trace_id = "" }
    }
  }
  forward_to = [loki.write.logs_sink.receiver]
}
```

And the sink carries the low-cardinality box/env labels:

```alloy
loki.write "logs_sink" {
  endpoint { url = sys.env("LOGS_WRITE_URL") }
  external_labels = {
    instance = coalesce(sys.env("HOMELAB_INSTANCE"), "unknown"),
    cluster  = coalesce(sys.env("HOMELAB_CLUSTER"), "default"),
    env         = coalesce(sys.env("HOMELAB_ENV"), "prod"),
    environment = coalesce(sys.env("HOMELAB_ENV"), "prod"),
  }
}
```

Set the three env vars per source in that Alloy's `.env`:

```sh
HOMELAB_INSTANCE=prod-podcast   # the box
HOMELAB_CLUSTER=vps             # coarse group
HOMELAB_ENV=prod                # prod | staging | dev | ci (never "production")
```

## App-level requirement (deeper correlation coverage)

The snippet correlates any log that carries the **trace id in the line**. For an app's
**own internal** log lines to correlate, the app must write the active trace id. Any of
these shapes is captured:

- `trace_id=<32hex>` — OTel log correlation (`OTEL_PYTHON_LOG_CORRELATION=true`)
- JSON `"trace_id":"<32hex>"` — structured events
- `trace=<32hex>` — access log / pipeline prefix
- W3C `traceparent` (`00-<32hex>-…`) or `sentry-trace` in a logged header

Where an app can't emit trace context, correlation is limited to its edge log —
that's an app-instrumentation gap, documented per app, not an infra bug.

## Staging vs prod

The **only** thing that separates staging from prod in the logs is the `environment`
label (and the old `env`, until ADR-0010 phase C). An app deployed to both MUST ship with `HOMELAB_ENV=staging` on the
staging box and `HOMELAB_ENV=prod` on prod. Without it, both collapse to one
stream and cannot be filtered apart (GlitchTip splits them by project; logs split
them by `environment`).

## Rollout checklist (per source)

1. Point every log source's `forward_to` at the `loki.relabel "naming"` step, which
   forwards to `loki.process "homelab_std"`. Never add labels on the source's targets.
2. Ensure `loki.write` carries `instance` + `cluster` + `environment` (+ `env`) external_labels.
3. Set `HOMELAB_INSTANCE` / `HOMELAB_CLUSTER` / `HOMELAB_ENV` in that Alloy's `.env`.
4. Validate before deploying: `alloy validate <file>` (a `config.d` set is the union of
   its files, so validate them concatenated). Then restart and check **three** things —
   the fields, the volume, and that no old lines were replayed:
   ```sh
   VL=http://homelab:9428/select/logsql/query
   curl -s $VL --data-urlencode 'query=_time:5m AND instance:<box> | stats by (service, environment) count()'
   curl -s $VL --data-urlencode 'query=_time:5m AND instance:<box> AND trace_id:* | stats count()'
   curl -s http://homelab:9428/metrics | grep ^vl_rows_ingested_total   # twice, 20 s apart: rate ≈ normal
   ```
5. The Grafana correlation + `Logs — Overview` filters then work with no per-source
   config — they key off these standard fields.

## Ownership & integration — who changes what, where

The single most confusing thing about this setup is that **one running Alloy on a
box is assembled from files owned by different repos**. Read this before changing
any prod log config — it's the map.

### The model: one node Alloy per box, config.d/ drop-ins (ADR-121)

Each box runs **one** Alloy. On the VPS its config is a **directory**,
`/opt/vps-observability/config.d/`, loaded as the union of its files. The mini and the
DGX each run a single `config.alloy`, bind-mounted from the box's checkout of this repo.

```
/opt/vps-observability/config.d/      (prod VPS)
  base.alloy     <- shared: discovery.docker "app", loki.relabel "naming", the
                    homelab_std trace_id stage, loki.write "logs_sink" (instance/cluster/
                    environment), host journal + Caddy + fail2ban + app-event file sources
  selfmon.alloy  <- Alloy's own metrics
  operator.alloy <- the operator stack's containers + app/surface labels
  player.alloy   <- the player stack's containers + app/surface labels
  litellm.alloy  <- the LiteLLM gateway + its Postgres
  orrery.alloy   <- orrery's containers + data-refresh file; inlines its own trace stage and
                    naming relabel so it deploys independently of base.alloy
```

A **drop-in** keeps ONLY its own containers (a precise keep-filter), stamps
`app`/`surface`, and forwards through base's `loki.relabel "naming"` to the sink. It never
redefines the sink or touches another app's sources. Alloy hot-reloads on
`docker kill -s HUP alloy`.

### Who owns / deploys each piece

| Piece | Source of truth | How it reaches the box |
|---|---|---|
| prod `base.alloy`, `selfmon.alloy` | `podcast_scraper` · `infra/observability/` | podcast `deploy-config.yml` (scp, atomic rename, HUP) |
| prod `operator.alloy` / `player.alloy` / `litellm.alloy` | `podcast_scraper` · `infra/observability/` | `deploy-operator.sh` / `deploy-player.sh` / `deploy-litellm.sh` (cp + HUP) |
| prod `orrery.alloy` | `orrery` · `ops/observability/orrery.alloy` | orrery `ops/deploy_stack.sh` (cp + HUP) |
| mirror of the prod files | this repo · `hosts/prod-podcast/config.d/` | nothing — a copy; refresh it after the podcast deploy |
| mini `alloy-homelab` | this repo · `hosts/homelab/config.alloy` | `git pull` + `docker restart alloy-homelab` on the mini |
| DGX `alloy` | this repo · `config.alloy` | `git pull` + restart on the DGX |
| Grafana correlation + dashboards | this repo · `backend/grafana/` | `git pull` on the mini (file provisioning) |

### Rollout status (ADR-0010 phase A, 2026-10-14)

| Source | `service` + `environment` | Current trace_id regex |
|---|---|---|
| Mac mini | deployed, verified (800ae69) | deployed |
| DGX | committed (1dd7e67), **not deployed** — with the DGX converge, plus `HOMELAB_ENV=prod` in its `.env` (says `production`) | committed, not deployed |
| prod `base.alloy` + podcast drop-ins | podcast_scraper local commit, ships with the next deploy; live prod has **no** environment key today | **not deployed** (checked on the box 2026-10-14) — next deploy |
| prod `orrery.alloy` | orrery local commit, ships with orrery's next deploy | orrery keeps the traceparent-only pattern (it writes no trace ids) |
| ops events (podcast `emit_ops_event.sh`) | podcast_scraper local commit | — |
| `ci-ops-poller`, signal-fleet inbox | deployed (6dcf540) | — |
| fleetd | already `service` + `environment` | — |
| dev pushes (`dev_push.py`) | already; service names fixed in a podcast_scraper local commit | — |
