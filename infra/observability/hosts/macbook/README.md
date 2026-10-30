# MacBook research collector

What a local-model run on the MacBook (Apple M4 Pro, 48 GB) needs recorded next to its results,
sent to the mini over the tailnet with the same series names as the DGX (`instance="macbook"`,
`cluster="workstation"`):

| Signal | Source |
|---|---|
| CPU, memory | `prometheus.exporter.unix` (`job="integrations/unix"`) |
| Ollama log (loads, per-request speed) | Homebrew's Ollama service log, `/opt/homebrew/var/log/ollama.log` (`job="ollama"`) |

Not collected: GPU utilisation (macOS exposes it only through `powermetrics`, which needs root),
and Ollama metrics (the `ollama-metrics` sidecar is a container).

## Install (user level, no root)

The laptop's checkout is a working copy, so it is not pulled for this; the config comes from git:

```bash
# Alloy v1.17.0 (alloy-darwin-arm64.zip, SHA256SUMS-verified) into ~/.local/opt/alloy-1.17.0,
# linked as ~/.local/opt/alloy.
cd ~/Projects/agentic-ai-homelab && git fetch -q origin
mkdir -p ~/.config/alloy-research ~/.local/state/alloy-research
git show origin/main:infra/observability/hosts/macbook/config.alloy > ~/.config/alloy-research/config.alloy
git show origin/main:infra/observability/hosts/macbook/dev.homelab.alloy-research.plist \
  > ~/Library/LaunchAgents/dev.homelab.alloy-research.plist
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/dev.homelab.alloy-research.plist
```

A config change: the same `git show` into `~/.config/alloy-research/`, then
`launchctl kickstart -k gui/$(id -u)/dev.homelab.alloy-research`. Undo:
`launchctl bootout gui/$(id -u)/dev.homelab.alloy-research` and delete the plist.
