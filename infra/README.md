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
| **DGX** | tailnet `dgx-llm-1` (100.69.49.126) | GPU/LLM inference services (Ollama, MOSS, Whisper, diarization, vLLM) + DCGM/cAdvisor exporters + `gpu-mode-swap`. SSH via Tailscale: `ssh markodragoljevic@dgx-llm-1` (personal) / `ssh ops@dgx-llm-1` (agents). |
| **prod-podcast** | public VPS | The podcast apps (operator API + player) + a node Alloy shipping metrics/logs to the mini + a Caddy edge that tunnels the public endpoints (GlitchTip, Umami, orrery beacon). |

**Network:** everything internal is **tailnet-only** — services bind to the mini's
tailnet IP (`100.87.33.61`) or the device name `homelab`, never `127.0.0.1` or a
public interface. The *only* public surface is what the prod-podcast Caddy edge
deliberately tunnels (e.g. `telemetry.closelistening.app` → GlitchTip).

## Systems

| System | Purpose | Host | Access | Creds | README |
|---|---|---|---|---|---|
| **observability** | Metrics/logs/traces backend — Grafana + VictoriaMetrics/Logs/Traces + Alloy | mini | Grafana `https://grafana.tail6d0ed4.ts.net` · VM `https://vm.tail6d0ed4.ts.net` · VLogs `https://vlogs.tail6d0ed4.ts.net` · VTraces `https://vtraces.tail6d0ed4.ts.net` | `backend/.env` | [observability/](observability/README.md) |
| **glitchtip** | Self-hosted error tracking (Sentry-compatible) | mini | admin UI `https://glitchtip.tail6d0ed4.ts.net` · public ingest `telemetry.closelistening.app` · ingest port `:8090` (loopback) | `glitchtip/.env` | [glitchtip/](glitchtip/README.md) |
| **umami** | Privacy-friendly web analytics | mini | admin `https://umami.tail6d0ed4.ts.net` · ingest port `:3001` (loopback) | `~/umami/.env` | [umami/](umami/README.md) |
| **langfuse** | LLM tracing / cost observability | mini | web UI `https://langfuse.tail6d0ed4.ts.net` · ingest `:4000` (internal) | `langfuse/.env` | [langfuse/](langfuse/README.md) |
| **litellm** | Production LLM gateway — provider-swappable aliases + per-consumer budget keys | mini | web UI `https://litellm.tail6d0ed4.ts.net/ui/` · ingest `:4001/v1` (internal) | `litellm/.env` | [litellm/](litellm/README.md) |
| **delivery** | Outbound comms — multi-tenant digest email (Resend) + self-hosted Web Push | mini | tailnet-only, egress-only; loopback `/metrics` `:9110-9112` | `delivery/.env` | [delivery/](delivery/README.md) |
| **homelab-home** | Tailnet start page (mini · DGX · prod columns) | mini | `https://hub.tail6d0ed4.ts.net` | reads other stacks' `.env` | [homelab-home/](homelab-home/README.md) |
| **reverse-proxy** | Per-service Tailscale nodes (Caddy) serving HTTPS for observability + admin UIs | mini | web nodes `{grafana,glitchtip,umami,langfuse,litellm,hub,vm,vlogs,vtraces}.tail6d0ed4.ts.net` | — | [reverse-proxy/](reverse-proxy/README.md) |
| **mini-metrics** | Mac-mini host metrics → VictoriaMetrics | mini | pushes to VM `:8428` | — | [mini-metrics/](mini-metrics/README.md) |
| **dgx-scrape** | Pulls DGX GPU/app metrics + TCP health over tailnet → VM | mini | pushes to VM `:8428` | — | [dgx-scrape/](dgx-scrape/README.md) |
| **ci-ops-poller** | Pulls GitHub Actions runs (CI / drift / drill) → VictoriaLogs for CI health + DORA | mini | pushes to VLogs `:9428` | `ci-ops-poller/.env` | [ci-ops-poller/](ci-ops-poller/README.md) |
| **dgx** | DGX-host operator scripts (`gpu-mode-swap`) + service map | DGX | Tailscale SSH (see above) | — | [dgx/](dgx/README.md) |
| **vllm** | Local vLLM inference stacks (coder / autoresearch) | DGX | `:8003` / `:9000` `/v1` (GPU-mode gated) | — | [vllm/](vllm/README.md) |

