# AGENTS.md — infra/x3 (the X3 workstation as a deployment surface)

The X3 (`omarchy`, 100.92.54.65) is the operator's workstation and the third deployment surface,
next to the mini and the DGX (RFC-0008). It runs the local assistant model; the eval harness uses
the same box for its own runs.

- **Deploy from `~/deploy/agentic-ai-homelab`, a checkout on `main`, never from `/work/...`.**
  `/work/agentic-ai-homelab` is the dev tree (branches, uncommitted edits). Every unit here and the
  X3 collector are linked from the deploy checkout: `git -C ~/deploy/agentic-ai-homelab pull
  --ff-only` + a restart deploys a change. Recipe: `docs/recipes/x3-deploy.md`.
- **User units only** (`systemctl --user`, linger is on). No root on this box for our services;
  the operator runs the few `sudo` steps (ufw, `tailscale serve`) by hand.
- **The eval harness rule.** The assistant (port 11435) and the harness's Ollama (127.0.0.1:11434)
  share 62 GiB of GPU memory (GTT). Before a harness run of a model over ~35 GB:
  `systemctl --user stop ollama-assistant`; start it again after. Phase 1 measured gpt-oss:120b
  beside the assistant: 37% CPU offload and swap 16 → 41 GB.
- **Ollama upgrades are the operator's call.** Both instances use
  `~/.local/opt/ollama-<version>`; the unit names the version. Changing it changes the eval
  harness's baseline too, so ask first.
- **Port 11435 is the only one open to the tailnet** for our services, and only `tag:homelab-host`
  may reach it (chipi/infra `tailscale/policy.hujson`). Don't publish another port without the
  ACL and ufw change being agreed.
- `assistant-ui-eval/` is the throwaway UI comparison (RFC-0008 phase 3); it runs from the dev
  tree and is removed after the decision.
