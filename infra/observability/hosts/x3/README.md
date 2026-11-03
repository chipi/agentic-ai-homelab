# X3 research collector

What a local-model run on the X3 needs recorded next to its results, sent to the mini over the
tailnet with the same series names as the DGX (`instance="x3"`, `cluster="workstation"`):

| Signal | Source |
|---|---|
| CPU, memory, memory pressure (PSI) | `prometheus.exporter.unix` (`job="integrations/unix"`) |
| AMD Strix Halo GPU busy % and VRAM | the exporter's `drm` collector (`node_drm_*`) |
| Ollama log (loads, offload, per-request `tg = N t/s`) | the long-job file eval-harness runs `ollama serve` under (`job="ollama"`) |
| Assistant UI evaluation containers' logs (`assistant-*` only) | `loki.source.docker` (`service` = container name) |
| The assistant's log (`ollama-assistant` unit) | `~/.local/state/log/ollama-assistant/ollama.log` (`service="assistant"`) |
| LibreChat and mcp-grafana metrics | `/metrics` on `127.0.0.1:3080` (bearer secret in `~/.config/assistant-ui-eval/metrics-secret`) and `:3082` (`job="librechat"`, `job="mcp-grafana"`) |

The evaluation UIs also send their own traces to VictoriaTraces (services `librechat`,
`open-webui`), and Open WebUI pushes its metrics over OTLP (label `service.name="open-webui"`);
see `infra/x3/assistant-ui-eval/docker-compose.yml`. Their LLM calls are traced in Langfuse by
the gateway (project `agents`, key `assistant-ui-eval`).

No Ollama metrics exporter here: the `ollama-metrics` sidecar is a container, and the X3's
Docker holds only the operator's dev work and the evaluation stack. The log carries the model
and speed lines.

## Install (user level, no root)

```bash
# Alloy v1.17.0 (the fleet's version) from the release zip, SHA256SUMS-verified, into
# ~/.local/opt/alloy-1.17.0, linked as ~/.local/opt/alloy.
ln -sfn ~/deploy/agentic-ai-homelab/infra/observability/hosts/x3/alloy-research.service \
  ~/.config/systemd/user/alloy-research.service
systemctl --user daemon-reload && systemctl --user enable --now alloy-research
```

The unit and config are read from the deploy checkout `~/deploy/agentic-ai-homelab` (on `main`,
not the dev tree), so `git -C ~/deploy/agentic-ai-homelab pull --ff-only` + `systemctl --user
restart alloy-research` deploys a change. Undo: `systemctl --user disable --now alloy-research` and remove the link.