Per-folder rules layer on top of the repo-root [`AGENTS.md`](../AGENTS.md); see
[`infra/AGENTS.md`](AGENTS.md), [`infra/dgx/AGENTS.md`](dgx/AGENTS.md),
[`infra/vllm/AGENTS.md`](vllm/AGENTS.md).

## How they connect

```
  DGX (dgx-llm-1, 100.69.49.126)      Mac mini (homelab / 100.87.33.61)
  ├─ Ollama/MOSS/Whisper/…    ─TS─→   ├─ dgx-scrape ─┐
  ├─ DCGM :9400, cAdvisor :8080 ─TS─→ ├─ mini-metrics ┤→ VictoriaMetrics :8428
  └─ gpu-mode-swap                    │                ├→ VictoriaLogs   :9428  ← Alloy
                                      │                └→ VictoriaTraces :10428 ← OTel
  prod-podcast (VPS)                  ├─ Grafana :3000  (reads all three)
  ├─ operator API + player  ─OTel/logs→ ├─ GlitchTip :8090, Umami :3001, Langfuse :4000
  └─ Caddy edge ──tunnels──→ public    └─ homelab-home :8888 (links every board)
```

## Access basics

- **SSH to the mini:** `ssh -i ~/.ssh/homelab_mini -o IdentitiesOnly=yes homelab`
  (Docker CLI is at `/usr/local/bin/docker`).
- **SSH to the DGX:** `ssh markodragoljevic@dgx-llm-1` (personal) or
  `ssh ops@dgx-llm-1` (agents / automation). Keyless Tailscale SSH over the tailnet.
- **Reach a service:** use the tailnet name/IP + port from the table (e.g.
  `http://homelab:3000` for Grafana). Loopback won't work — services bind the
  tailnet IP.
- **Run a stack:** `cd infra/<system> && docker compose up -d` (in place; reads
  the local `.env`). Secrets live in each stack's `.env` — **gitignored, never
  committed** (see the repo-root and `infra/` `AGENTS.md`).

## Rebuilding the mini from scratch

The mini is an **Intel** Mac (`x86_64`, Homebrew at `/usr/local`) — the CPU-temp
reader (`osx-cpu-temp`) reads the Intel SMC, so this rebuild is Intel-specific.

### Prerequisites (the from-bare-macOS layer the scripts assume)

These come **before** the two scripts. Everything else is captured as code; these
are the OS-level pieces a fresh install needs first. Do them top to bottom:

