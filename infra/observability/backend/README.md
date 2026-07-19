# Self-hosted observability backend — VictoriaMetrics + Grafana

The storage + viz half of the observability stack. Runs on **one** host at a
time (DGX now, Mac mini once it's up). The Alloy **collectors** in [`../`](../)
run on every host and `remote_write` here.

```
Alloy@DGX ─┐
Alloy@VPS ─┼─► VictoriaMetrics :8428 ◄── Grafana :3000
Alloy@…   ─┘        (this compose)
```

- **VictoriaMetrics** — single-node TSDB, the remote_write sink. Low RAM,
  PromQL-compatible, runs fine on a Mac mini.
- **Grafana OSS** — reads VM, draws dashboards. Datasource + dashboard folders
  are provisioned from files in git, so they survive host moves.

Ingest and the Grafana UI are published to the **Tailscale IP only** — never a
public interface. Grafana reaches VM over the internal compose bridge.

## Prerequisites

- Docker + compose.
- **Tailscale** on this host and on every host that pushes (DGX, VPS, …). Note
  this host's tailnet IP (`tailscale ip -4`) — call it `100.x.y.z`.

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
# on the backend host — should climb as collectors report:
curl -s "http://127.0.0.1:8428/api/v1/query?query=up" | head
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
- VM snapshot for a real backup: `curl http://127.0.0.1:8428/snapshot/create`
  then copy the snapshot dir out of the volume.

## Notes

- Images are pinned. Bump deliberately.
- No auth on VM by design (tailnet-private). If you ever expose it wider, front
  it with `vmauth` or a reverse proxy — don't publish 8428 publicly.
