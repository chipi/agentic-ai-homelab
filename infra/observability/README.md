# Observability — Grafana Alloy + DCGM + cAdvisor + Ollama metrics

Unified self-hosted observability for the homelab. One compose, four
containers, `remote_write` to the self-hosted **VictoriaMetrics** backend
([`backend/`](backend/)) via `REMOTE_WRITE_URL`. (There's no Grafana Cloud
anymore — it was retired for the self-hosted backend; see ADR-0005/0006.)

This dir is the **collector**; it's designed to run on every collecting host.
The storage + viz half (VictoriaMetrics + VictoriaLogs + VictoriaTraces +
Grafana) lives in [`backend/`](backend/) and runs on the **Mac mini**
(`homelab`) — not the DGX.

> **Current reality (2026-07-25):** the DGX has no working collector on it yet
> (no SSH). So instead of this compose running *on* the DGX, the mini's
> [`../dgx-scrape/`](../dgx-scrape/README.md) launchd loop **pulls** the DGX's
> DCGM (:9400) and cAdvisor (:8080) exporters over the LAN and pushes them into
> VictoriaMetrics. The mini runs the [`hosts/homelab/`](hosts/homelab/) variant
> of this collector for its own host metrics. See the
> [host map](../README.md) for who runs what.

Besides metrics, Alloy also ships **Docker container logs** (`loki.source.docker`
via the mounted Docker socket) to VictoriaLogs — set `LOGS_WRITE_URL` to the
backend's `http://<ip>:9428/insert/loki/api/v1/push`. Host journald is available
but commented out in `config.alloy`.

## What gets scraped

| Source | Exporter | What you see |
|---|---|---|
| Linux host (CPU, mem, disk, net, fs, load) | Alloy built-in `prometheus.exporter.unix` | Base health — every Grafana dashboard assumes node_exporter-style metrics |
| NVIDIA GPU (utilization, VRAM, power, temp, ECC) | `dcgm-exporter` | First-party NVIDIA exporter, GB10 Blackwell compatible |
| Docker containers (CPU/mem/restarts per container) | `cadvisor` | Per-container forensics — "why did this container restart" |
| vLLM (tok/s, queue depth, KV cache, TTFT, per-model) | built-in `/metrics` | Serving health for the coding LLM |
| Ollama (model inventory, RAM, loaded count) | `ollama-metrics` sidecar | Passive Level-1 visibility into Ollama |

## How it pushes

Alloy uses `prometheus.remote_write` to the self-hosted VictoriaMetrics
backend: set `REMOTE_WRITE_URL` to the backend host's tailnet address,
`http://homelab:8428/api/v1/write` (or its IP `http://100.87.33.61:8428/...`).
No auth on the tailnet. See [`backend/`](backend/). Reaching it needs both the
collecting host and the backend on the tailnet.

## Quick start

```bash
# On a collecting host — run the compose from the repo in place:
git clone <this repo>
cd agentic-ai-homelab/infra/observability

cp .env.example .env   # .env is gitignored; never commit it
$EDITOR .env           # set REMOTE_WRITE_URL=http://homelab:8428/api/v1/write
                       # (and LOGS_WRITE_URL=http://homelab:9428/insert/loki/api/v1/push)
chmod 600 .env

sudo docker compose up -d
sudo docker compose ps
sudo docker compose logs alloy | grep -i 'remote_write\|error' | head
```

Verify in the self-hosted Grafana (`http://homelab:3000`) → Explore, or with a
direct query against VictoriaMetrics:
```bash
curl -s "http://homelab:8428/api/v1/query?query=up{instance='homelab'}"
```
Expect rows for `node`, `dcgm`, `cadvisor`, `vllm` (0 if vLLM down — expected),
`ollama` (1 if `ollama-metrics` sidecar started cleanly).

## Dashboards

Dashboards + alerts are **provisioned as code** on the backend, under
[`backend/grafana/`](backend/grafana/) — they load automatically and survive
host moves. No manual import. The organized set (Homelab / Production Infra /
Podcast Operator / Podcast Player) is documented in
[`backend/grafana/dashboards/README.md`](backend/grafana/dashboards/README.md).

## The Ollama observability decision (the part you actually need to read)

Both viable Ollama exporters (NorskHelsenett's `ollama-metrics` and
`frcooper/ollama-exporter`) are **transparent proxies**. They sit between
your application and Ollama. Three levels of deployment:

| Level | What changes | What you see | Trade |
|---|---|---|---|
| **1. Passive** | Bring up exporter, no client changes. Default in this compose. | `ollama_loaded_models`, `ollama_model_ram_mb`, `ollama_model_loaded` (1/0 per model). Per-request metrics stay at 0. | Free visibility; no risk |
| **2. Selective proxy** | Retarget *some* Ollama clients to `:9778` instead of `:11434` | Above + per-request tokens / duration / time-per-token for retargeted clients | Exporter becomes a hard dep for those clients |
| **3. Full proxy** | All Ollama clients hit `:9778` | Complete per-request visibility | Single point of failure for all Ollama traffic |

Default ships as Level 1. To promote a specific client to Level 2: change
its Ollama base URL config from `http://<host>:11434` to `http://<host>:9778`.
That's the entire promotion.

## Configuration

Edit `config.alloy` to:
- Adjust the `instance` label if you have multiple homelab hosts.
- Uncomment the secondary-vLLM block if running multiple vLLM composes.
- Uncomment the fastapi block + adjust ports if you wire prometheus_client
  into project HTTP services.

`scrape_interval`: 15s for high-volume LLM serving (catches spikes), 30s
for host/cAdvisor (lower-volume base metrics).

## Operational

- **Volume**: the collector holds nothing durable — it flushes to the
  VictoriaMetrics backend continuously; only Alloy's WAL (~10MB) and cAdvisor's
  in-memory state live on the collecting host. Durable storage is the backend's
  named volumes on the mini. Reboot losses on a collector are trivial.
- **Resource cost**: ~250MB RAM total across the 4 containers, <5% of one
  CPU core under typical scrape load.
- **Log rotation**: each container limited to 60MB total
  (`20m × 3`) to prevent disk fill on long-running deploys.
- **Container restart**: `unless-stopped` — survives reboots, stops only on
  explicit `docker compose down`.

## When to NOT run this

- If your DGX-class box is doing time-sensitive ML training where every
  watt of GPU matters, the DCGM exporter's continuous polling is a tiny
  but nonzero overhead. Worth measuring; usually trivial.
- The backend is already local (VictoriaMetrics on the mini, no cloud), so
  airgapped / no-outbound-internet setups are fine — everything stays on the
  tailnet. The only reachability requirement is collector ↔ backend on the
  tailnet.

## Provenance

This config was authored in the session captured in
`docs/history/0001-genesis.md` Phase 3. Decisions D-0003 (NorskHelsenett
choice) and D-0004 (Level 1 default) recorded in
`docs/history/0002-decisions.md`.

## Related

- Systems index: [`infra/README.md`](../README.md)
- Global docs: [Pillar 2 — Local AI infra](https://github.com/chipi/agentic-ai-homelab/blob/main/docs/local-ai-infra.md)
- Dashboards: [`backend/grafana/dashboards/README.md`](backend/grafana/dashboards/README.md)
- Alerts: [`backend/grafana/provisioning/alerting/README.md`](backend/grafana/provisioning/alerting/README.md)