| # | Prereq | Install | Why |
|---|---|---|---|
| 1 | **Xcode Command Line Tools** | `xcode-select --install` | gives `git` + `make` — needed to clone the repo and build `osx-cpu-temp` |
| 2 | **Homebrew** | the [brew.sh](https://brew.sh) install one-liner | the package manager everything below rides on |
| 3 | **Brew packages** | `brew bundle --file infra/Brewfile` | colima (container engine, QEMU-backed), node_exporter, sops, age — see [`Brewfile`](Brewfile). `mini-setup.sh` runs this for you. |
| 4 | **Tailscale** | Mac **App Store** → sign in, `tailscale up` | the tailnet everything binds to. It's the App Store GUI build (root-owned), **not** a brew cask — that's why it's not in the Brewfile. |
| 5 | **age key** | drop the private key at `~/.config/sops/age/keys.txt` | `bootstrap.sh` decrypts `secrets.sops.env` with it — the one secret no script can regenerate; restore it from your password manager / backup. |

### Then the two idempotent scripts

Both run **in-place from this checkout** (no copy-outs), so `git pull` ships updates:

```sh
git clone <repo> ~/agentic-ai-homelab && cd ~/agentic-ai-homelab
./infra/observability/bootstrap.sh   # CONTAINERS — Grafana + Victoria* + GlitchTip + Langfuse + Umami
                                     #   (needs colima running, tailscale up, sops+age+age-key from above)
./infra/mini-setup.sh                # HOST bits — runs `brew bundle`, then installs node_exporter,
                                     #   the launchd collectors (mini-metrics / dgx-scrape / ci-ops-poller),
                                     #   the CPU-temp reader, and the Grafana alert-provisioning reload
```

Then stage the gitignored per-stack secrets (each dir's `.env` — see its
`.env.example`; the collectors' too, e.g. `ci-ops-poller/.env` `GITHUB_TOKEN`)
and re-run the relevant step. The `homelab-home` landing page comes up with `cd
infra/homelab-home && ./gen.sh && docker compose up -d`.

**Still not covered** (managed by their own subprojects, not this rebuild): the
`bugfix-metrics` / `fleetd` launchd jobs.

## Self-service — what you can do yourself, no ask needed

Don't wait for someone to run a command you can run. These are **read-only or
reversible** — do them directly, no approval:

| I want to… | Do this |
|---|---|
| See what's running on the hub | `ssh -i ~/.ssh/homelab_mini -o IdentitiesOnly=yes homelab '/usr/local/bin/docker ps'` |
| Open a dashboard | Grafana at `https://grafana.tail6d0ed4.ts.net` (tailnet) |
| Query a metric | `curl -s "http://homelab:8428/api/v1/query?query=up"` |
| Search logs | VictoriaLogs `https://vlogs.tail6d0ed4.ts.net` (LogsQL) |
| See traces | VictoriaTraces `https://vtraces.tail6d0ed4.ts.net` (or via Grafana) |
| Check errors / LLM traces | GlitchTip `https://glitchtip.tail6d0ed4.ts.net` · Langfuse `https://langfuse.tail6d0ed4.ts.net` |
| Snapshot the DGX/GPU state | the `dgx-status` skill (read-only) |
| Know which vLLM owns the GPU | the `gpu-mode` skill, read-only: `~/bin/gpu-mode-swap.sh --mode-only` |
| Resolve a service's real URL | the `homelab-endpoint` skill, or the tables above |

**These DO need an ask first** — shared-state or destructive, one approval per
invocation (see the repo-root `AGENTS.md`): switching GPU mode
(`gpu-mode-swap.sh --mode`), bringing any stack `up`/`down`, `docker compose
down -v`, migrations, anything mutating the DGX or a shared dataset. Check,
diagnose, and stage the exact command yourself — then get the one-word go before
the mutating step. The rule is *"don't wait for someone to look for you,"* not
*"change shared infra without approval."*

> **The DGX is not the hub.** Metrics, logs, traces, dashboards, error
> tracking, LLM traces — all live on the **Mac mini** (`homelab`), not the DGX.
> The DGX only runs GPU/LLM inference and exposes exporters that the mini pulls
> over the LAN. If you're reaching for the DGX to see a dashboard, you want
> `homelab`.

## Dashboards & alerts

The Grafana dashboards and alert rules are provisioned-as-code under
[`observability/backend/grafana/`](observability/backend/grafana/):
- **Dashboards:** [`dashboards/README.md`](observability/backend/grafana/dashboards/README.md)
  (global) + a README per folder (Homelab / Production Infra / Podcast Operator /
  Podcast Player) explaining that folder's goal and every board.
- **Alerts:** [`provisioning/alerting/README.md`](observability/backend/grafana/provisioning/alerting/README.md)
  — every rule, its threshold and intent, contact points, and notification policies.
