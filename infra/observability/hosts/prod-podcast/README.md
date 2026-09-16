# VPS collector — `prod-podcast`

Second Alloy collector (the first is the DGX one at `../../`). Ships the
podcast-scraper VPS's **host + container metrics** to VictoriaMetrics and its
**security logs** to VictoriaLogs on the **Mac mini** (`homelab`), over the
tailnet. (The backend was briefly on the DGX during setup — that stopgap is
retired; ship to `homelab`.)

Deployed on the box at **`/opt/vps-observability/`** (not `~/agentic-ai-homelab`).
Copy `.env.example` → `.env` there.

> **This directory is a MIRROR, not the source of truth.** Nothing here is deployed
> from this repo. It is kept complete and runnable so a checkout is a usable
> disaster-recovery definition of the stack — `docker-compose.yml` mounts `./config.d`,
> so the `.alloy` files must stay present — but edits here reach nothing.
>
> | file | owner / deploy path |
> |---|---|
> | `config.d/*.alloy` | `podcast_scraper:infra/observability/` → `deploy-config.yml` |
> | `docker-compose.yml` | **nobody** — see below |
>
> This warning exists because the previous version of this line said the opposite
> ("this dir is the tracked source of truth"), and `base.alloy` then drifted 41 lines
> from the box while reading as authoritative. See `chipi/agentic-ai-homelab#64`.

### `docker-compose.yml` is unowned — and that is tracked, not accepted

No deploy path ships it, so it can only change by someone editing the box as root.
Verified 2026-09-16: repo vs box is **comment-only drift, zero behavioural difference**
(41 functional lines each, parsed YAML structures equal). The repo copy is the better
one — it carries the cadvisor-pin warning below, which the box lost, and the box's own
header comment is *wrong*, claiming telemetry ships to the DGX when it ships to
`homelab`.

It cannot join the GitOps loop the way `config.d` did: `/opt/vps-observability` is
`drwxr-xr-x root root`, so `deploy` can neither write the file nor rename over it.
(`config.d` works precisely because it is `drwxrwxr-x deploy deploy`.) Adopting it needs
a one-time `chown deploy` on **the file, not the directory** — the directory also holds
`.env` with `GRAFANA_CLOUD_PROM_API_KEY`. Tracked separately; until then, treat the box
copy as unmanaged.

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

> **DO NOT run a bare `docker compose up -d` in `/opt/vps-observability`.** It omits the
> endpoints override and silently repoints Alloy at raw endpoints that no longer work —
> metrics keep flowing (so nothing looks wrong) while logs are dropped. That is not
> hypothetical: it cost ~5h of prod log shipping on 2026-09-16 (#64). The previous
> version of this section recommended exactly that command.

Normal path — **no root, no SSH**, both gated on the `prod` environment:

```sh
# Alloy config.d drop-ins (base.alloy, selfmon.alloy, <app>.alloy) — scp + HUP
gh workflow run deploy-config.yml -f surface=<player|operator|all>

# Alloy remote-write endpoints (the TLS nodes) — override + recreate
gh workflow run deploy-vps-observability-endpoints.yml -f confirm=DEPLOY_OBS_ENDPOINTS
```

If you genuinely must recreate by hand on the box, **include the override**:

```sh
cd /opt/vps-observability && docker compose -p vps-observability \
  -f docker-compose.yml -f "$HOME/.vps-observability-endpoints.override.yml" up -d alloy
```

Validate any `.alloy` change before shipping — the files are merged into ONE config, so a
syntax error in any of them takes down *all* telemetry on the next HUP:

```sh
docker run --rm -v "$PWD/config.d/base.alloy:/c.alloy:ro" \
  --entrypoint /bin/alloy grafana/alloy:v1.17.0 fmt /c.alloy
```

## Verify (from any tailnet host)

```sh
# metrics landing:
curl -s "http://homelab:8428/api/v1/query?query=up{instance='prod-podcast'}"
# security logs landing (should be journal + caddy only):
curl -sG "http://homelab:9428/select/logsql/query" \
  --data-urlencode "query=instance:prod-podcast AND _time:5m | stats by (job) count()"
```

Backend + tailnet ACL details: [`../../backend/README.md`](../../backend/README.md).

## Log collection: one node Alloy + per-app drop-ins (ADR-121)

This box runs **one** Alloy (the node agent / "router" — reads the Docker socket, so it
sees every container). Alloy runs against the **directory** `/etc/alloy/config.d/`
(`command: run /etc/alloy/config.d`) and merges all `*.alloy` files into one config:

- `config.d/base.alloy` — the shared router: `discovery.docker`, the `loki.write` sink
  (→ homelab VictoriaLogs), + the journal/caddy/podcast sources. **Owned by
  `podcast_scraper:infra/observability/base.alloy`**, not by this repo — the copy here is
  a mirror. (It was genuinely unowned until 2026-09-16, hand-edited over SSH as root; the
  `.bak-<timestamp>` files on the box are the fingerprint.)
- `config.d/selfmon.alloy` — Alloy scraping its own `:12345`, so the collector's shipping
  health (`loki_write_dropped_entries_total`) is visible. Also owned by `podcast_scraper`.
- `config.d/<app>.alloy` — each app drops its OWN `discovery.relabel` keep-filter + labels
  (e.g. `orrery.alloy`), delivered by that app's deploy. Mirrors the ADR-114 Caddy edge
  (`sites/<app>.caddy`). Reload after a drop: `docker kill -s HUP alloy` (no root needed).

**Deploy rule:** the box's `/opt/vps-observability/config.d/` may contain app drop-ins
from other repos — a deploy here must update **only `base.alloy`**, never wipe the dir.
