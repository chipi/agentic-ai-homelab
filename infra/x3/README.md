# infra/x3 — the X3 workstation

What runs on the X3 (`omarchy`, 100.92.54.65) for the homelab, and how. Rules for agents:
[`AGENTS.md`](AGENTS.md). Deploy, status, logs and undo: `docs/recipes/x3-deploy.md`.

| Service | What | Where |
|---|---|---|
| `ollama-assistant` (user unit) | the assistant model, `qwen3:30b-a3b-instruct-2507-q4_K_M`, 32k context, kept loaded | `100.92.54.65:11435` (tailnet only; the mini reaches it, nothing else) |
| `alloy-research` (user unit) | the X3 collector: host and GPU metrics, the Ollama logs, the eval stack's logs and metrics | `infra/observability/hosts/x3/` |
| `assistant-ui-eval/` (compose) | LibreChat and Open WebUI side by side, until the UI decision | loopback, published by `tailscale serve` on 8443/8444 |

The eval harness's own Ollama (`127.0.0.1:11434`, started by its long-job runs) is not ours: same
binary and model directory, separate process. See the GPU memory rule in `AGENTS.md`.

The LiteLLM alias `assistant` on the mini sends to this model first and falls back to
`assistant-cloud` (the same model on OpenRouter) when the X3 does not answer.
