# X3 research collector

What a local-model run on the X3 needs recorded next to its results, sent to the mini over the
tailnet with the same series names as the DGX (`instance="x3"`, `cluster="workstation"`):

| Signal | Source |
|---|---|
| CPU, memory, memory pressure (PSI) | `prometheus.exporter.unix` (`job="integrations/unix"`) |
| AMD Strix Halo GPU busy % and VRAM | the exporter's `drm` collector (`node_drm_*`) |
| Ollama log (loads, offload, per-request `tg = N t/s`) | the long-job file eval-harness runs `ollama serve` under (`job="ollama"`) |

No Ollama metrics exporter here: the `ollama-metrics` sidecar is a container, and the X3 runs no
Docker. The log carries the model and speed lines.

## Install (user level, no root)

```bash
# Alloy v1.17.0 (the fleet's version) from the release zip, SHA256SUMS-verified, into
# ~/.local/opt/alloy-1.17.0, linked as ~/.local/opt/alloy.
ln -sfn /work/agentic-ai-homelab/infra/observability/hosts/x3/alloy-research.service \
  ~/.config/systemd/user/alloy-research.service
systemctl --user daemon-reload && systemctl --user enable --now alloy-research
```

The config is read from this checkout, so `git pull` + `systemctl --user restart alloy-research`
deploys a change. Undo: `systemctl --user disable --now alloy-research` and remove the link.
