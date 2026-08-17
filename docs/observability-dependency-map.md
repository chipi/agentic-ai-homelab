# Observability dependency & blast-radius map

**Why this exists:** on 2026-08-16/17 a chain of "obvious" changes cascaded into
hidden breakage we only found by practice — and failed a few times first:

- Reprovisioning Grafana (colima cutover) silently **wiped the Grafana service-account
  token** → the triage fleet's Grafana source 401'd **and** the hub home page's alert
  banner went blank. Nobody connected "Grafana volume reset" to "fleet + hub break."
- Closing the raw GlitchTip/Umami ports moved `homelab:8090` from reachable to refused
  → the triage fleet (which used `SF_HOST=homelab` → tailnet IP) lost its GlitchTip
  source. A port-close looked local; it wasn't.
- The same reprovision wiped **GlitchTip projects + DSN keys + API tokens**, **Umami
  websites + the DB `.env`**, and **Langfuse projects** — breaking prod error/analytics
  ingest, the fleet's read tokens, and umami-on-recreate.

The lesson: these services have **non-obvious consumers**. Before changing one, consult
the table below to size the blast radius. Keep this doc current when couplings change.

---

## Change → check (the blast-radius table)

| If you change… | Also breaks / must re-check | Where |
|---|---|---|
| **Reprovision Grafana** (fresh volume) | fleet's `GRAFANA_TOKEN` (SA token wiped → 401) · hub alert banner (`GTOK`) · any provisioned SA tokens | `signal-fleet/fleet-gateway.env`, `homelab-home/gen.sh:15` |
| **Reprovision GlitchTip** | ALL projects + DSN keys + API tokens gone → prod player/viewer/orrery DSNs, moss/pyannote/delivery DSNs, fleet `GLITCHTIP_TOKEN` read, fleet project 10 | apps' DSNs, `signal-fleet`, `dgx ~/.env` |
| **Reprovision Umami** | ALL websites + tracking UUIDs gone → deployed site scripts post to nothing · **the `.env` (DB pw + APP_SECRET) if it wasn't restored** → crash-loop on recreate | deployed HTML, `infra/umami/.env` |
| **Reprovision Langfuse** | projects reseed to `agents` only via INIT env → LiteLLM keys drift → **silent 401 trace loss** | `infra/litellm/.env` ↔ `infra/langfuse/.env` |
| **Close a raw port** (`*_LISTEN=127.0.0.1`) | any consumer using `homelab:<port>` / the tailnet IP (colima: `host.docker.internal`=bridge-gw, NOT loopback) → local pushers via that path break | fleet `SF_HOST`, litellm→langfuse `host.docker.internal:4000`, gha-deployer→`:9428` |
| **Rotate/revoke a Grafana token** | fleet triage source · hub alert banner (both read the SAME token from `fleet-gateway.env`) | `signal-fleet/fleet-gateway.env` → both consumers |
| **Rotate the GlitchTip API token** | fleet's issue-read correlation (`GLITCHTIP_TOKEN`) | `signal-fleet/mvp/correlate.py` |
| **Change LiteLLM or Langfuse project keys** | they MUST stay equal or LiteLLM 401s on export with **zero logs** (dead-man alert `langfuse-export-down` is the only signal) | `litellm/.env` `LANGFUSE_*` == `langfuse/.env` `LANGFUSE_INIT_PROJECT_*` |
| **Move a service to a new node / retire a serve port** | hub page links (`gen.sh` MINILINK + rows), the service READMEs, `docs/recipes/observability-endpoints.md`, `infra/README.md` all hardcode URLs | see "Known stale docs" below |
| **Restart/reprovision the mini `alloy`** | metrics + logs stop for the mini (and DGX is pulled by `dgx-scrape`, separate) | `infra/observability/hosts/homelab/` |
| **Revoke the caddy-tailscale `TS_AUTHKEY`** | nothing immediately (nodes keep enrolled state) — but no NEW node can be added | `infra/reverse-proxy/.env` |
| **Regenerate a converge-managed DGX compose** | hand-edits to `/opt/<svc>/docker-compose.yml` are overwritten — durable change is in `podcast_scraper` `infra/dgx/converge/deploy.py` | cross-repo |

---

## Per-service dependency detail

Legend — **P**roducers (write to it) · **C**onsumers (read it) · **I**ntegrators (hold a URL/token/DSN/pw for it).

### Grafana  (`grafana.tail6d0ed4.ts.net`, internal `:3000`)
- **P:** provisioning YAML (datasources/alerts/dashboards); operators.
- **C:** hub page alert banner (`gen.sh` → `/grafana/api/alertmanager/…`, bearer `GTOK`); **signal-fleet triage** (`config.py` `GRAFANA_URL/TOKEN`, `sources.py`); reverse-proxy node.
- **I:** admin pw (`observability/backend/.env`); **the viewer SA token is shared** — `fleet-gateway.env:GRAFANA_TOKEN` powers BOTH the fleet and the hub banner (`gen.sh:15`). Alert→GlitchTip webhook (`ALERT_GLITCHTIP_WEBHOOK_URL`).

### VictoriaMetrics  (`vm.tail6d0ed4.ts.net`, internal `:8428`)
- **P:** mini `alloy` remote_write; DGX `alloy` (→ vm node); `mini-metrics/push.sh` + `dgx-scrape/push.sh` (service_up, container_uptime_seconds); **fleetd/signal-fleet** (`fleetd_cycle`, `signal_fleet_*`); openrouter-spend collector.
- **C:** Grafana dashboards + alert rules; **hub page** (`/vm/api/v1/query`, same-origin via nginx); **signal-fleet** correlation (`VM_URL`); reverse-proxy node.
- **I:** push `…:8428/api/v1/import/prometheus` (no auth, tailnet); `SF_VM_URL`; `REMOTE_WRITE_URL` in `config.alloy`.

