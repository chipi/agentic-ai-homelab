# VPS collector — `prod-podcast`

Second Alloy collector (the first is the DGX one at `../../`). Ships the
podcast-scraper VPS's **host + container metrics** to VictoriaMetrics and its
**security logs** to VictoriaLogs on the DGX, over the tailnet.

Deployed on the box at **`/opt/vps-observability/`** (not `~/agentic-ai-homelab`);
this dir is the tracked source of truth. Copy `.env.example` → `.env` there.

## What it ships (and what it deliberately doesn't)

Self-hosted backend → **basic infra profile, not a firehose**:

| Signal | Source | Interval / volume |
|---|---|---|
| Host CPU/mem/disk/net/fs | node-exporter (`job=node`) | **60s** |
| Container CPU/mem/net/fs | cAdvisor `:8081` (`job=cadvisor`), keep-listed | **60s** |
| sshd / fail2ban | systemd journal (`job=systemd-journal`) | event-driven |
| Caddy edge access | `/var/log/caddy/access.log` (`job=caddy`) | event-driven |

**Not shipped — on purpose:** container stdout/stderr. For a self-hosted backend
that's a firehose; app logs stay locally via `docker logs`. Only the security
signal (journal + Caddy) goes to VictoriaLogs.

Differences vs the DGX collector: no GPU/LLM scrapes (dcgm/vllm/ollama dropped);
cAdvisor on `:8081` (`:8080` is the viewer); 60s scrape (DGX is finer); no
container-log shipping; no docker.sock mount (only container-log discovery used it).

## Deploy / redeploy

```sh
# on the VPS, from /opt/vps-observability
docker compose up -d          # PROD box — get per-instance approval first
alloy fmt config.alloy        # validate before up
```

## Verify (from any tailnet host)

```sh
# metrics landing:
curl -s "http://100.69.49.126:8428/api/v1/query?query=up{instance='prod-podcast'}"
# security logs landing (should be journal + caddy only):
curl -sG "http://100.69.49.126:9428/select/logsql/query" \
  --data-urlencode "query=instance:prod-podcast AND _time:5m | stats by (job) count()"
```

Backend + tailnet ACL details: `../../backend/README.md` and the handover at
`docs/wip/observability-vps-collector-handover.md`.
