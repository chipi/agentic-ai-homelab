# Pillar 2 — Local AI infrastructure

The self-hosted LLM stack on a single DGX-class box, reached over
Tailscale.

> **Status: v0.1 partial.** Observability layer is real and templated
> (`infra/observability/`). vLLM and LibreChat composes are placeholders
> for v0.2.

## The stack (target state)

```
+--------------------------------------------------------------------+
|  Tailnet (encrypted transport, ACL'd ports)                        |
|                                                                    |
|  laptop  --opencode-->                              :9000  vLLM    |
|  phone   --LibreChat web-->                         :3080  Lib     |
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
|    librechat/                   <-- mobile-friendly multi-model UI |
|                                                                    |
|  Other services already on box:                                    |
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
Plus **3080** if mobile via LibreChat is enabled.
Plus optionally **3000** (Open WebUI), **8080** (cAdvisor UI), **12345**
(Alloy admin UI) if local browsing is wanted (none required).

## What's in this pillar

### `infra/vllm/` — vLLM compose template *(v0.2)*

Hardened compose for vLLM serving on NVIDIA GB10-class hardware. The
template captures the decisions from `docs/history/0002-decisions.md`:

- `--api-key` enabled (`buddy-is-the-king` placeholder — change it)
- `--revision <sha>` pinned to known-good model snapshot
- `VLLM_DISABLE_TORCH_COMPILE=1` (GB10 Blackwell hot-fix)
- `vllm-cache` mount (avoids CUDA-graph recompile on cold start)
- `env_file` for `HF_TOKEN` (gated-model support)
- Tool-call parser configured for Qwen3-Coder family
- Log rotation (`50m × 3`)
- Healthcheck with 10-min start_period
- Image-bump sibling-file convention (`docker-compose.yml.<newtag>`)

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
(vLLM).

See `infra/observability/README.md` for setup.

### `infra/librechat/` — LibreChat slim deploy *(v0.2)*

3-container deploy: `api + mongodb + meilisearch`. Skips nginx (tailnet
handles encryption) and RAG containers (deferred).

Pre-wires vLLM coder-next as a custom endpoint via `librechat.yaml`.
Optional RAG / MCP / multi-provider additions documented in
`infra/librechat/README.md` (v0.2).

## Operational notes

### GPU contention

`gpu-memory-utilization=0.92` on vLLM coder-next is "I own the GPU" mode.
It cannot coexist with:
- The autoresearch vLLM (`infra/dgx/vllm-autoresearch/` in
  podcast_scraper, runs at `gpu-memory-utilization=0.60` on port 8003)
- Ollama (uses GPU when serving)
- pyannote / whisper services if they're under load

In practice it's one-or-the-other. The mode-swap helper script (open
thread, see `docs/wip/NEXT_STEPS.md`) automates the toggle.

### Image pinning

All NVIDIA vLLM images are tagged `:25.11-py3`, `:26.05-py3`, etc. Pin
explicitly — `:latest` will drift and break model-arch compatibility
unpredictably. The `docker-compose.yml.<newtag>` sibling-file pattern
lets you stage an upgrade without touching the live config:
1. Copy current → `docker-compose.yml.<oldtag>.bak`
2. Edit live → new tag
3. `docker compose up -d`
4. Validate; revert by `cp` if needed

### Tailscale ACL

Only inbound port that needs an ACL hole: **9000** (vLLM).
Optionally **3080** (LibreChat web).

All observability traffic is *outbound* HTTPS to Grafana Cloud — no ACL
change needed.

### Disk budget

HF model cache: `/opt/llm-models/huggingface/`. Models:
- `Qwen/Qwen3-Coder-Next-FP8` — ~75 GB (the working set)
- `Qwen3.6-35B-A3B` — ~67 GB (autoresearch path)
- `Qwen2.5-7B-Instruct` — ~14 GB (openwebui demo path)

Rule: keep FP8 over BF16 of the same model on Blackwell (FP8 is ~1.5-2×
throughput at <1% quality loss for code).
