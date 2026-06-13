# Observability — Grafana Alloy + DCGM + cAdvisor + Ollama metrics

Unified self-hosted observability for a DGX-class homelab. One compose, four
containers, push to Grafana Cloud over outbound HTTPS only.

## What gets scraped

| Source | Exporter | What you see |
|---|---|---|
| Linux host (CPU, mem, disk, net, fs, load) | Alloy built-in `prometheus.exporter.unix` | Base health — every Grafana dashboard assumes node_exporter-style metrics |
| NVIDIA GPU (utilization, VRAM, power, temp, ECC) | `dcgm-exporter` | First-party NVIDIA exporter, GB10 Blackwell compatible |
| Docker containers (CPU/mem/restarts per container) | `cadvisor` | Per-container forensics — "why did this container restart" |
| vLLM (tok/s, queue depth, KV cache, TTFT, per-model) | built-in `/metrics` | Serving health for the coding LLM |
| Ollama (model inventory, RAM, loaded count) | `ollama-metrics` sidecar | Passive Level-1 visibility into Ollama |

## How it pushes

Alloy uses `prometheus.remote_write` to Grafana Cloud's hosted Prometheus.
Auth via basic auth (username = instance ID; password = API token).

Tailscale ACL change required: **none** (outbound HTTPS to grafana.net is
allowed by default).

## Quick start

```bash
# On the DGX-class host — run the compose from the repo in place:
git clone <this repo>
cd agentic-ai-homelab/infra/observability

cp .env.example .env   # .env is gitignored; never commit it
$EDITOR .env           # paste the 3 Grafana Cloud values
chmod 600 .env

sudo docker compose up -d
sudo docker compose ps
sudo docker compose logs alloy | grep -i 'remote_write\|error' | head
```

Verify in Grafana Cloud → Explore:
```
up{instance="homelab-1"}
```
Expect rows for `node`, `dcgm`, `cadvisor`, `vllm` (0 if vLLM down — expected),
`ollama` (1 if `ollama-metrics` sidecar started cleanly).

## Dashboards to import

- **1860** — Node Exporter Full
- **12239** — NVIDIA DCGM Exporter
- **17296** — vLLM
- **893** — Docker (cAdvisor)

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

- **Volume**: scrape data flushes to Grafana Cloud continuously; nothing
  persists on disk except Alloy's WAL (~10MB) and the cAdvisor
  in-memory state. Reboot losses are trivial.
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
- If you don't have outbound internet (some airgapped setups), this
  push-based config doesn't apply — you'd need a local Prometheus +
  Grafana instead.

## Provenance

This config was authored in the session captured in
`docs/history/0001-genesis.md` Phase 3. Decisions D-0003 (NorskHelsenett
choice) and D-0004 (Level 1 default) recorded in
`docs/history/0002-decisions.md`.
