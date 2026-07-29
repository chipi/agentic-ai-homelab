# Pillar 2 — Local AI infrastructure

The self-hosted stack, reached over Tailscale. It spans **three hosts** —
don't assume "one box":

- **DGX** (`dgx-llm-1`, tailnet `100.69.49.126`) — the GPU/LLM inference box:
  vLLM, Ollama, and the podcast ML services. SSH via Tailscale:
  `ssh markodragoljevic@dgx-llm-1` (personal) / `ssh ops@dgx-llm-1` (agents).
- **Mac mini** (`homelab`, tailnet `100.87.33.61`) — the **always-on hub**.
  Runs the entire observability backend (Grafana + VictoriaMetrics/Logs/
  Traces), plus GlitchTip, Langfuse, Umami, and the landing page. This is
  where metrics, logs, traces, and dashboards live — **not the DGX**.
- **prod-podcast** (public VPS) — the podcast apps + a collector that ships
  telemetry back to the mini.

> **Where does X run? → [`infra/README.md`](https://github.com/chipi/agentic-ai-homelab/blob/main/infra/README.md)**
> is the authoritative index (three-hosts table + every system + how they
> connect + how to reach each). This pillar is the narrative; that file is
> the map. When in doubt about a host, trust the map.

> **Status: v0.2.** `infra/vllm/` (template + operator deploys) runs on the
> DGX; the observability backend (`infra/observability/backend/`) and the
> app services run on the Mac mini. Operational moves covered by recipes in
> `docs/recipes/`.

## Why this shape

Single GPU. Single operator. Tailnet-only access. Three honest constraints,
and the stack falls out of them:

- **One GPU** → workloads are *mutex*, not concurrent. The coder vLLM and
  the autoresearch vLLM can't share. Treat that as a feature: the
  `gpu-mode-swap` recipe makes the toggle explicit instead of
  whoever-grabbed-it-first chaos.
- **One operator** → no internal users, no SSO, no auth beyond a single
  shared `--api-key`. Tailscale handles identity at the network layer.
  Anything fancier than that is overhead.
- **Tailnet-only** → for the DGX, no public ingress and no auth beyond the
  tailnet. Telemetry no longer leaves the tailnet at all: it ships to the
  **self-hosted** observability backend on the Mac mini (`homelab`), not to
  any cloud. (There is no Grafana Cloud anymore — see ADR-0005/0006.) The
  one deliberate public surface lives on the prod-podcast VPS's Caddy edge,
  not here.

What's NOT in this pillar (and why):
- **Self-hosted multi-model chat UIs.** Tried in genesis, dropped after
  evaluation (D-0007). Chatbox covers the only real use case (phone access
  to vLLM) with zero deploy cost.
- **Multi-host *orchestration*.** The homelab spans a few hosts (DGX for
  GPU, Mac mini for the always-on hub, a VPS for the podcast apps), but
  there's no orchestration layer — no k8s, no Swarm. Each host runs its own
  `docker compose` stacks in place. The topology is in
  [`infra/README.md`](https://github.com/chipi/agentic-ai-homelab/blob/main/infra/README.md);
  the coordination is a human.
- **Cloud LLM API patterns.** Different problem, different pillar — see
  [`cloud-ai-workflow.md`](cloud-ai-workflow.md).

## The stack

Two boxes carry the AI stack, joined over the tailnet. The DGX **generates**
signals (GPU, containers, app metrics); the Mac mini **stores and shows**
them. Nothing on the DGX renders a dashboard — go to the mini for that.

```
  laptop / phone ──opencode · Chatbox──→ vLLM :9000 (on the DGX)

+----------------------------------+     +-----------------------------------+
|  DGX  (dgx-llm-1, GPU box)        |     |  Mac mini  (homelab — the hub)    |
|  tailnet 100.69.49.126 · SSH OK   |     |  tailnet 100.87.33.61 · always-on |
|                                   |     |                                   |
|  Inference (this repo):           |     |  Observability backend:           |
|    vllm coder-next   :9000        |     |    VictoriaMetrics :8428  (metrics)|
|    vllm openwebui    :3000  (mutex)|    |    VictoriaLogs    :9428  (logs)  |
|                                   |     |    VictoriaTraces  :10428 (traces)|
|  Already on box (not this repo):  |     |    Grafana         :3000  (view)  |
|    ollama            :11434       |     |                                   |
|    pyannote/whisper/moss  8001-4  |     |  Apps on the hub:                 |
|                                   |     |    GlitchTip :8090  (errors)      |
|  Exporters (scraped over tailnet):|     |    Langfuse  :4000  (LLM traces)  |
|    DCGM   :9400   (GPU)   ────────┼──┐  |    Umami     :3001  (web analytics)|
|    cAdvisor :8080 (containers) ───┼─┐│  |    homelab-home :8888 (start page)|
+----------------------------------+ ││  |                                   |
                                     ││  |  Collectors (launchd on the mini):|
   prod-podcast (VPS) ──OTel/logs────┼┼─→│    dgx-scrape  ← pulls DGX exporters|
                                     └┴─→│    mini-metrics ← mini host metrics |
                                         └───────────────────────────────────+
```

FW / ACL ports to remember: **9000** (vLLM, on the DGX) and, on the mini,
**3000** (Grafana) · **8428/9428/10428** (VictoriaMetrics/Logs/Traces) ·
**8090** (GlitchTip) · **4000** (Langfuse) · **3001** (Umami). All bind the
tailnet, none are public (the podcast VPS edge is the only public surface).

## What's in this pillar

### Systems index — every self-hosted service *(start here)*

The canonical, per-system reference lives next to the code at
[`infra/README.md`](https://github.com/chipi/agentic-ai-homelab/blob/main/infra/README.md):
the three hosts (Mac mini `homelab` / DGX / prod-podcast VPS), a table of every
system (purpose · host · access · creds · link to its own README), how they
connect, and access basics. Each system (`observability`, `glitchtip`, `umami`,
`langfuse`, `homelab-home`, `mini-metrics`, `dgx-scrape`, `dgx`, `vllm`) carries
its own README covering access + usage.

Observability is documented as-code:
- **Dashboards** — [`dashboards/README.md`](https://github.com/chipi/agentic-ai-homelab/blob/main/infra/observability/backend/grafana/dashboards/README.md)
  (global) + a README per Grafana folder (Homelab / Production Infra / Podcast
  Operator / Podcast Player) stating that folder's goal and every board.
- **Alerts** — [`provisioning/alerting/README.md`](https://github.com/chipi/agentic-ai-homelab/blob/main/infra/observability/backend/grafana/provisioning/alerting/README.md)
  — every rule, threshold, and intent; contact points; policies.

### `infra/vllm/` — template + operator deploys *(v0.2, real)*

Three subdirs:

- **`template/`** — the canonical hardened compose for vLLM serving on
  NVIDIA GB10-class hardware. Copy this when standing up a new stack.
- **`coder-next/`** — the operator's daily-driver deploy
  (`Qwen3-Coder-Next-FP8` on port 9000) + the image-bump sibling
  (`.26.05-py3`).
- **`openwebui/`** — alt path: Qwen 2.5-7B served via vLLM behind Open
  WebUI on port 3000. Mutex with `coder-next` at runtime (same GPU).

The template captures the decisions from `docs/history/0002-decisions.md`:

- `--api-key` enabled (`buddy-is-the-king` placeholder — change it)
- `--revision <sha>` pinned to known-good model snapshot
- `VLLM_DISABLE_TORCH_COMPILE=1` (GB10 Blackwell hot-fix)
- `vllm-cache` mount (avoids CUDA-graph recompile on cold start)
- `env_file` for `HF_TOKEN` (gated-model support)
- Tool-call parser configured for Qwen3-Coder family
  (`--tool-call-parser qwen3_coder` + `--enable-auto-tool-choice`)
- Log rotation (`50m × 3`)
- Healthcheck with 10-min `start_period` (cold start can take ~5 min
  on first revision-pull + CUDA-graph compile)
- Image-bump sibling-file convention (`docker-compose.yml.<newtag>`) —
  stage an upgrade without touching the live config

See [`infra/vllm/template/README.md`](https://github.com/chipi/agentic-ai-homelab/blob/main/infra/vllm/template/README.md)
for model selection, port + GPU mem tuning, and the image-bump dance.

### `infra/observability/` — self-hosted metrics/logs/traces *(real)*

Fully self-hosted on the **Mac mini** (`homelab`) — there is no Grafana
Cloud. Two layers:

- **Backend** (`infra/observability/backend/`, on the mini) — the storage +
  view plane: **VictoriaMetrics** (:8428, metrics), **VictoriaLogs** (:9428),
  **VictoriaTraces** (:10428, OTLP), and **Grafana OSS** (:3000) with
  dashboards + alerts provisioned as code.
- **Collection** — how signals reach the backend:
  - The **mini** runs a containerized Alloy (`hosts/homelab/`) for its own
    host metrics, plus two launchd loops: `mini-metrics/` (native macOS
    signals) and `dgx-scrape/`.
  - The **DGX** has no working collector on it yet (SSH now available, but
    push-collector not deployed). So `dgx-scrape/` on the mini **pulls**
    the DGX's DCGM (:9400) and cAdvisor (:8080) exporters over the LAN every
    20s and pushes them into VictoriaMetrics, labelled `instance=dgx-llm-1`.
    This is the interim model; a DGX push-collector (node-exporter + Alloy)
    is now possible but not yet deployed. The DGX ships no logs yet.
  - The **prod-podcast VPS** runs its own Alloy that ships metrics/logs to
    the mini over the tailnet.

Dashboards and alerts live as code under
[`backend/grafana/`](https://github.com/chipi/agentic-ai-homelab/blob/main/infra/observability/backend/grafana/),
organized into Grafana folders (Homelab / Production Infra / Podcast
Operator / Podcast Player) — see the per-folder READMEs for what each board
covers.

Bring-up walkthrough: **[`recipes/mac-mini-observability.md`](recipes/mac-mini-observability.md)**
(the current, self-hosted procedure). Naming/endpoint conventions:
[`recipes/observability-endpoints.md`](recipes/observability-endpoints.md).
Config-layer details: [`infra/observability/README.md`](https://github.com/chipi/agentic-ai-homelab/blob/main/infra/observability/README.md).

> The older [`recipes/observability-boot.md`](recipes/observability-boot.md)
> describes the retired Grafana-Cloud-on-the-DGX design and is **superseded**
> — don't follow it.

### Ollama — supporting role *(not deployed by this repo)*

Ollama already runs on the DGX (`:11434`) and stays there. It's not
deployed by this repo, but Pillar 2 covers it because it shares the GPU
and shows up in dashboards.

What Ollama is for in this setup:

- **Model catalog** — `ollama pull` is the cheapest way to try a new
  model without writing a compose.
- **Smaller models** — Qwen 2.5-7B, Llama 3.2-3B, etc. Anything that
  doesn't need vLLM's throughput.
- **Background availability** — when the vLLM coder-next is *down*
  (mid-swap, image bump, model download), Ollama is the fallback for
  opencode / Claude Code via OpenAI-compatible API.

What Ollama is *not* for:
- The coder vLLM workload. Qwen3-Coder-Next-FP8 needs vLLM throughput +
  tool-call parsing. Ollama lacks the right tool-call schema and saturates
  the GPU less efficiently.
- Production-style serving with metrics. Per Level-1 observability
  decision, Ollama shows up as "model inventory + RAM gauges" only.

### Mobile access *(out of scope)*

No self-hosted UI in this pillar. If phone access to the local vLLM is
wanted, **Chatbox** (OpenAI-compatible client, mobile app, no deploy)
points at `http://<dgx-host>.<your-tailnet>.ts.net:9000` and works
directly. Anything richer (multi-model chat, RAG, MCP) is out of scope —
see [`docs/wip/NEXT_STEPS.md`](wip/NEXT_STEPS.md) "Not in scope".

## Operational notes

### GPU contention

`gpu-memory-utilization=0.75` on vLLM coder-next is "I own the GPU" mode.
The default is 0.75 (not 0.92) because GB10 has 121 GB of **unified**
CPU+GPU memory — pushing to 0.92 grabs ~112 GB and starves the host /
sibling services. Override transiently via `${VLLM_GPU_MEM_UTIL}` on a
quieter box. Even at 0.75 it cannot coexist with:

- The autoresearch vLLM (`infra/dgx/vllm-autoresearch/` in
  podcast_scraper, runs at `gpu-memory-utilization=0.60` on port 8003)
- Ollama actively serving a request
- pyannote / whisper services under load

In practice it's one-at-a-time. The toggle is scripted, not muscle
memory — see [`recipes/gpu-mode-swap.md`](recipes/gpu-mode-swap.md) for
the three-mode (`code` / `research` / `idle`) script + recipe.

### Image pinning

All NVIDIA vLLM images are tagged `:25.11-py3`, `:26.05-py3`, etc. Pin
explicitly — `:latest` will drift and break model-arch compatibility
unpredictably. The `docker-compose.yml.<newtag>` sibling-file pattern
lets you stage an upgrade without touching the live config:

1. Copy current → `docker-compose.yml.<oldtag>.bak`
2. Edit live → new tag
3. `docker compose up -d`
4. Validate; revert by `cp` if needed

Full walkthrough in
[`infra/vllm/template/README.md`](https://github.com/chipi/agentic-ai-homelab/blob/main/infra/vllm/template/README.md)
→ "Image-bump dance".

### Tailscale ACL

DGX inbound port that needs an ACL hole: **9000** (vLLM).
Also **UDP 60000-61000** if mosh is used for the operator session (see
[`recipes/dgx-terminal-dashboard.md`](recipes/dgx-terminal-dashboard.md)).

Observability is now **tailnet-internal**, not outbound-to-cloud: the mini's
`dgx-scrape` reaches the DGX exporters (**:9400** DCGM, **:8080** cAdvisor)
over the LAN, and the mini's backend ports (**:3000** Grafana, **:8428/9428/
10428** VictoriaMetrics/Logs/Traces) are reachable over the tailnet. Grant
those on the tailnet ACL; nothing here talks to a cloud.

### Disk budget

HF model cache: `/opt/llm-models/huggingface/`. Working set of models:

| Model | Size | Used by |
|---|---|---|
| `Qwen/Qwen3-Coder-Next-FP8` | ~75 GB | coder-next vLLM |
| `Qwen3.6-35B-A3B` | ~67 GB | autoresearch vLLM (podcast_scraper) |
| `Qwen2.5-7B-Instruct` | ~14 GB | openwebui demo path |

Rule: prefer FP8 over BF16 of the same model on Blackwell. FP8 is
~1.5-2× throughput at <1% quality loss for code. Bf16 stays only if
the model doesn't have an FP8 release.

### CUDA-graph cache

The shared `vllm-cache` volume (`/opt/llm-models/vllm-cache` on host)
holds compiled CUDA graphs across compose stops/starts. Without it,
every `docker compose up` pays a 5-10 minute recompile penalty. The
infra/vllm/template/ mounts this by default.

### Operator terminal dashboard

Day-to-day "what's the DGX doing" view runs in a 4-pane tmux session
(nvitop / btop / ctop / custom llm-status), reached over mosh so it
survives laptop sleep. Full setup, file contents, troubleshooting, and
keyboard cheat sheet in
[`recipes/dgx-terminal-dashboard.md`](recipes/dgx-terminal-dashboard.md).

One-liner to connect:

```bash
mosh <dgx-host>.<your-tailnet>.ts.net -- tmux attach -t dgx
```

## Recipes that operate this stack

| Recipe | When |
|---|---|
| [DGX terminal dashboard](recipes/dgx-terminal-dashboard.md) | Daily — your `dgx` ⏎ moment |
| [GPU mode-swap](recipes/gpu-mode-swap.md) | Every time you switch between coder/research/idle |
| [Mac mini → observability host](recipes/mac-mini-observability.md) | Standing up / re-checking the self-hosted backend |
| [Observability endpoints](recipes/observability-endpoints.md) | Looking up the `homelab` service names/ports |

The recipes are the operator-facing surface. The compose templates in
`infra/` are the artifact; the recipes are how you actually use them.

## Self-service — what you can do yourself, no ask needed

Agents (and humans) too often stall waiting for someone to run a command
that they can run themselves. These are **read-only or reversible** and need
no approval. Do them directly:

| I want to… | Do this |
|---|---|
| See what's running on the hub | `ssh -i ~/.ssh/homelab_mini -o IdentitiesOnly=yes homelab '/usr/local/bin/docker ps'` |
| Open a dashboard | Grafana at `http://homelab:3000` (tailnet) |
| Query a metric | `curl -s 'http://homelab:8428/api/v1/query?query=up'` |
| Search logs | VictoriaLogs at `http://homelab:9428` (LogsQL) |
| Check GPU / DGX state | the [`dgx-status`](recipes/dgx-terminal-dashboard.md) skill (read-only snapshot) |
| Know which vLLM owns the GPU | the `gpu-mode` skill (read-only check) |
| Find a service's real URL | the `homelab-endpoint` skill, or [`infra/README.md`](https://github.com/chipi/agentic-ai-homelab/blob/main/infra/README.md) |

**Where it *does* need an ask** — because it's shared-state or destructive:
switching GPU mode (`gpu-mode-swap`), bringing a stack `up`/`down`, anything
that mutates the DGX or a shared dataset. Check, diagnose, and prepare the
exact command yourself; get the one-word go before you run the mutating step.
The rule is "don't wait for someone to *look* for you," not "change shared
infra without approval."
