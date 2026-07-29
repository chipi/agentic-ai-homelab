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
| `instance` | stream label | low | the **host/box** (`homelab`, `dgx-llm-1`, `prod-podcast`) | Alloy `external_labels` (env `HOMELAB_INSTANCE`) |
| `cluster` | stream label | low | coarse group (`homelab`, `dgx`, `vps`) | Alloy `external_labels` (env `HOMELAB_CLUSTER`) |
| `env` | stream label | low | deploy env (`prod`, `staging`, `dev`, `ci`) | Alloy `external_labels` (env `HOMELAB_ENV`) |
| `app` | stream label | low | application (`podcast`, `player`, `orrery`, …) | set per drop-in (`loki.source.docker` labels), from the compose stack |
| `surface` | stream label | low | sub-part of an app: `api`, `web`, `app` | relabel from the container name / compose service (see below) |
| `container` | stream label | low-med | container name | `loki.source.docker` sets it |

> **Naming is the EXISTING convention, not invented here.** ADR-121's per-app
> drop-ins already use `app` (`podcast` = the operator stack, `player`, `orrery`)
> and `surface` (`api` / `web` / `app`). The standard adopts those names verbatim —
> do not rename to `operator`/`component`. `app=podcast,surface=api` is the
> operator API; `app=player,surface=api` is the player API — already separable.
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
// --- homelab log standard: extract trace_id -> structured_metadata ---
// Captures the 32-hex trace id from W3C `traceparent` (00-<trace>-<span>-flags)
// and Sentry `sentry-trace` (<trace>-<span>-sampled). The trailing -<16hex span>
// makes it unambiguous, so it does NOT false-match bare hashes, git shas, or
// Alloy's own internal `trace_id=<hex>` graph logs (no -span suffix). RE2 syntax.
loki.process "homelab_std" {
  stage.regex {
    expression = "(?:00-)?(?P<trace_id>[a-f0-9]{32})-[a-f0-9]{16}"
  }
  // promote the capture to structured_metadata ONLY when it matched (else empty
  // and harmless — infra logs simply carry no trace_id).
  stage.structured_metadata {
    values = { trace_id = "" }
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
    env      = coalesce(sys.env("HOMELAB_ENV"), "prod"),
  }
}
```

Set the three env vars per source in that Alloy's `.env`:

```sh
HOMELAB_INSTANCE=prod-podcast   # the box
HOMELAB_CLUSTER=vps             # coarse group
HOMELAB_ENV=prod                # prod | staging | dev | ci
```

## App-level requirement (deeper correlation coverage)

The snippet correlates any log that carries the **trace context in the line** —
edge/Caddy request logs (traceparent) and Sentry-instrumented app logs
(sentry-trace). For an app's **own internal** log lines to correlate, the app must
emit the active trace id into its logs. Prescribed shape (either is captured if it
carries the `-<span>` tail, or add the app to a `trace_id`-key stage):

- structured: `... trace_id=<32hex>-<16hex> ...` or a JSON `"trace_id":"<32hex>"`
- or propagate `traceparent` so the edge log already carries it (default: covered)

Where an app can't emit trace context, correlation is limited to its edge log —
that's an app-instrumentation gap, documented per app, not an infra bug.

## Staging vs prod

The **only** thing that separates staging from prod in the logs is the `env`
label. An app deployed to both MUST ship with `HOMELAB_ENV=staging` on the
staging box and `HOMELAB_ENV=prod` on prod. Without it, both collapse to one
stream and cannot be filtered apart (GlitchTip splits them by project; logs split
them by `env`).

## Rollout checklist (per source)

1. Add the `loki.process "homelab_std"` stage; repoint the source's `forward_to`.
2. Ensure `loki.write` carries `instance` + `cluster` + `env` external_labels.
3. Set `HOMELAB_INSTANCE` / `HOMELAB_CLUSTER` / `HOMELAB_ENV` in that Alloy's `.env`.
4. Restart Alloy; confirm `field_values env` and `field_values trace_id` populate:
   ```sh
   curl -sG "http://homelab:9428/select/logsql/query" \
     --data-urlencode 'query=<instance>:* _time:15m trace_id:* | stats count()'
   ```
5. The Grafana correlation + `Logs — Overview` filters then work with no per-source
   config — they key off these standard fields.

## Ownership & integration — who changes what, where

The single most confusing thing about this setup is that **one running Alloy on a
box is assembled from files owned by different repos**. Read this before changing
any prod log config — it's the map.

### The model: one node Alloy per box, config.d/ drop-ins (ADR-121)

Each box runs **one** Alloy. Its config is a **directory** (`/etc/alloy/config.d/`
on the mini/DGX, `/opt/vps-observability/config.d/` on the VPS) that Alloy loads
as a union of files:

```
config.d/
  base.alloy      <- INFRA owns. Shared router: discovery.docker "app",
                     loki.write "logs_sink" (sets instance/cluster/env +
                     the homelab_std trace_id stage), host journal + Caddy sources.
  podcast.alloy   <- the OPERATOR app owns. Its scoped loki.source.docker + app/surface labels.
  player.alloy    <- the PLAYER app owns. Same shape, its own containers.
  orrery.alloy    <- ORRERY owns.
