# homelab (Mac mini) self-monitoring

The Mac mini runs the observability backend, so it should watch itself — most
importantly **disk** (the SSD holds all metric/log/trace retention) and the
stack containers' health/logs.

The DGX's Alloy collector can't run here (Linux-only). This is the macOS variant:

| Signal | Mechanism | Notes |
|---|---|---|
| macOS host (cpu/mem/**disk**/load) | **native `node_exporter`** (brew) on `:9100` | MUST be native — a container sees the OrbStack Linux VM, not real macOS |
| container logs (all stack containers) | Alloy container + Docker socket → VictoriaLogs | high value |
| metrics/logs sink | local backend via `host.docker.internal:8428/:9428` | loopback-local, no tailnet/ACL |

**Known gap:** per-container CPU/mem (cAdvisor) is not included — cAdvisor is
unreliable on OrbStack. Host + logs cover the important signals; add cAdvisor
later if you want per-container metrics.

## Setup

1. **Native host exporter** (once):
   ```sh
   brew install node_exporter
   brew services start node_exporter      # listens on :9100, restarts on boot
   curl -s localhost:9100/metrics | head  # sanity
   ```

2. **Collector**:
   ```sh
   cd infra/observability/hosts/homelab
   docker compose up -d
   ```

## Verify

```sh
# host metrics landing (from the mini or any tailnet host via homelab:8428):
curl -s "http://localhost:8428/api/v1/query?query=up{job='node',instance='homelab'}"
# disk free %:
curl -s "http://localhost:8428/api/v1/query?query=node_filesystem_avail_bytes{instance='homelab',mountpoint='/'}"
```

Then Grafana → **Node Exporter Full** dashboard → pick `instance=homelab`, and
**Logs — Overview** → the stack containers appear.

## Alerting

The backend's provisioned `infra-disk-low` rule (VictoriaMetrics, <10% free)
fires automatically once these `node_filesystem_*` series arrive — no extra
config. Wire a notification channel in the backend `.env` to actually get pinged.

## Notes

- Bridge-networked; `host.docker.internal` (via `extra_hosts` host-gateway)
  reaches both node_exporter and the published backend ports.
- Everything is same-box loopback — no tailnet exposure, no ACL grants.
