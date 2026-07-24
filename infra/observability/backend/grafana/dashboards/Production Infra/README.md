# Production Infra — Grafana folder

Monitors the **prod-podcast VPS** — the public-facing host running podcast services. Host metrics and container telemetry route to VictoriaMetrics; security/access logs route to VictoriaLogs via node Alloy.

## Boards

| Board | uid | Goal | Datasource | Key panels |
|---|---|---|---|---|
| **Host Overview** | `prod-infra-host-overview` | Host OS health snapshot | VictoriaMetrics (prometheus) | CPU busy, Memory used, Disk used (/), Load1, CPU by mode (stack), Memory (total/used, timeseries), Network (rx/tx bytes/s), Disk free by mount |
| **Containers** | `prod-infra-containers` | Docker container resource consumption | VictoriaMetrics (prometheus) | Container count, Total container memory, Host cores, Host memory, CPU by container (cores), Memory (working set) by container, Network RX/TX by container, Containers by memory (top 20), OOM events. Var: `$instance` (default prod-podcast). |
| **Edge Security** | `prod-infra-edge-security` | SSH brute-force, fail2ban, Caddy request/status summary | VictoriaLogs (victoriametrics-logs-datasource) | SSH failed/accepted logins, fail2ban ban count, Caddy request count; SSH auth failures over time, fail2ban actions over time, Caddy requests/status over time; raw security event logs (sshd/fail2ban), Caddy access tail. |

## Notes

- **Containers board limitation (GH #1272):** cAdvisor container name labels are absent on the VPS, same as homelab. Panels grouped by container name (CPU/Memory/Network by container, Containers by memory) remain unpopulated; scalar stats (count, total memory, OOM events) and host metrics work.
- **Edge Security is log-based only.** No Caddy metrics query (no reverse-proxy instrumentation); panels query VictoriaLogs journal exports from Alloy (sshd, fail2ban, caddy access logs).
- **Provisioning:** All JSONs auto-load into the **Production Infra** Grafana folder within 30s (configured in `../provisioning/dashboards/dashboards.yml`). Dashboards persist in git; `allowUiUpdates: true` lets UI tweaks, but export back to JSON to persist.

See parent [`../README.md`](../README.md) for vendored dashboard notes and datasource setup.