```

A **drop-in** (`<app>.alloy`) is a small file an app owns that *references* base's
shared components (`discovery.docker "app"`, `loki.write "logs_sink"`, and the
shared `loki.process "homelab_std"`) and adds ONLY its own `loki.source.docker`
with a precise keep-filter + `app`/`surface` labels. It never redefines the sink
or touches another app's sources. Alloy hot-reloads on `docker kill -s HUP alloy`.

### Who owns / deploys each piece

| Piece | Owning repo · path | How it reaches the box | Change it when… |
|---|---|---|---|
| **base.alloy** (VPS) | `agentic-ai-homelab` · `infra/observability/hosts/prod-podcast/config.d/base.alloy` | infra deploy (repo-tracked; **not** the app `deploy.sh`) | changing the sink, shared labels (`env`), Caddy/journal sources, the `homelab_std` trace_id stage |
| **podcast.alloy** (operator) | `podcast_scraper-infra` · `infra/observability/podcast.alloy` | operator `deploy.sh` → `cp` into `config.d/` + HUP | changing what operator container logs ship / their `app`/`surface`/denoise |
| **player.alloy** | `podcast_scraper-infra` · `infra/observability/player.alloy` | player deploy → `cp` + HUP | same, for the player stack |
| **orrery.alloy / orrery agent** | `orrery` repo · `ops/observability/` | orrery's own deploy | orrery uses **grafana-agent**, not Alloy — different syntax; match the intent, not the snippet |
| **mini `alloy-homelab`** | `agentic-ai-homelab` · `infra/observability/hosts/homelab/config.alloy` | `git pull` + restart on the mini | mini host/container logs |
| **DGX `alloy`** | `agentic-ai-homelab` · `infra/observability/config.alloy` | `git pull` + restart on the DGX | DGX host/container logs |
| **Grafana correlation + dashboards** | `agentic-ai-homelab` · `infra/observability/backend/grafana/` | `git pull` + Grafana restart/hot-reload on the mini | derivedFields, tracesToLogs, `Logs — Overview` filters |

**Rule of thumb:** shared/edge/sink concerns (env, trace_id stage, Caddy) → infra's
`base.alloy` (agentic). Per-app container logs + their labels → that app's drop-in
(its own repo). The dashboards + correlation that *consume* these fields → agentic.

### Rollout status

| Source | Standard applied? |
|---|---|
| Mac mini (`homelab`) | ✅ deployed + verified (env, trace_id stage) |
| DGX (`dgx-llm-1`) | ✅ deployed + verified (env, trace_id stage) |
| Grafana correlation + filters | ✅ deployed (log↔trace on clean field + header fallback; host/env/app/severity vars) |
| prod `base.alloy` | ⏳ changed in-repo (env + homelab_std), awaiting infra deploy |
| prod `podcast.alloy` / `player.alloy` | ⏳ changed in `podcast_scraper-infra`, deploy with next app deploy |
| orrery | ⏳ grafana-agent — assess separately |
