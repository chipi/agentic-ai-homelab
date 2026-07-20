# Self-hosted observability backend — VictoriaMetrics + VictoriaLogs + VictoriaTraces + Grafana

The storage + viz half of the observability stack. Runs on **one** host at a
time (DGX now, Mac mini once it's up). The Alloy **collectors** in [`../`](../)
run on every host and push metrics + logs here; apps push traces (OTLP).

```
metrics ─► VictoriaMetrics :8428 ─┐
logs    ─► VictoriaLogs    :9428 ─┼─► Grafana :3000
traces  ─► VictoriaTraces  :10428 ┘        (this compose)
```

- **VictoriaMetrics** — single-node TSDB, the metrics remote_write sink. Low
  RAM, PromQL-compatible, runs fine on a Mac mini.
- **VictoriaLogs** — the logs sink (Loki push protocol). Same-family, light,
  LogsQL. Grafana reads it via the `victoriametrics-logs-datasource` plugin.
- **VictoriaTraces** — the traces sink (**OTLP** ingest at
  `/insert/opentelemetry/v1/traces`). Same family. Grafana reads it via the
  built-in **Jaeger** and **Tempo** datasources (VictoriaTraces speaks both) —
  no plugin; plus the `grafana-exploretraces-app` for exploration. Young (pre-1.0).
- **Grafana OSS** — reads all three, draws dashboards + Explore-logs/traces.
  Datasources + dashboards are provisioned from files in git, so they survive moves.

Ingest and the Grafana UI are published to the **Tailscale IP only** — never a
public interface. Grafana reaches the stores over the internal compose bridge.

## Prerequisites

- Docker + compose.
- **Tailscale** on this host and on every host that pushes (DGX, VPS, …). Note
  this host's tailnet IP (`tailscale ip -4`) — call it `100.x.y.z`.
- **Tailnet ACL:** if your tailnet uses a restrictive per-port ACL (tagged
  hosts with an explicit port allowlist — check with
  `sudo tailscale debug netmap`), grant **`3000`** (Grafana UI), **`8428`**
  (metrics ingest) and **`9428`** (logs ingest) to this host's tag in the admin
  console. The last two are only needed for *remote* collectors — a same-host
  collector reaches them locally (bypasses the ACL). A default "allow all
  between own devices" ACL needs nothing. Symptom of a missing grant: the
  container listens fine locally but tailnet peers time out.

## Bring-up

```sh
cd infra/observability/backend
cp .env.example .env
# edit .env:
#   VM_LISTEN=100.x.y.z         # this host's tailnet IP
#   GRAFANA_LISTEN=100.x.y.z    # so you can reach the UI from your laptop
#   GRAFANA_ADMIN_PASSWORD=...  # required
docker compose up -d
docker compose ps
```

Grafana → `http://100.x.y.z:3000` (admin + the password you set). The
VictoriaMetrics datasource is already wired; drop dashboard JSON into
[`grafana/dashboards/`](grafana/dashboards/) (IDs listed in its README).

## Point a collector here

On each collecting host (DGX, VPS), edit `infra/observability/.env`:

```sh
REMOTE_WRITE_URL=http://100.x.y.z:8428/api/v1/write   # backend's tailnet IP
```

then restart that host's Alloy: `cd infra/observability && docker compose up -d`.
`REMOTE_WRITE_URL` overrides the Grafana Cloud vars; VM needs no auth on the
tailnet. Confirm data is landing:

```sh
# from any tailnet host — VM binds to VM_LISTEN (the tailnet IP), not loopback.
# Substitute your backend host's tailnet IP for 100.x.y.z:
curl -s "http://100.x.y.z:8428/api/v1/query?query=count(up)"
```

## Cutover from Grafana Cloud (no gap)

VictoriaMetrics and Grafana Cloud are independent sinks. To migrate safely:

1. Bring this backend up; point **one** collector at it via `REMOTE_WRITE_URL`.
2. Verify metrics land in local Grafana for a day.
3. Flip the rest of the collectors.
4. Once happy, stop caring about Grafana Cloud (or keep it as an off-site
   mirror — that needs dual remote_write, not wired yet; ask if you want it).

## Move to the Mac mini later

1. `docker compose down` here (DGX).
2. Either migrate the named volumes (`vm-data`, `grafana-data`) to the mini, or
   start fresh — short retention makes a clean start cheap.
3. `docker compose up -d` on the mini.
4. Give the mini the tailnet name/IP the collectors expect (or update
   `REMOTE_WRITE_URL` on each collector). Dashboards + datasource re-provision
   from git automatically.

## Backup / rollback

- **Config** is in git (this dir). **Data** is in the two named volumes.
- Rollback of a bad bring-up: `docker compose down` (add `-v` to also wipe the
  volumes — destructive, only if you want a clean slate).
- VM snapshot for a real backup: `curl http://100.x.y.z:8428/snapshot/create`
  then copy the snapshot dir out of the volume.

## Alerting (provisioned as code, generic channels)

Alert **rules + routing** are code (`grafana/provisioning/alerting/`); notification
**channels** are pluggable — each ships inert and activates when you set its env in
`.env` + `docker compose up -d grafana`. Nothing new to deploy per channel.

- **rules.yaml** — metric starters over VictoriaMetrics: `infra-target-down`
  (`up==0`, critical), `infra-disk-low` (<10% free, warning), `app-http-5xx`
  (FastAPI 5xx, warning). Tune the thresholds against real traffic.
- **contactpoints.yaml** — `default` (email), `slack`, `glitchtip`. Each reads its
  secret from the container env via `$__env{...}`.
- **policies.yaml** — everything → `default`; `severity=critical` → **also**
  GlitchTip (opens an issue), then falls through to default.

**Add / configure a channel:** set the var in `.env`, restart grafana.

| Channel | Var(s) | Notes |
| --- | --- | --- |
| Slack | `ALERT_SLACK_WEBHOOK_URL` | incoming-webhook URL; make it the day-to-day channel by pointing the `default` route at `slack` in `policies.yaml` |
| Email | `GF_SMTP_*` + `ALERT_EMAIL_TO` | SMTP off by default |
| GlitchTip | `ALERT_GLITCHTIP_WEBHOOK_URL` | for confirmed issues (`severity=critical` route) |

**Add a NEW channel type** (PagerDuty, Telegram, Teams…): add a receiver to
`contactpoints.yaml` with that type + its `$__env{...}` secret, pass the var
through in the compose grafana `environment:`, and route to it in `policies.yaml`.
No rule changes.

**NOT yet re-homed:** the T-11 host/edge security rules (ssh brute-force,
fail2ban, Caddy 5xx) still live in the podcast repo as Loki LogQL. They need the
prod-VPS `tenant=common` security-log pipeline confirmed shipping here **and** a
LogQL→LogsQL translation before they can fire — don't provision rules that can't.

## Notes

- Images are pinned. Bump deliberately.
- No auth on VM by design (tailnet-private). If you ever expose it wider, front
  it with `vmauth` or a reverse proxy — don't publish 8428 publicly.
