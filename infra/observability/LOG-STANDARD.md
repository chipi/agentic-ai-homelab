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
| `app` | stream label | low | application (`operator`, `player`, `orrery`, …) | from the **compose project** (see below) |
| `component` | stream label | low | sub-part of an app: `api`, `ui`, `pipeline`, `worker` | from the **compose service** (see below) |
| `container` | stream label | low-med | container name | `loki.source.docker` sets it |
| `trace_id` | **structured_metadata** | **high** | 32-hex W3C/Sentry trace id, for correlation | `loki.process` regex stage (below) |

**Why `trace_id` is structured_metadata, not a stream label:** trace ids are unique
per request (very high cardinality). As a *stream label* they would explode
VictoriaLogs' stream count. As *structured_metadata* they are a normal queryable
field (`trace_id:<id>`) with **no** stream-cardinality cost. This distinction is
mandatory — never promote `trace_id` (or any per-request id) to a stream label.

### Deriving `app` + `component` from compose (the "double API" case)

Several apps ship the **same service name** — e.g. both the operator and player
stacks run a container literally named `api` from the same image. The service
name alone can't tell them apart; the **compose project** can. So:

- `app` ← `com.docker.compose.project` (mapped to a clean name)
- `component` ← `com.docker.compose.service` (mapped to `api` / `ui` / …)

Example relabel rules in the Alloy `loki.source.docker` (or a `discovery.relabel`):

```alloy
// app  <- compose project   (operator vs player: distinguishes the two `api`s)
rule {
  source_labels = ["__meta_docker_container_label_com_docker_compose_project"]
  regex         = "compose|operator.*"   // operator stack's project dir
  target_label  = "app"
  replacement   = "operator"
}
rule {
  source_labels = ["__meta_docker_container_label_com_docker_compose_project"]
  regex         = "player.*"
  target_label  = "app"
  replacement   = "player"
}
// component <- compose service  (api stays api; viewer/learning-app -> ui)
rule {
  source_labels = ["__meta_docker_container_label_com_docker_compose_service"]
  regex         = "api"
  target_label  = "component"
  replacement   = "api"
}
rule {
  source_labels = ["__meta_docker_container_label_com_docker_compose_service"]
  regex         = "viewer|learning-app|.*-ui"
  target_label  = "component"
  replacement   = "ui"
}
```

Result: `app=operator,component=api` vs `app=player,component=api` are separable,
so the two APIs' logs never merge. Filter by `app` and/or `component` in Grafana.

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

## Applied where

| Source | Alloy | Repo | Status |
|---|---|---|---|
| Mac mini (`homelab`) | `alloy-homelab` | this repo (`infra/observability/`) | reference impl |
| DGX (`dgx-llm-1`) | `alloy` | this repo (`infra/observability/`) | reference impl |
| prod VPS (`prod-podcast`) | node Alloy | `podcast_scraper-infra` | rollout |
| apps (orrery / podcast / player) | app logging | app repos | rollout |
