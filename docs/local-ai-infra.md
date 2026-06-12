# Pillar 2 — Local AI infrastructure

The self-hosted LLM stack on a single DGX-class box, reached over
Tailscale.

> **Status: v0.2.** Both deployables — `infra/vllm/` (template + two
> operator deploys: coder-next and openwebui) and `infra/observability/`
> (Alloy stack) — are real. Operational moves (boot, mode-swap, dashboard)
> covered by recipes in `docs/recipes/`.

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
- **Tailnet-only** → no public ingress, no Caddy / nginx / TLS termination
  to maintain. The only outbound flow is observability → Grafana Cloud
  (HTTPS, no ACL change).

What's NOT in this pillar (and why):
- **Self-hosted multi-model chat UIs.** Tried in genesis, dropped after
  evaluation (D-0007). Chatbox covers the only real use case (phone access
  to vLLM) with zero deploy cost.
- **Multi-host orchestration.** This is a homelab repo. One box.
- **Cloud LLM API patterns.** Different problem, different pillar — see
  [`cloud-ai-workflow.md`](cloud-ai-workflow.md).

## The stack

```
+--------------------------------------------------------------------+
|  Tailnet (encrypted transport, ACL'd ports)                        |
|                                                                    |
|  laptop  --opencode-->                              :9000  vLLM    |
|  phone   --Chatbox/OpenAI-compat-->                 :9000  vLLM    |
|                                                                    |
+--------------------------------------------------------------------+
                              |
                              v
+--------------------------------------------------------------------+
|  DGX (single GPU, e.g., GB10)                                      |
|                                                                    |
|  ~/docker-compose/                                                 |
|    vllm-Qwen3-Coder-Next/      <-- the coding LLM (port 9000)      |
|    vllm-openwebui/              <-- alt model + UI (mutex w/ above)|
|    grafana-alloy/               <-- observability                  |
|                                                                    |
|  Other services already on box (not deployed by this repo):        |
|    ollama (:11434)              <-- model catalog + smaller models |
|    pyannote (:8001)             <-- diarization                    |
|    whisper-openai (:8002)       <-- transcription                  |
|    speaches (:8000)             <-- alternative whisper            |
|                                                                    |
|  Observability:                                                    |
|    alloy → Grafana Cloud Prometheus (outbound HTTPS only)          |
|                                                                    |
+--------------------------------------------------------------------+
```

Single FW port to remember: **9000** (vLLM coding model).
Plus optionally **3000** (Open WebUI), **8080** (cAdvisor UI), **12345**
(Alloy admin UI) if local browsing is wanted (none required).

## What's in this pillar

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

### `infra/observability/` — Grafana Alloy stack *(v0.1, real)*

Four containers, all `host` network for trivial localhost scraping:

- **alloy** — single binary, declarative River config. Built-in unix
  exporter handles host metrics. Pushes to Grafana Cloud via
  `prometheus.remote_write`.
- **dcgm-exporter** — NVIDIA's first-party GPU exporter.
- **cadvisor** — per-container CPU/mem/restarts.
- **ollama-metrics** (NorskHelsenett) — sidecar for Ollama. Operates at
  Level 1 (passive — model inventory + RAM only, no client retargeting
  required).

Recommended Grafana dashboards: **1860** (node), **12239** (DCGM), **17296**
(vLLM), **893** (cAdvisor).

Boot walkthrough lives in [`recipes/observability-boot.md`](recipes/observability-boot.md);
config-layer details in
[`infra/observability/README.md`](https://github.com/chipi/agentic-ai-homelab/blob/main/infra/observability/README.md).

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

`gpu-memory-utilization=0.92` on vLLM coder-next is "I own the GPU" mode.
It cannot coexist with:

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

Only inbound port that needs an ACL hole: **9000** (vLLM).
Also **UDP 60000-61000** if mosh is used for the operator session (see
[`recipes/dgx-terminal-dashboard.md`](recipes/dgx-terminal-dashboard.md)).

All observability traffic is *outbound* HTTPS to Grafana Cloud — no ACL
change needed.

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
| [Observability boot](recipes/observability-boot.md) | Once per DGX rebuild / first install of Grafana Cloud |

The recipes are the operator-facing surface. The compose templates in
`infra/` are the artifact; the recipes are how you actually use them.
