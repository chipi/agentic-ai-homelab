# Handover — point the VPS collector at the self-hosted metrics backend

**For:** the next agent. **Goal:** get the VPS (`prod-podcast`) shipping its
host + container metrics into the self-hosted VictoriaMetrics that now runs on
the DGX, so they show up in the same Grafana.

**Status when this was written (2026-07-19):** backend is LIVE on the DGX and
the DGX collector already writes to it. This task adds the VPS as a *second*
collector. Nothing here touches the DGX.

---

## The target you're pointing at

> **`homelab`** is the Tailscale name of the observability host (a MagicDNS device name →
> the DGX now, the Mac mini later). See [`../recipes/observability-endpoints.md`](../recipes/observability-endpoints.md).
> Until `homelab` is named (on the mini), substitute the host IP `100.69.49.126`.

- **VictoriaMetrics** (ingest): `http://homelab:8428/api/v1/write`
  - Reachable from any tailnet host. No auth on the tailnet.
- **Grafana** (where you'll verify): `http://homelab:3000` (Homelab folder).

## The machine you're working on

- **VPS:** `prod-podcast`, Tailscale IP `100.124.111.115`. It's on the tailnet
  already. Confirm SSH first: `ssh prod-podcast` (MagicDNS) or `ssh 100.124.111.115`.
- **It is PRODUCTION** (runs the podcast-scraper stack). Read-only probe first;
  get per-instance approval from the operator before `docker compose up`.

## PREREQUISITE — tailnet ACL must allow 8428 to the DGX

This tailnet uses a **restrictive per-port ACL**. The backend host
(`tag:dgx-llm-host`, `homelab`) must have **`8428`** (metrics) and, if you
also ship logs, **`9428`** (logs) granted, or the push will silently time out
(tailscaled drops it — the collector logs connection errors). `3000`, `8428`
and `9428` were all granted 2026-07-19, so no ACL change should be needed —
but verify from the VPS BEFORE configuring:
`curl -m5 -o /dev/null -w "%{http_code}\n" http://homelab:8428/health`
(expect `200`; and `.../9428/` if shipping logs — a timeout means the ACL grant
is missing — stop and tell the operator).

If you ship logs from the VPS too, also set in its collector `.env`:
`LOGS_WRITE_URL=http://homelab:9428/insert/loki/api/v1/push`.

## Key unknown to resolve FIRST

Does the VPS already run the Alloy collector, or not? Two paths:

### Path A — collector already there
Check: `ssh prod-podcast 'docker ps --format "{{.Names}}" | grep -E "alloy|cadvisor"'`
and `ls ~/agentic-ai-homelab/infra/observability/`.
If Alloy is running, you only need to repoint it (see "Repoint" below).

### Path B — no collector yet (more likely)
The VPS needs the collector deployed. It has **no GPU and probably no
vLLM/Ollama**, so the repo's `config.alloy` (which scrapes `dcgm:9400`,
`vllm:9000`, `ollama:9778`) will have those targets permanently DOWN — harmless
(they just report `up=0`) but noisy. Decide with the operator:
- **Quick:** deploy the collector as-is; ignore the 3 dead LLM/GPU targets.
- **Clean:** trim `config.alloy` on the VPS to host + cAdvisor only (drop the
  dcgm/vllm/ollama scrape blocks). Recommended for a non-GPU box.

Also: the VPS's Docker `cadvisor` gives you the podcast-stack container metrics —
that's the useful signal here, alongside host CPU/mem/disk/net.

## Repoint / configure (the actual change)

In the VPS collector's `infra/observability/.env`:

```sh
REMOTE_WRITE_URL=http://homelab:8428/api/v1/write   # DGX VictoriaMetrics
HOMELAB_INSTANCE=prod-podcast     # distinct from the DGX so series don't collide
HOMELAB_CLUSTER=vps               # logical group; filter on this in Grafana
```

Notes:
- `REMOTE_WRITE_URL` is honored by the **new** `config.alloy` (coalesce:
  `REMOTE_WRITE_URL` wins, else `GRAFANA_CLOUD_PROM_URL`). If the VPS is on an
  **old** `config.alloy` (pre-rename, reads `GRAFANA_CLOUD_PROM_URL` directly),
  just set `GRAFANA_CLOUD_PROM_URL` to the VM URL instead — same effect. Check
  which by `grep REMOTE_WRITE_URL config.alloy`.
- Back up the existing `.env` first: `cp -a .env .env.bak.pre-vm`.
- VM ignores basic_auth on the tailnet, so leftover Grafana Cloud creds are fine.

Apply: `cd infra/observability && docker compose up -d` (recreates Alloy to
reload env). Confirm no `remote_write` errors: `docker logs alloy | grep -iE 'remote_write|error' | tail`.

## Verify (from any tailnet host)

```sh
# new instance should appear:
curl -s "http://homelab:8428/api/v1/query?query=up{instance='prod-podcast'}"
# host + cadvisor series climbing for the VPS:
curl -s "http://homelab:8428/api/v1/query?query=count({instance='prod-podcast'})"
```

Then open Grafana → the Node Exporter Full / Docker dashboards should offer
`prod-podcast` in the instance/job dropdown.

## Safety / rollback

- Non-destructive: this only adds an outbound metrics push + (Path B) a few
  read-only exporter containers. No prod data touched.
- Rollback: restore `.env.bak.pre-vm` and `docker compose up -d`, or
  `docker compose stop alloy` to stop shipping. `docker compose down` removes
  the collector containers.
- Don't publish `:8428`/`:3000` publicly anywhere — tailnet only.

## Gotchas

- Ports bind to the **tailnet IP**, so verify with `homelab`, never
  `127.0.0.1`.
- If the VPS runs `ufw` default-deny inbound, outbound push still works (no
  inbound rule needed on the VPS for pushing).
- Give the VPS a distinct `HOMELAB_INSTANCE` or its series will merge with the
  DGX's and confuse dashboards.

Background + full design: `infra/observability/backend/README.md` and its
sibling `infra/observability/README.md`.
