# `infra/` — homelab systems

Every self-hosted system in the homelab, run **from this repo in place** (the
compose stacks read a repo-root or stack-local `.env`; you `docker compose up`
from the stack's own directory — you don't copy files to `~/docker-compose/`).
This file is the index: what each system is, where it runs, how to reach it, and
where its own README lives.

Ties into the global docs at
[Pillar 2 — Local AI infrastructure](https://github.com/chipi/agentic-ai-homelab/blob/main/docs/local-ai-infra.md).

## The three hosts

| Host | Name / address | Runs |
|---|---|---|
| **Mac mini** | `homelab` · tailnet `100.87.33.61` | The observability backend (Grafana + VictoriaMetrics/Logs/Traces), GlitchTip, Umami, Langfuse, the landing page, and the host/DGX collectors. The always-on hub. |
| **DGX** | LAN `192.168.1.111` · label `dgx-llm-1` | GPU/LLM inference services (Ollama, MOSS, Whisper, diarization, vLLM) + DCGM/cAdvisor exporters + `gpu-mode-swap`. **No SSH yet** — reached only over the LAN by the mini's collectors. |
| **prod-podcast** | public VPS | The podcast apps (operator API + player) + a node Alloy shipping metrics/logs to the mini + a Caddy edge that tunnels the public endpoints (GlitchTip, Umami, orrery beacon). |

**Network:** everything internal is **tailnet-only** — services bind to the mini's
tailnet IP (`100.87.33.61`) or the device name `homelab`, never `127.0.0.1` or a
public interface. The *only* public surface is what the prod-podcast Caddy edge
deliberately tunnels (e.g. `telemetry.closelistening.app` → GlitchTip).

## Systems

| System | Purpose | Host | Access | Creds | README |
|---|---|---|---|---|---|
| **observability** | Metrics/logs/traces backend — Grafana + VictoriaMetrics/Logs/Traces + Alloy | mini | Grafana `homelab:3000` · VM `:8428` · VLogs `:9428` · VTraces `:10428` | `backend/.env` | [observability/](observability/README.md) |
| **glitchtip** | Self-hosted error tracking (Sentry-compatible) | mini | `homelab:8090` · public `telemetry.closelistening.app` | `glitchtip/.env` | [glitchtip/](glitchtip/README.md) |
| **umami** | Privacy-friendly web analytics | mini | admin `homelab:3001` | `~/umami/.env` | [umami/](umami/README.md) |
| **langfuse** | LLM tracing / cost observability | mini | `homelab:4000` | `langfuse/.env` | [langfuse/](langfuse/README.md) |
| **homelab-home** | Tailnet start page (mini · DGX · prod columns) | mini | `homelab:8888` | reads other stacks' `.env` | [homelab-home/](homelab-home/README.md) |
| **mini-metrics** | Mac-mini host metrics → VictoriaMetrics | mini | pushes to VM `:8428` | — | [mini-metrics/](mini-metrics/README.md) |
| **dgx-scrape** | Pulls DGX GPU/app metrics + TCP health over LAN → VM | mini | pushes to VM `:8428` | — | [dgx-scrape/](dgx-scrape/README.md) |
| **dgx** | DGX-host operator scripts (`gpu-mode-swap`) + service map | DGX | LAN `192.168.1.111` (no SSH yet) | — | [dgx/](dgx/README.md) |
| **vllm** | Local vLLM inference stacks (coder / autoresearch) | DGX | `:8003` / `:9000` `/v1` (GPU-mode gated) | — | [vllm/](vllm/README.md) |

Per-folder rules layer on top of the repo-root [`AGENTS.md`](../AGENTS.md); see
[`infra/AGENTS.md`](AGENTS.md), [`infra/dgx/AGENTS.md`](dgx/AGENTS.md),
[`infra/vllm/AGENTS.md`](vllm/AGENTS.md).

## How they connect

```
  DGX (192.168.1.111)                Mac mini (homelab / 100.87.33.61)
  ├─ Ollama/MOSS/Whisper/…    ─LAN→   ├─ dgx-scrape ─┐
  ├─ DCGM :9400, cAdvisor :8080 ─LAN→ ├─ mini-metrics ┤→ VictoriaMetrics :8428
  └─ gpu-mode-swap                    │                ├→ VictoriaLogs   :9428  ← Alloy
                                      │                └→ VictoriaTraces :10428 ← OTel
  prod-podcast (VPS)                  ├─ Grafana :3000  (reads all three)
  ├─ operator API + player  ─OTel/logs→ ├─ GlitchTip :8090, Umami :3001, Langfuse :4000
  └─ Caddy edge ──tunnels──→ public    └─ homelab-home :8888 (links every board)
```

## Access basics

- **SSH to the mini:** `ssh -i ~/.ssh/homelab_mini -o IdentitiesOnly=yes homelab`
  (Docker CLI is at `/usr/local/bin/docker`).
- **Reach a service:** use the tailnet name/IP + port from the table (e.g.
  `http://homelab:3000` for Grafana). Loopback won't work — services bind the
  tailnet IP.
- **Run a stack:** `cd infra/<system> && docker compose up -d` (in place; reads
  the local `.env`). Secrets live in each stack's `.env` — **gitignored, never
  committed** (see the repo-root and `infra/` `AGENTS.md`).

## Dashboards & alerts

The Grafana dashboards and alert rules are provisioned-as-code under
[`observability/backend/grafana/`](observability/backend/grafana/):
- **Dashboards:** [`dashboards/README.md`](observability/backend/grafana/dashboards/README.md)
  (global) + a README per folder (Homelab / Production Infra / Podcast Operator /
  Podcast Player) explaining that folder's goal and every board.
- **Alerts:** [`provisioning/alerting/README.md`](observability/backend/grafana/provisioning/alerting/README.md)
  — every rule, its threshold and intent, contact points, and notification policies.
