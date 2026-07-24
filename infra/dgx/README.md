# DGX — host scripts + service map

**What it is:** operator scripts and the service inventory for the DGX-class GPU
box (`192.168.1.111`, label `dgx-llm-1`) that hosts the local LLM/inference
stack. This directory is **host tooling**, not a compose stack — the services
themselves are managed on the DGX; the telemetry that watches them is pushed from
the Mac mini (see [dgx-scrape](../dgx-scrape/README.md)).

## Where it runs

- **Host:** DGX, LAN `192.168.1.111`. **No SSH access yet** — the box is reached
  only over the LAN (exporter + app ports) by the mini's collectors. Anything
  needing a DGX shell is currently blocked.
- **Scripts** in [`bin/`](bin) run *on the DGX* (operator-invoked). The DGX also
  holds a **deploy-only** checkout of this repo — never author or commit there
  (see [`AGENTS.md`](AGENTS.md); the 2026-07-20 drift incident).

## Services on the DGX (as monitored)

The mini's [dgx-scrape](../dgx-scrape/README.md) TCP-health-checks these and
scrapes the exporters over the LAN:

| Service | Port | Notes |
|---|---|---|
| Ollama | 11434 | text LLM |
| Whisper | 8000 | ASR |
| Diarization (pyannote) | 8001 | exposes Prometheus `/metrics` (→ `job=pyannote-app`) |
| openai-whisper | 8002 | closes its port when crashed (honest down-signal) |
| MOSS | 8004 | exposes Prometheus `/metrics` (→ `job=moss-app`); saturates under load |
| cAdvisor | 8080 | container metrics (names absent, GH #1272) |
| DCGM | 9400 | GPU metrics |
| vLLM (coder / autoresearch) | 8003 / 9000 | GPU-mode gated — see [vllm](../vllm/README.md) |

## Usage — GPU mode coordination

One DGX GPU can't host the coder-next vLLM and the autoresearch vLLM at once
(both want ~90% VRAM → OOM). Coordinate with `gpu-mode-swap.sh` **before** hitting
any local vLLM endpoint:

```bash
~/bin/gpu-mode-swap.sh --mode-only     # → code | research | idle | BROKEN-BOTH
~/bin/gpu-mode-swap.sh code --json     # bring coder-next up
~/bin/gpu-mode-swap.sh research --json # bring autoresearch up
~/bin/gpu-mode-swap.sh idle --json     # both down
```

Always call by **absolute path** (the `gpu-mode` alias doesn't load in
non-interactive shells). Full contract (output modes, exit codes, env config,
sudo, failure modes): [`bin/README.md`](bin/README.md).

## Gotchas

- **No SSH yet** — LAN-only. Telemetry works (pull from the mini); anything
  interactive on the DGX is blocked until access is restored.
- **Deploy-only checkout** — commit on your workstation, push, then `git pull` on
  the DGX. Never leave an unpushed commit on the DGX ([`AGENTS.md`](AGENTS.md)).
- **Health = TCP-open, not HTTP** — inference servers stop answering HTTP
  `/health` under load while still serving; a closed port is the real "down."

## Related

- Telemetry collector: [dgx-scrape](../dgx-scrape/README.md)
- GPU dashboards: `../observability/backend/grafana/dashboards/Homelab/` (GPU —
  DCGM, DGX — Services)
- Systems index: [`infra/README.md`](../README.md)
