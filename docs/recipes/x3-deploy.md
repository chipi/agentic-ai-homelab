# X3 deploy — the assistant and the collector

## Why this exists

The X3 (`omarchy`) is the third deployment surface next to the mini and the DGX (RFC-0008). Its
services are systemd **user** units, linked from a deploy checkout on `main`, so the dev tree in
`/work/agentic-ai-homelab` can hold branches without changing what runs. Rules:
[`infra/x3/AGENTS.md`](https://github.com/chipi/agentic-ai-homelab/blob/main/infra/x3/AGENTS.md).

## Quick reference

| What | Command (on the X3) |
|---|---|
| deploy a change | `git -C ~/deploy/agentic-ai-homelab pull --ff-only && systemctl --user daemon-reload && systemctl --user restart ollama-assistant alloy-research` |
| status | `systemctl --user status ollama-assistant alloy-research` |
| what is loaded | `curl -s http://100.92.54.65:11435/api/ps` |
| logs | `tail -f ~/.local/state/log/ollama-assistant/ollama.log`; in VictoriaLogs `instance:x3 service:assistant` |
| before a big eval-harness run | `systemctl --user stop ollama-assistant` (models over ~35 GB), `start` after |

## One-time setup

```bash
git clone https://github.com/chipi/agentic-ai-homelab.git ~/deploy/agentic-ai-homelab
D=~/deploy/agentic-ai-homelab
ln -sfn $D/infra/x3/ollama-assistant.service ~/.config/systemd/user/ollama-assistant.service
ln -sfn $D/infra/observability/hosts/x3/alloy-research.service ~/.config/systemd/user/alloy-research.service
systemctl --user daemon-reload
systemctl --user enable --now ollama-assistant
systemctl --user restart alloy-research
```

The operator's `sudo` steps (once):

```bash
sudo ufw allow in on tailscale0 to any port 11435 proto tcp comment 'homelab assistant (RFC-0008)'
```

The Tailscale ACL (chipi/infra `tailscale/policy.hujson`) lets `tag:homelab-host` reach
`omarchy:11435` and nothing else on the X3.

## Verification

- From the mini: `curl -s http://100.92.54.65:11435/api/version` answers; another X3 port does not.
- `curl -s http://100.92.54.65:11435/api/ps` lists `qwen3:30b-a3b-instruct-2507-q4_K_M` with
  `size_vram` equal to its size (on the GPU).
- The eval harness's Ollama on `127.0.0.1:11434` keeps its PID.
- The hub: Hosts → X3 lamp green; the `x3-assistant-down` alert is not firing.

## Undo

```bash
systemctl --user disable --now ollama-assistant
rm ~/.config/systemd/user/ollama-assistant.service && systemctl --user daemon-reload
sudo ufw delete allow in on tailscale0 to any port 11435 proto tcp
```

Then revert the ACL rule in chipi/infra, and point LiteLLM's `assistant` alias at
`assistant-cloud` only.

## Troubleshooting

- **The unit restarts every 15 s right after boot:** it binds the tailnet address, which exists
  only once `tailscaled` is up; it settles by itself.
- **Slow answers, swap rising:** something else holds GPU memory (GTT 62 GiB), usually an eval
  harness model. `curl -s http://127.0.0.1:11434/api/ps` shows it; see the rule above.
- **The log grows without bound:** it is an append file with no rotation. Truncate it with
  `: > ~/.local/state/log/ollama-assistant/ollama.log` (the collector tails from the end).