### VictoriaLogs  (`vlogs.tail6d0ed4.ts.net`, internal `:9428`)
- **P:** mini + DGX `alloy` (`loki.source.docker`); **gha-deployer CI ops events** (raw `:9428`, ADR-119 — still needs the raw grant).
- **C:** Grafana alert rules (SSH-fail, fail2ban, orrery-refresh LogsQL); **signal-fleet** (`VL_URL`, correlate.py); reverse-proxy node.
- **I:** `LOGS_WRITE_URL`; `SF_VL_URL`.

### VictoriaTraces  (`vtraces.tail6d0ed4.ts.net`, internal `:10428`)
- **P:** OTEL exporters (stub, not widely wired). **C:** VLogs→traces click-through; **signal-fleet** `vt_trace()`; Grafana. **I:** `SF_VT_URL`.

### GlitchTip  (`glitchtip.tail6d0ed4.ts.net`, internal loopback `:8090`)
- **P:** prod player/viewer/orrery apps (DSNs via prod Caddy); **moss (proj 14) + pyannote(→sentry.io removed)**; delivery (proj 13); Grafana critical-alert webhook; LiteLLM SENTRY_DSN.
- **C:** **signal-fleet triage** reads issues (`GLITCHTIP_URL/TOKEN`, correlate.py); hub page link.
- **I:** per-project DSNs (`<key>@host/<id>`); fleet read token; `GLITCHTIP_DOMAIN`+CSRF; superuser. **Project registry:** 1 gi-kg-viewer/orrery, 5 player, 6 orrery, 13 delivery, 14 moss, 15 pyannote, 16 podcast-pipeline, 17 podcast-api.

### Langfuse  (`langfuse.tail6d0ed4.ts.net`, internal `:4000`)
- **P:** LiteLLM callback (every LLM call); bugfix-fleet. **C:** operators (UI). **I:** **`LANGFUSE_INIT_PROJECT_*` == litellm `LANGFUSE_*` (hard coupling)**; litellm reaches it via `host.docker.internal:4000`; `langfuse-check` daemon probes both gateways.

### Umami  (`umami.tail6d0ed4.ts.net`, internal loopback `:3001`)
- **P:** deployed site trackers (`data-website-id=<uuid>`). **C:** operators (UI); hub page link. **I:** `UMAMI_DB_PASSWORD` + `UMAMI_APP_SECRET` (`infra/umami/.env` — **was a reprovision casualty**); website UUIDs: player `cd384a3e…`, viewer `a5a60c25…`, orrery `4a25d8da…`.

### LiteLLM  (`litellm.tail6d0ed4.ts.net`, internal `:4001`)
- **P:** its own call logs → postgres. **C:** Grafana LLM-spend dashboards (read-only PG role); hub page (master key display). **I:** `LITELLM_MASTER_KEY`; `LITELLM_PG_RO_PASSWORD` (Grafana); Langfuse keys; SENTRY_DSN; provider keys.

---

## Credential & silent-failure hotspots
1. **LiteLLM ↔ Langfuse project keys** — must be equal; drift = silent 401 trace loss. Only signal: `langfuse-export-down` dead-man alert + `langfuse-check` daemon.
2. **The shared Grafana viewer token** — one token in `fleet-gateway.env` feeds BOTH the fleet and the hub banner. Rotating it needs both re-checked.
3. **Reprovision wipes tokens/DSNs/projects, not just "data."** A "fresh empty volume" also deletes every API token + project + website + the service `.env` (if it lived only in the container). See the re-seed checklist below.
4. **colima networking gotcha** — `host.docker.internal` = bridge gateway (192.168.5.2), NOT loopback. A `127.0.0.1`-only bind is unreachable from other containers; the ACL trim (not the loopback bind) is what safely removes tailnet exposure.

## Re-seed checklist after a volume reprovision
For GlitchTip/Umami/Langfuse (the nightly `infra/backup/` pg_dump now makes this a restore):
1. **GlitchTip:** recreate each project with its old `id`+`public_key` (harvest DSNs from apps), recreate API tokens (fleet), re-set `GLITCHTIP_DOMAIN`+CSRF.
2. **Umami:** recreate websites with old UUIDs; rebuild `infra/umami/.env` (`UMAMI_DB_PASSWORD` via `ALTER USER`, new `UMAMI_APP_SECRET`).
3. **Langfuse:** confirm `LANGFUSE_INIT_PROJECT_*` == litellm keys.
4. **Grafana:** mint a new Viewer SA token → `fleet-gateway.env:GRAFANA_TOKEN` → regenerate the hub page.

## Known stale docs (2026-08-17 audit — to sweep)
These still describe the pre-migration exposure (serve ports `:8443/:8444/:8445/:10000`,
`homelab:8888`, raw `:8090/:3001` as tailnet-reachable, OrbStack). Fix or banner them:
`docs/recipes/observability-endpoints.md` (full rewrite) · `infra/homelab-serve/README.md`
(deprecate) · `infra/README.md` · `infra/{glitchtip,umami,langfuse,homelab-home}/README.md` ·
`docs/adr/ADR-0006-*` (OrbStack→colima) · `docs/recipes/mac-mini-observability.md`.
